"""Unit tests for app.services.transcription_service.

These tests mock heavy ML/HTTP dependencies and exercise branching logic for
local/API transcription, MPS handling, and speaker diarization formatting.
"""

import os
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


def _ensure_stubbed_heavy_modules():
    """Provide lightweight stubs for heavy optional deps used by the service."""
    # torch with backends and cuda flags
    torch = types.SimpleNamespace()
    torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
    torch.cuda = types.SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None, get_device_properties=lambda *_: types.SimpleNamespace(total_memory=8 * 1024**3), memory_allocated=lambda *_: 0)
    torch.float16 = object()
    torch.float32 = object()
    sys.modules.setdefault("torch", torch)  # simple stub

    # transformers pipeline/model/processor
    transformers = types.SimpleNamespace(AutoModelForSpeechSeq2Seq=Mock(), AutoProcessor=Mock(), pipeline=Mock())
    sys.modules.setdefault("transformers", transformers)

    # openai client with OpenAI symbol
    openai_mod = types.ModuleType("openai")
    setattr(openai_mod, "OpenAI", object)
    sys.modules.setdefault("openai", openai_mod)

    # numpy
    sys.modules.setdefault("numpy", types.ModuleType("numpy"))

    # torchaudio.functional alias used as F
    torchaudio = types.ModuleType("torchaudio")
    setattr(torchaudio, "functional", types.SimpleNamespace())
    sys.modules.setdefault("torchaudio", torchaudio)

    # pyannote will be patched per-test when needed
    sys.modules.setdefault("pyannote", types.ModuleType("pyannote"))
    pa = types.ModuleType("pyannote.audio")
    # Minimal Pipeline placeholder so module import succeeds
    class _Pipeline:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            raise RuntimeError("not used in import phase")
    setattr(pa, "Pipeline", _Pipeline)
    sys.modules.setdefault("pyannote.audio", pa)

    # Minimal PyQt6 stubs for modules that import Qt types
    sys.modules.setdefault("PyQt6", types.ModuleType("PyQt6"))
    qtcore = types.ModuleType("PyQt6.QtCore")
    class _QObject:
        def __init__(self, *a, **k):
            pass
    qtcore.QObject = _QObject
    qtcore.pyqtSignal = lambda *a, **k: None
    sys.modules.setdefault("PyQt6.QtCore", qtcore)
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    class _QWidget:  # only for type reference
        pass
    qtwidgets.QWidget = _QWidget
    sys.modules.setdefault("PyQt6.QtWidgets", qtwidgets)


_ensure_stubbed_heavy_modules()


from app.services.transcription_service import TranscriptionService, ModelManager


class TestTranscriptionService(unittest.TestCase):
    def setUp(self):
        # Patch logger to keep quiet and assert warnings
        self.logger_patcher = patch("app.services.transcription_service.logger")
        self.mock_logger = self.logger_patcher.start()

        # Stub ModelManager.instance() to avoid real model loading
        self.mm_patcher = patch.object(ModelManager, "instance")
        self.mock_mm_instance = self.mm_patcher.start()
        self.mm = Mock()
        self.mm._get_optimal_device.return_value = "cpu"
        self.mm.create_pipeline.return_value = lambda path: {"text": "hello", "chunks": []}
        self.mock_mm_instance.return_value = self.mm

        self.svc = TranscriptionService()

        # Create a temp file for paths that require opening
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.write(b"data")
        self.tmp.flush()
        self.tmp.close()
        self.file_path = self.tmp.name

    def tearDown(self):
        self.logger_patcher.stop()
        self.mm_patcher.stop()
        try:
            os.unlink(self.file_path)
        except FileNotFoundError:
            pass

    def test_transcribe_file_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.svc.transcribe_file("/nope.wav", model_id="m", method="local")

    def test_transcribe_file_api_ignores_speaker_detection_with_warning(self):
        with patch.object(self.svc, "_transcribe_with_api", return_value={"text": "x", "method": "api"}) as m:
            out = self.svc.transcribe_file(self.file_path, model_id="m", method="api", language="en", openai_api_key="sk-1", speaker_detection=True)
        self.assertEqual(out["method"], "api")
        self.mock_logger.warning.assert_called()  # speaker detection ignored
        m.assert_called()

    def test_transcribe_file_mps_path_selected(self):
        # Simulate MPS available and CUDA off
        import torch as torch_mod
        torch_mod.backends.mps.is_available = lambda: True
        torch_mod.cuda.is_available = lambda: False
        with patch.object(self.svc, "_transcribe_with_mps", return_value={"text": "mps"}) as m:
            out = self.svc.transcribe_file(self.file_path, model_id="m", method="local", language="en", speaker_detection=False, hardware_acceleration_enabled=True)
        self.assertEqual(out["text"], "mps")
        m.assert_called_once()

    def test_transcribe_file_mps_with_speaker_detection_prefers_cpu(self):
        # MPS available but speaker detection forces CPU/local path
        import torch as torch_mod
        torch_mod.backends.mps.is_available = lambda: True
        torch_mod.cuda.is_available = lambda: False
        with patch.object(self.svc, "_transcribe_locally", return_value={"text": "cpu"}) as m:
            out = self.svc.transcribe_file(self.file_path, model_id="m", method="local", language="en", speaker_detection=True, hardware_acceleration_enabled=True)
        self.assertEqual(out["text"], "cpu")
        self.mock_logger.warning.assert_called()
        m.assert_called_once()

    def test_transcribe_file_standard_local_path(self):
        # No MPS path -> standard local
        import torch as torch_mod
        torch_mod.backends.mps.is_available = lambda: False
        with patch.object(self.svc, "_transcribe_locally", return_value={"text": "ok"}) as m:
            out = self.svc.transcribe_file(self.file_path, model_id="m", method="local", language="en")
        self.assertEqual(out["text"], "ok")
        m.assert_called_once()

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


if __name__ == "__main__":
    unittest.main()
