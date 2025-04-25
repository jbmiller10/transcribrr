"""
Unit-tests covering redaction utilities and HTTPS enforcement.
"""

import logging
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
)

from app.secure import SensitiveLogFilter, get_service_id, redact


# ───────────────────────── redaction ────────────────────────
class TestSecureRedaction(unittest.TestCase):
    def test_redact_openai(self):
        raw = "sk-abcdefghijklmnopqrstuvwxyz123456"
        self.assertIn("***-REDACTED-***", redact(raw))

    def test_redact_hf(self):
        raw = "hf_abcdefghijklmnopqrstuvwxyz123456"
        self.assertIn("***-REDACTED-***", redact(raw))

    def test_redact_multiple(self):
        raw = (
            "OpenAI sk-abcdefghijklmnopqrstuvwxyz123456 "
            "HF hf_abcdefghijklmnopqrstuvwxyz123456"
        )
        self.assertEqual(redact(raw).count("***-REDACTED-***"), 2)

    def test_log_filter(self):
        filt = SensitiveLogFilter()
        rec = logging.LogRecord(
            "x", logging.INFO, "t.py", 1, "sk-abcdefghijklmnopqrstuvwxyz123456", (), None
        )
        filt.filter(rec)
        self.assertIn("***-REDACTED-***", rec.msg)

    def test_service_id(self):
        from app.constants import APP_NAME, APP_VERSION

        self.assertEqual(get_service_id(), f"{APP_NAME.lower()}-v{APP_VERSION}")


# ───────────────────────── HTTPS tests ──────────────────────
class TestSecureHTTPS(unittest.TestCase):
    @patch("requests.Session.send")
    def test_openai_https_guard(self, mock_send):
        from app.threads.GPT4ProcessingThread import GPT4ProcessingThread

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_send.return_value = mock_resp

        worker = GPT4ProcessingThread("T", "P", "gpt-4o", 64, 0.7, "sk")
        # HTTP → must fail
        worker.API_ENDPOINT = "http://api.openai.com/v1/chat/completions"
        with self.assertRaises(ValueError):
            worker._send_api_request([{"role": "user", "content": "x"}])

        # HTTPS → succeeds
        worker.API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
        worker._send_api_request([{"role": "user", "content": "x"}])

    @patch("app.services.transcription_service.OpenAI")
    def test_whisper_https_guard(self, mock_openai):
        from app.services.transcription_service import TranscriptionService

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tmp.write(b"\0\0")
        tmp.close()

        cli = MagicMock()
        mock_openai.return_value = cli
        mock_rsp = MagicMock()
        mock_rsp.text = "demo"
        cli.audio.transcriptions.create.return_value = mock_rsp

        svc = TranscriptionService()

        with self.assertRaises(ValueError):
            svc._transcribe_with_api(
                tmp.name, "en", "sk-test", base_url="http://api.openai.com/v1"
            )

        out = svc._transcribe_with_api(
            tmp.name, "en", "sk-test", base_url="https://api.openai.com/v1"
        )
        self.assertEqual(out["text"], "demo")
        os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
