"""
Unit tests for app.utils covering:
- file type detection, ffmpeg checks, URL validation, language conversion
- backup/timestamp helpers, system requirement checks, temp cleanup
- ConfigManager and PromptManager behaviors

Tests run headless by injecting lightweight stubs for PyQt6 and torch before
importing app.utils.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import types
import sys
import json


# --- Inject minimal stubs before importing app.utils (only for truly optional deps) ---
torch_stub = types.ModuleType("torch")
cuda_ns = types.SimpleNamespace(
    is_available=lambda: False,
    device_count=lambda: 0,
    get_device_name=lambda idx: f"GPU{idx}",
    get_device_properties=lambda idx: types.SimpleNamespace(total_memory=8 * 1024**3),
)
backends_ns = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
torch_stub.cuda = cuda_ns
torch_stub.backends = backends_ns
sys.modules["torch"] = torch_stub
_orig_sysmods = {k: sys.modules.get(k) for k in ("torch",)}


from app import utils  # noqa: E402 (import after stubs)

# Restore original modules to avoid impacting other test modules
for _k, _v in _orig_sysmods.items():
    if _v is None:
        sys.modules.pop(_k, None)
    else:
        sys.modules[_k] = _v


class TestFileTypeDetection(unittest.TestCase):
    def test_is_video_file(self):
        self.assertTrue(utils.is_video_file("movie.MP4"))
        self.assertTrue(utils.is_video_file("clip.webm"))
        self.assertFalse(utils.is_video_file("audio.mp3"))
        self.assertFalse(utils.is_video_file("doc.txt"))

    def test_is_audio_file(self):
        self.assertTrue(utils.is_audio_file("voice.WAV"))
        self.assertTrue(utils.is_audio_file("song.ogg"))
        self.assertFalse(utils.is_audio_file("video.mkv"))
        self.assertFalse(utils.is_audio_file("archive.zip"))


class TestFFmpegChecks(unittest.TestCase):
    @patch("app.utils.subprocess.run")
    @patch("app.utils.os.access", return_value=True)
    @patch("app.utils.os.path.exists", return_value=True)
    @patch("app.utils.shutil.which", return_value="/usr/bin/ffmpeg")
    def test_ensure_ffmpeg_available_success(self, *_mocks):
        proc = types.SimpleNamespace(returncode=0, stdout=b"ffmpeg version 4.4")
        with patch("app.utils.subprocess.run", return_value=proc):
            ok, msg = utils.ensure_ffmpeg_available()
        self.assertTrue(ok)
        self.assertIn("ffmpeg", msg.lower())

    @patch("app.utils.os.path.exists", return_value=False)
    @patch("app.utils.shutil.which", return_value=None)
    def test_ensure_ffmpeg_available_not_found(self, *_mocks):
        ok, msg = utils.ensure_ffmpeg_available()
        self.assertFalse(ok)
        self.assertIn("ffmpeg not found", msg.lower())

    def test_check_ffmpeg_success(self):
        proc = types.SimpleNamespace(returncode=0, stdout="ffmpeg version 5.0")
        with patch("app.utils.subprocess.run", return_value=proc):
            self.assertTrue(utils.check_ffmpeg())

    def test_check_ffmpeg_not_found(self):
        with patch("app.utils.subprocess.run", side_effect=FileNotFoundError()):
            self.assertFalse(utils.check_ffmpeg())

    def test_check_ffmpeg_unexpected_error(self):
        with patch("app.utils.subprocess.run", side_effect=RuntimeError("boom")):
            self.assertFalse(utils.check_ffmpeg())


class TestURLAndLanguage(unittest.TestCase):
    def test_validate_url_youtube_variants(self):
        good = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "http://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        ]
        for url in good:
            self.assertTrue(utils.validate_url(url), url)
        self.assertFalse(utils.validate_url("https://example.com/watch?v=dQw4w9WgXcQ"))

    def test_language_to_iso(self):
        self.assertEqual(utils.language_to_iso("english"), "en")
        self.assertEqual(utils.language_to_iso(" English "), "en")
        self.assertEqual(utils.language_to_iso("FRENCH"), "fr")
        self.assertEqual(utils.language_to_iso("unknown"), "en")


class TestBackupAndTimestamp(unittest.TestCase):
    @patch("app.utils.shutil.copy2")
    @patch("app.utils.get_timestamp", return_value="20240101_120000")
    @patch("app.utils.os.makedirs")
    @patch("app.utils.os.path.exists", return_value=True)
    def test_create_backup_success(self, *_mocks):
        path = utils.create_backup("/x/file.txt", backup_dir="/x/backups")
        self.assertTrue(path.endswith("file_20240101_120000.txt"))

    @patch("app.utils.os.path.exists", return_value=False)
    def test_create_backup_nonexistent(self, _exists):
        self.assertIsNone(utils.create_backup("/missing.txt"))

    @patch("app.utils.shutil.copy2", side_effect=IOError("nope"))
    @patch("app.utils.os.path.exists", return_value=True)
    def test_create_backup_failure(self, *_mocks):
        self.assertIsNone(utils.create_backup("/x/file.txt"))

    def test_get_timestamp_format(self):
        class _DT:
            @staticmethod
            def now():
                return types.SimpleNamespace(strftime=lambda fmt: "20240101_123045")

        with patch("app.utils.datetime", new=types.SimpleNamespace(datetime=_DT)):
            self.assertEqual(utils.get_timestamp(), "20240101_123045")


class TestSystemRequirements(unittest.TestCase):
    @patch("app.utils.check_ffmpeg", return_value=True)
    @patch("app.utils.platform.python_version", return_value="3.11.7")
    @patch("app.utils.platform.version", return_value="5.15.0")
    @patch("app.utils.platform.system", return_value="Linux")
    @patch("app.utils.torch.cuda.is_available", return_value=False)
    def test_check_system_requirements_cpu_only(self, *_mocks):
        with patch("app.utils.torch.backends.mps.is_available", return_value=False):
            res = utils.check_system_requirements()
        self.assertIn("os", res)
        self.assertTrue(res["ffmpeg_installed"])  # mocked True
        self.assertIn("issues", res)
        self.assertTrue(any("CPU" in s or "CUDA/MPS" in s for s in res["issues"]))


class TestTempCleanup(unittest.TestCase):
    @patch("app.utils.os.remove")
    @patch("app.utils.os.path.getmtime", return_value=0)
    @patch("time.time", return_value=86400 * 2)
    @patch("glob.glob", return_value=["/tmp/transcribrr_temp_1"])
    @patch("app.utils.os.path.isfile", return_value=True)
    def test_cleanup_temp_files_deletes_old(self, *_mocks):
        deleted = utils.cleanup_temp_files(directory="/tmp", file_pattern="transcribrr_temp_*", max_age_days=1)
        self.assertEqual(deleted, 1)

    @patch("time.time", return_value=100)
    @patch("app.utils.os.path.getmtime", return_value=50)
    @patch("glob.glob", return_value=["/tmp/transcribrr_temp_1"])
    @patch("app.utils.os.path.isfile", return_value=True)
    def test_cleanup_temp_files_none_old(self, *_mocks):
        deleted = utils.cleanup_temp_files(directory="/tmp", file_pattern="transcribrr_temp_*", max_age_days=1)
        self.assertEqual(deleted, 0)

    @patch("app.utils.os.remove", side_effect=PermissionError("denied"))
    @patch("app.utils.os.path.getmtime", return_value=0)
    @patch("time.time", return_value=86400 * 2)
    @patch("glob.glob", return_value=["/tmp/transcribrr_temp_1"])
    @patch("app.utils.os.path.isfile", return_value=True)
    def test_cleanup_temp_files_error(self, *_mocks):
        deleted = utils.cleanup_temp_files(directory="/tmp", file_pattern="transcribrr_temp_*", max_age_days=1)
        self.assertEqual(deleted, 0)


class TestConfigManager(unittest.TestCase):
    def tearDown(self):
        utils.ConfigManager._instance = None

    @patch("app.utils.os.makedirs")
    def test_instance_singleton(self, _mk):
        a = utils.ConfigManager.instance()
        b = utils.ConfigManager.instance()
        self.assertIs(a, b)

    @patch("app.utils.json.load", return_value={"k": "v"})
    @patch("app.utils.open", create=True)
    @patch("app.utils.os.path.exists", return_value=True)
    def test_load_config_success(self, *_mocks):
        cm = utils.ConfigManager.instance()
        self.assertEqual(cm.get("k"), "v")

    @patch.object(utils.ConfigManager, "_save_config")
    @patch("app.utils.os.path.exists", return_value=False)
    def test_load_config_missing_file(self, _exists, mock_save):
        cm = utils.ConfigManager.instance()
        mock_save.assert_called()
        # Defaults present
        self.assertIsInstance(cm.get_all(), dict)

    def test_load_config_corrupt_json(self):
        utils.ConfigManager._instance = None
        with patch("app.utils.os.path.exists", return_value=True), \
            patch("app.utils.open", create=True), \
            patch("app.utils.json.load", side_effect=json.JSONDecodeError("x", "{}", 0)):
            cm = utils.ConfigManager.instance()
            self.assertIsInstance(cm.get_all(), dict)

    def test_save_config_writes_json(self):
        utils.ConfigManager._instance = None
        with patch("app.utils.os.path.exists", return_value=False), \
            patch.object(utils.ConfigManager, "_save_config") as mock_save:
            cm = utils.ConfigManager.instance()
            # First call occurred in _load_config due to missing file
            self.assertTrue(mock_save.called)
        # Now exercise _save_config directly
        with patch("app.utils.os.makedirs") as _mk, \
            patch("app.utils.open", create=True) as _op, \
            patch("app.utils.json.dump") as jdump:
            cm._save_config()
            # Ensure formatting flags passed
            args, kwargs = jdump.call_args
            self.assertEqual(kwargs.get("indent"), 4)
            self.assertTrue(kwargs.get("sort_keys"))

    def test_get_set_update_flows(self):
        utils.ConfigManager._instance = None
        with patch("app.utils.os.path.exists", return_value=False):
            cm = utils.ConfigManager.instance()
        with patch.object(cm, "_save_config") as mock_save:
            # attach a safe signal sink avoiding cross-test PyQt stubs
            mock_emit = MagicMock()
            cm.config_updated = types.SimpleNamespace(emit=mock_emit)
            # set new
            cm.set("x", 1)
            mock_save.assert_called()
            mock_emit.assert_called_with({"x": 1})
            mock_save.reset_mock(); mock_emit.reset_mock()
            # set unchanged
            cm.set("x", 1)
            mock_save.assert_not_called()
            mock_emit.assert_not_called()
            # update multiple
            cm.update({"x": 2, "y": 3})
            self.assertTrue(mock_save.called)
            mock_emit.assert_called_with({"x": 2, "y": 3})
            # get with fallback
            self.assertEqual(cm.get("missing", default=7), 7)
            # get_all returns a copy
            all1 = cm.get_all()
            self.assertIsNot(all1, cm._config)

    @patch("app.utils.create_backup", return_value="/path/to/backup.json")
    def test_config_create_backup_delegates(self, _cb):
        utils.ConfigManager._instance = None
        with patch("app.utils.os.path.exists", return_value=False):
            cm = utils.ConfigManager.instance()
        self.assertTrue(cm.create_backup().endswith("backup.json"))


class TestPromptManager(unittest.TestCase):
    def tearDown(self):
        utils.PromptManager._instance = None

    @patch("app.utils.os.makedirs")
    def test_instance_singleton(self, _mk):
        a = utils.PromptManager.instance()
        b = utils.PromptManager.instance()
        self.assertIs(a, b)

    @patch("app.utils.json.load", return_value={
        "old_style": "text only",
        "new_style": {"text": "hello", "category": "Custom"},
    })
    @patch("app.utils.open", create=True)
    @patch("app.utils.os.path.exists", return_value=True)
    def test_load_prompts_normalizes_and_merges(self, *_mocks):
        pm = utils.PromptManager.instance()
        data = pm.get_prompts()
        # Defaults included and custom prompts normalized
        self.assertIn("old_style", data)
        self.assertEqual(data["old_style"]["category"], "General")
        self.assertEqual(data["new_style"]["text"], "hello")

    def test_normalize_prompts_various(self):
        utils.PromptManager._instance = None
        with patch("app.utils.os.path.exists", return_value=False):
            pm = utils.PromptManager.instance()
        normalized = pm._normalize_prompts({
            "s1": "just text",
            "s2": {"text": "t", "category": "C"},
            "bad": 123,
        })
        self.assertEqual(normalized["s1"]["category"], "General")
        self.assertEqual(normalized["s2"]["category"], "C")
        # invalid entry skipped (not raising)
        self.assertNotIn("bad", normalized)

    def test_add_update_delete_prompt(self):
        utils.PromptManager._instance = None
        with patch("app.utils.os.path.exists", return_value=False):
            pm = utils.PromptManager.instance()
        with patch.object(pm, "_save_prompts") as _sv:
            # Replace Qt signal with simple stub to avoid patching bound signal
            pm.prompts_changed = types.SimpleNamespace(emit=MagicMock())
            # add ok
            self.assertTrue(pm.add_prompt(" Name ", " Text ", " "))
            # add invalid
            self.assertFalse(pm.add_prompt("", ""))
            # update ok
            self.assertTrue(pm.update_prompt("Name", "New", "Cat"))
            # update invalid name
            self.assertFalse(pm.update_prompt("Missing", "X"))
            # delete ok
            self.assertTrue(pm.delete_prompt("Name"))
            # delete missing
            self.assertFalse(pm.delete_prompt("Name"))

    def test_import_export_prompts(self):
        utils.PromptManager._instance = None
        with patch("app.utils.os.path.exists", return_value=False):
            pm = utils.PromptManager.instance()
        # import success merge
        with patch("app.utils.open", create=True), \
            patch("app.utils.json.load", return_value={"imp": {"text": "t", "category": "I"}}), \
            patch.object(pm, "_save_prompts") as _sv:
            pm.prompts_changed = types.SimpleNamespace(emit=MagicMock())
            ok, msg = pm.import_prompts_from_file("/file.json", merge=True)
            self.assertTrue(ok)
            self.assertIn("success", msg.lower())
        # import replace
        with patch("app.utils.open", create=True), \
            patch("app.utils.json.load", return_value={"imp": "t"}), \
            patch.object(pm, "_save_prompts") as _sv:
            pm.prompts_changed = types.SimpleNamespace(emit=MagicMock())
            ok, _ = pm.import_prompts_from_file("/file.json", merge=False)
            self.assertTrue(ok)
        # import invalid json
        with patch("app.utils.open", create=True), \
            patch("app.utils.json.load", side_effect=json.JSONDecodeError("x", "{}", 0)):
            ok, msg = pm.import_prompts_from_file("/file.json")
            self.assertFalse(ok)
            self.assertIn("invalid json", msg.lower())
        # export success
        with patch("app.utils.os.makedirs"), \
            patch("app.utils.open", create=True), \
            patch("app.utils.json.dump") as jdump:
            ok, msg = pm.export_prompts_to_file("/out.json")
            self.assertTrue(ok)
            self.assertIn("exported", msg.lower())
            # indent formatting check
            self.assertIn("indent", jdump.call_args.kwargs)
        # export failure
        with patch("app.utils.open", side_effect=IOError("x")):
            ok, msg = pm.export_prompts_to_file("/out.json")
            self.assertFalse(ok)
            self.assertIn("failed", msg.lower())


if __name__ == "__main__":
    unittest.main()
