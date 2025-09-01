"""Unit tests for app.services.transcription_service.

These tests mock heavy ML/HTTP dependencies and exercise branching logic for
local/API transcription, MPS handling, and speaker diarization formatting.

Isolation note: Build and inject stubs for heavy modules via patch.dict in
setUp/tearDown to avoid leaking global sys.modules state across the suite.
"""

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


def _build_heavy_module_stubs() -> dict[str, object]:
    """Create stubs for heavy optional deps used by the service.

    Returns a mapping suitable for ``patch.dict(sys.modules, mapping)``.
    """
    mapping: dict[str, object] = {}

    # torch with backends and cuda flags
    torch = types.SimpleNamespace()
    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    torch.cuda = types.SimpleNamespace(
        is_available=lambda: False,
        empty_cache=lambda: None,
        get_device_properties=lambda *_: types.SimpleNamespace(total_memory=8 * 1024**3),
        memory_allocated=lambda *_: 0,
    )
    torch.float16 = object()
    torch.float32 = object()
    mapping["torch"] = torch

    # transformers pipeline/model/processor
    transformers = types.SimpleNamespace(
        AutoModelForSpeechSeq2Seq=Mock(),
        AutoProcessor=Mock(),
        pipeline=Mock(),
    )
    mapping["transformers"] = transformers

    # openai client with OpenAI symbol
    openai_mod = types.ModuleType("openai")
    setattr(openai_mod, "OpenAI", object)
    mapping["openai"] = openai_mod

    # numpy
    mapping["numpy"] = types.ModuleType("numpy")

    # torchaudio.functional alias used as F
    torchaudio = types.ModuleType("torchaudio")
    setattr(torchaudio, "functional", types.SimpleNamespace())
    mapping["torchaudio"] = torchaudio

    # pyannote (placeholder; Pipeline overridden per-test when needed)
    mapping["pyannote"] = types.ModuleType("pyannote")
    pa = types.ModuleType("pyannote.audio")
    class _Pipeline:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            raise RuntimeError("not used in import phase")
    setattr(pa, "Pipeline", _Pipeline)
    mapping["pyannote.audio"] = pa

    # Minimal PyQt6 stubs for modules that import Qt types
    pyqt = types.ModuleType("PyQt6")
    qtcore = types.ModuleType("PyQt6.QtCore")
    class _QObject:
        def __init__(self, *a, **k):
            pass
    qtcore.QObject = _QObject
    qtcore.pyqtSignal = lambda *a, **k: None
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    class _QWidget:  # only for type reference
        pass
    qtwidgets.QWidget = _QWidget
    mapping["PyQt6"] = pyqt
    mapping["PyQt6.QtCore"] = qtcore
    mapping["PyQt6.QtWidgets"] = qtwidgets

    return mapping


# Service module is imported inside setUp after patching sys.modules


class TestTranscriptionService(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures with isolated mocks."""
        self._setup_module_stubs()
        self._setup_mocks()
        self._setup_service()
        self._setup_test_file()

    def _setup_module_stubs(self):
        """Inject heavy-module stubs to avoid real imports."""
        self._mods = _build_heavy_module_stubs()
        self._mods_patcher = patch.dict(sys.modules, self._mods, clear=False)
        self._mods_patcher.start()
        import app.services.transcription_service as tsvc
        self._tsvc = tsvc

    def _setup_mocks(self):
        """Configure mocks for logger and ModelManager."""
        # Patch logger to capture warnings/errors
        self.logger_patcher = patch("app.services.transcription_service.logger")
        self.mock_logger = self.logger_patcher.start()

        # Stub ModelManager to avoid real model loading
        self.mm_patcher = patch.object(self._tsvc.ModelManager, "instance")
        self.mock_mm_instance = self.mm_patcher.start()
        self.mm = Mock()
        self.mm._get_optimal_device.return_value = "cpu"
        self.mm.create_pipeline.return_value = lambda path: {"text": "hello", "chunks": []}
        self.mock_mm_instance.return_value = self.mm

    def _setup_service(self):
        """Initialize the service under test."""
        self.svc = self._tsvc.TranscriptionService()

    def _setup_test_file(self):
        """Create a mock file path instead of actual temp file."""
        # Use a mock file path instead of creating real file (fixes Mystery Guest)
        self.file_path = "/mock/test/audio.wav"
        # Patch file operations to avoid real filesystem access
        self.open_patcher = patch("builtins.open", create=True)
        self.mock_open = self.open_patcher.start()
        self.mock_open.return_value.__enter__.return_value.read.return_value = b"mock audio data"
        
        # Patch os.path.exists to return True for our mock file
        self.exists_patcher = patch("os.path.exists")
        self.mock_exists = self.exists_patcher.start()
        self.mock_exists.return_value = True

    def tearDown(self):
        """Clean up all patches."""
        self.logger_patcher.stop()
        self.mm_patcher.stop()
        self._mods_patcher.stop()
        self.open_patcher.stop()
        self.exists_patcher.stop()

    def test_transcribe_file_missing_file_raises(self):
        # Configure mock to return False for non-existent file
        self.mock_exists.return_value = False
        with self.assertRaises(FileNotFoundError):
            self.svc.transcribe_file("/nope.wav", model_id="m", method="local")

    def test_transcribe_file_api_ignores_speaker_detection_with_warning(self):
        """Test that API method ignores speaker_detection and logs warning."""
        with patch.object(self.svc, "_transcribe_with_api", return_value={"text": "x", "method": "api"}) as mock_api:
            out = self.svc.transcribe_file(
                self.file_path, model_id="m", method="api", 
                language="en", openai_api_key="sk-1", speaker_detection=True
            )
        
        # Verify the API method was used and speaker detection was NOT passed
        self.assertEqual(out["method"], "api")
        self.assertEqual(out["text"], "x")
        
        # Verify warning was logged about speaker detection being ignored
        warning_calls = [call for call in self.mock_logger.warning.call_args_list]
        self.assertTrue(any("speaker" in str(call).lower() for call in warning_calls),
                        "Expected warning about speaker detection being ignored")
        
        # Verify API was called WITHOUT speaker_detection parameter
        mock_api.assert_called_once()
        call_args = mock_api.call_args
        # The API method shouldn't receive speaker_detection parameter
        self.assertNotIn("speaker_detection", call_args[1] if call_args[1] else {})

    def test_transcribe_file_mps_path_selected(self):
        """Test that MPS acceleration is used when available and enabled."""
        # Simulate MPS available and CUDA off
        import torch as torch_mod
        torch_mod.backends.mps.is_available = lambda: True
        torch_mod.cuda.is_available = lambda: False
        
        mps_result = {"text": "mps transcribed", "method": "local_mps"}
        with patch.object(self.svc, "_transcribe_with_mps", return_value=mps_result) as mock_mps:
            out = self.svc.transcribe_file(
                self.file_path, model_id="m", method="local", 
                language="en", speaker_detection=False, hardware_acceleration_enabled=True
            )
        
        # Verify MPS path was used and returned correct result
        self.assertEqual(out["text"], "mps transcribed")
        self.assertEqual(out["method"], "local_mps")
        
        # Verify MPS method was called with correct parameters
        mock_mps.assert_called_once_with(self.file_path, "m", "en")

    def test_transcribe_file_mps_with_speaker_detection_prefers_cpu(self):
        """Test that speaker detection forces CPU path even with MPS available."""
        # MPS available but speaker detection forces CPU/local path
        import torch as torch_mod
        torch_mod.backends.mps.is_available = lambda: True
        torch_mod.cuda.is_available = lambda: False
        
        cpu_result = {"text": "cpu transcribed", "method": "local"}
        with patch.object(self.svc, "_transcribe_locally", return_value=cpu_result) as mock_local:
            out = self.svc.transcribe_file(
                self.file_path, model_id="m", method="local", 
                language="en", speaker_detection=True, hardware_acceleration_enabled=True
            )
        
        # Verify CPU path was used instead of MPS
        self.assertEqual(out["text"], "cpu transcribed")
        self.assertEqual(out["method"], "local")
        
        # Verify warning about MPS being unavailable for speaker detection
        warning_calls = [call for call in self.mock_logger.warning.call_args_list]
        self.assertTrue(any("mps" in str(call).lower() for call in warning_calls),
                        "Expected warning about MPS not supporting speaker detection")
        
        # Verify local method was called with speaker detection enabled
        mock_local.assert_called_once()
        call_args = mock_local.call_args[0]
        self.assertTrue(call_args[3])  # speaker_detection parameter should be True

    def test_transcribe_file_standard_local_path(self):
        """Test standard local transcription when MPS is not available."""
        # No MPS path -> standard local
        import torch as torch_mod
        torch_mod.backends.mps.is_available = lambda: False
        
        local_result = {"text": "local transcribed", "method": "local", "chunks": []}
        with patch.object(self.svc, "_transcribe_locally", return_value=local_result) as mock_local:
            out = self.svc.transcribe_file(self.file_path, model_id="m", method="local", language="en")
        
        # Verify local path was used with correct result
        self.assertEqual(out["text"], "local transcribed")
        self.assertEqual(out["method"], "local")
        self.assertIn("chunks", out)
        
        # Verify local method was called with correct parameters
        mock_local.assert_called_once_with(self.file_path, "m", "en", False, None)

    def test__transcribe_locally_basic_and_string_result(self):
        # dict result
        res = self.svc._transcribe_locally(self.file_path, "m", "en", False, None)
        self.assertEqual(res["text"], "hello")
        # string result path
        self.mm.create_pipeline.return_value = lambda p: "hi"
        res2 = self.svc._transcribe_locally(self.file_path, "m", "en", False, None)
        self.assertEqual(res2["text"], "hi")

    def test__transcribe_locally_with_speaker_detection_success(self):
        self.mm.create_pipeline.return_value = lambda p: {"text": "base", "chunks": [{"text": "a", "timestamp": (0, 1)}]}
        with patch.object(self.svc, "_add_speaker_detection", return_value={"text": "base", "chunks": [], "has_speaker_detection": True}):
            out = self.svc._transcribe_locally(self.file_path, "m", "en", True, "hf")
        self.assertTrue(out.get("has_speaker_detection"))

    def test__transcribe_locally_with_speaker_detection_error_falls_back(self):
        self.mm.create_pipeline.return_value = lambda p: {"text": "base"}
        with patch.object(self.svc, "_add_speaker_detection", side_effect=Exception("boom")):
            out = self.svc._transcribe_locally(self.file_path, "m", "en", True, "hf")
        self.assertEqual(out["text"], "base")
        self.mock_logger.error.assert_called()

    def test__transcribe_locally_pipeline_exception_wrapped(self):
        self.mm.create_pipeline.side_effect = RuntimeError("fail")
        with self.assertRaises(RuntimeError):
            self.svc._transcribe_locally(self.file_path, "m", "en", False, None)

    def test__transcribe_with_api_success(self):
        # Prepare a fake OpenAI client
        class FakeRsp:
            text = "ok"

        class FakeTranscriptions:
            def create(self, **kwargs):
                return FakeRsp()

        class FakeAudio:
            def __init__(self):
                self.transcriptions = FakeTranscriptions()

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.audio = FakeAudio()

        with patch("app.services.transcription_service.OpenAI", return_value=FakeClient()):
            out = self.svc._transcribe_with_api(self.file_path, "english", api_key="sk")
        self.assertEqual(out["text"], "ok")

    def test__transcribe_with_api_input_validation(self):
        with self.assertRaises(ValueError):
            self.svc._transcribe_with_api(self.file_path, "english", api_key=None)
        with self.assertRaises(ValueError):
            self.svc._transcribe_with_api(self.file_path, "english", api_key="sk", base_url="http://insecure")

    def test__transcribe_with_api_empty_response_raises(self):
        class EmptyRsp:
            text = ""

        class FakeTranscriptions:
            def create(self, **kwargs):
                return EmptyRsp()

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.audio = types.SimpleNamespace(transcriptions=FakeTranscriptions())

        with patch("app.services.transcription_service.OpenAI", return_value=FakeClient()):
            with self.assertRaises(RuntimeError):
                self.svc._transcribe_with_api(self.file_path, "english", api_key="sk")

    def test__transcribe_with_api_exception_wrapped(self):
        class BoomClient:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("boom")

        with patch("app.services.transcription_service.OpenAI", side_effect=BoomClient):
            with self.assertRaises(RuntimeError):
                self.svc._transcribe_with_api(self.file_path, "english", api_key="sk")

    def test__add_speaker_detection_labels_chunks(self):
        # Build fake diarization output
        class Seg:
            def __init__(self, start, end):
                self.start = start
                self.end = end

        class FakeDiarization:
            def itertracks(self, yield_label=False):
                # Two speakers A then B
                yield (Seg(0, 1), None, "A")
                yield (Seg(1, 2), None, "B")

        class FakePipeline:
            def __call__(self, path):
                return FakeDiarization()

        class PipelineWrapper:
            @staticmethod
            def from_pretrained(*args, **kwargs):
                return FakePipeline()

        # Inject into sys.modules so local import sees it
        pa = sys.modules["pyannote.audio"]
        setattr(pa, "Pipeline", PipelineWrapper)

        base = {"text": "t", "chunks": [{"text": "c1", "timestamp": (0, 0.5)}, {"text": "c2", "timestamp": (1.1, 1.5)}]}
        out = self.svc._add_speaker_detection(self.file_path, base, hf_auth_key="hf")
        self.assertTrue(out.get("has_speaker_detection"))
        self.assertIn("formatted_text", out)
        self.assertIn("speaker", out["chunks"][0])

    def test__add_speaker_detection_no_segments_returns_original(self):
        class FakeDiarization:
            def itertracks(self, yield_label=False):
                if False:
                    yield None  # pragma: no cover

        class FakePipeline:
            def __call__(self, path):
                return FakeDiarization()

        class PipelineWrapper:
            @staticmethod
            def from_pretrained(*args, **kwargs):
                return FakePipeline()

        pa = sys.modules["pyannote.audio"]
        setattr(pa, "Pipeline", PipelineWrapper)

        base = {"text": "t", "chunks": []}
        out = self.svc._add_speaker_detection(self.file_path, base, hf_auth_key="hf")
        self.assertEqual(out, base)

    # --- Additional edge/error tests from plan ---

    def test_permission_denied_file(self):
        def bad_pipe(_path):
            raise PermissionError('denied')
        self.mm.create_pipeline.return_value = bad_pipe
        with self.assertRaises(RuntimeError):
            self.svc.transcribe_file(self.file_path, model_id='m', method='local')

    def test_directory_instead_of_file(self):
        """Test that passing a directory path raises appropriate error."""
        # Mock a directory path
        dir_path = "/mock/directory/"
        
        # Configure mock to simulate directory check
        def dir_pipe(path):
            if path.endswith('/'):
                raise IsADirectoryError('is a directory')
            return {"text": "ok"}
        
        self.mm.create_pipeline.return_value = dir_pipe
        
        with self.assertRaises(RuntimeError):
            self.svc.transcribe_file(dir_path, model_id='m', method='local')

    def test_invalid_audio_format(self):
        """Test that invalid audio format raises appropriate error."""
        # Mock a text file path
        text_file_path = "/mock/file.txt"
        
        def invalid_pipe(path):
            if path.endswith('.txt'):
                raise ValueError('unsupported audio format')
            return {"text": "ok"}
        
        self.mm.create_pipeline.return_value = invalid_pipe
        
        with self.assertRaises(RuntimeError):
            self.svc.transcribe_file(text_file_path, model_id='m', method='local')

    def test_corrupted_audio(self):
        def pipe_raises(_):
            raise IOError('file truncated')
        self.mm.create_pipeline.return_value = pipe_raises
        with self.assertRaises(RuntimeError):
            self.svc.transcribe_file(self.file_path, model_id='m', method='local')

    def test_api_network_timeout(self):
        class FakeTranscriptions:
            def create(self, **kwargs):
                import requests
                raise requests.Timeout('timeout')
        class FakeAudio:
            def __init__(self):
                self.transcriptions = FakeTranscriptions()
        class FakeClient:
            def __init__(self, *a, **k):
                self.audio = FakeAudio()
        with patch('app.services.transcription_service.OpenAI', return_value=FakeClient()):
            with self.assertRaises(RuntimeError):
                self.svc.transcribe_file(self.file_path, model_id='m', method='api', language='en', openai_api_key='sk')

    def test_api_authentication_errors(self):
        class FakeTranscriptions:
            def create(self, **kwargs):
                raise Exception('401 Unauthorized')
        class FakeClient:
            def __init__(self, *a, **k):
                self.audio = types.SimpleNamespace(transcriptions=FakeTranscriptions())
        with patch('app.services.transcription_service.OpenAI', return_value=FakeClient()):
            with self.assertRaises(RuntimeError):
                self.svc._transcribe_with_api(self.file_path, 'english', api_key='sk')

    def test_speaker_detection_requested_but_no_hf_key(self):
        # With speaker_detection True but no key, returns base result (no crash)
        self.mm.create_pipeline.return_value = lambda p: {"text": "base", "chunks": []}
        out = self.svc._transcribe_locally(self.file_path, 'm', 'en', True, None)
        self.assertEqual(out["text"], "base")


class TestModelManagerDeviceSelection(unittest.TestCase):
    def setUp(self):
        self._mods = _build_heavy_module_stubs()
        self._mods_patcher = patch.dict(sys.modules, self._mods, clear=False)
        self._mods_patcher.start()
        import app.services.transcription_service as tsvc
        self._tsvc = tsvc

    def test_hw_accel_disabled_returns_cpu(self):
        with patch("app.utils.ConfigManager") as CM:
            inst = Mock(); inst.get.return_value = False
            CM.instance.return_value = inst
            mm = self._tsvc.ModelManager()
            self.assertEqual(mm.device, "cpu")

    def test_cuda_selected_with_sufficient_memory(self):
        import torch as torch_mod
        torch_mod.cuda.is_available = lambda: True
        torch_mod.cuda.get_device_properties = lambda *_: types.SimpleNamespace(total_memory=8 * 1024**3)
        torch_mod.cuda.memory_allocated = lambda *_: 2 * 1024**3
        with patch("app.utils.ConfigManager") as CM:
            inst = Mock(); inst.get.return_value = True
            CM.instance.return_value = inst
            mm = self._tsvc.ModelManager()
            self.assertEqual(mm.device, "cuda")

    def test_cuda_insufficient_memory_falls_back_cpu(self):
        import torch as torch_mod
        torch_mod.cuda.is_available = lambda: True
        torch_mod.cuda.get_device_properties = lambda *_: types.SimpleNamespace(total_memory=2 * 1024**3)
        torch_mod.cuda.memory_allocated = lambda *_: 1.5 * 1024**3
        with patch("app.utils.ConfigManager") as CM:
            inst = Mock(); inst.get.return_value = True
            CM.instance.return_value = inst
            mm = self._tsvc.ModelManager()
            self.assertEqual(mm.device, "cpu")

    def test_get_free_gpu_memory_exception_returns_zero(self):
        import torch as torch_mod
        torch_mod.cuda.is_available = lambda: True
        def boom(*_):
            raise RuntimeError("cuda error")
        torch_mod.cuda.get_device_properties = boom
        mm = self._tsvc.ModelManager.instance()
        # Bypass __init__ device concerns by directly calling helper
        # Bypass __init__ device concerns by directly calling helper
        self.assertEqual(mm._get_free_gpu_memory(), 0.0)

    def tearDown(self):
        self._mods_patcher.stop()

if __name__ == "__main__":
    unittest.main()
