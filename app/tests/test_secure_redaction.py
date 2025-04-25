import unittest
import sys
import os
import logging
from unittest.mock import patch, MagicMock

# Add repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.secure import redact, SensitiveLogFilter, get_service_id


class TestSecureRedaction(unittest.TestCase):
    """Redaction/filter unit-tests."""

    def test_redact_openai_key(self):
        txt = "My API key is sk-abcdefghijklmnopqrstuvwxyz1234567890"
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", redact(txt))
        self.assertIn("***-REDACTED-***", redact(txt))

    def test_redact_hf_token(self):
        txt = "My HF token is hf_abcdefghijklmnopqrstuvwxyz1234567890"
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz1234567890", redact(txt))
        self.assertIn("***-REDACTED-***", redact(txt))

    def test_redact_multiple(self):
        txt = "sk-abcdefghijklmnopqrstuvwxyz1234567890 hf_abcdefghijklmnopqrstuvwxyz1234567890"
        red = redact(txt)
        self.assertEqual(red.count("***-REDACTED-***"), 2)

    def test_redact_empty(self):
        self.assertEqual(redact(""), "")
        self.assertEqual(redact(None), "")

    def test_log_filter(self):
        filt = SensitiveLogFilter()
        rec = logging.LogRecord("x", logging.INFO, "t.py", 1,
                                "sk-abcdefghijklmnopqrstuvwxyz1234567890", (), None)
        filt.filter(rec)
        self.assertIn("***-REDACTED-***", rec.msg)

    def test_log_filter_args(self):
        filt = SensitiveLogFilter()
        rec = logging.LogRecord("x", logging.INFO, "t.py", 1,
                                "Key: %s", ("sk-abcdefghijklmnopqrstuvwxyz1234567890",), None)
        filt.filter(rec)
        self.assertIn("***-REDACTED-***", rec.args[0])

    def test_service_id(self):
        from app.constants import APP_NAME, APP_VERSION
        self.assertEqual(get_service_id(), f"{APP_NAME.lower()}-v{APP_VERSION}")


class TestSecureHTTPS(unittest.TestCase):
    """HTTPS enforcement tests."""

    @patch("requests.Session.send")
    def test_https_validation_for_openai(self, mock_send):
        from app.threads.GPT4ProcessingThread import GPT4ProcessingThread

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_send.return_value = mock_resp

        t = GPT4ProcessingThread("T", "P", "gpt-4o", 100, 0.7, "sk-test")

        # HTTP – should fail
        with patch.object(t, "API_ENDPOINT", "http://api.openai.com/v1/chat/completions"):
            with self.assertRaises(ValueError):
                t._send_api_request([{"role": "user", "content": "x"}])

        # HTTPS – should succeed
        with patch.object(t, "API_ENDPOINT", "https://api.openai.com/v1/chat/completions"):
            t._send_api_request([{"role": "user", "content": "x"}])

    @patch("app.services.transcription_service.OpenAI")     # <- correct symbol
    def test_https_validation_for_whisper(self, mock_openai):
        from app.services.transcription_service import TranscriptionService

        mock_cli = MagicMock()
        mock_openai.return_value = mock_cli
        mock_resp = MagicMock()
        mock_resp.text = "demo"
        mock_cli.audio.transcriptions.create.return_value = mock_resp

        svc = TranscriptionService()

        # HTTP – expect failure
        with self.assertRaises(ValueError):
            svc._transcribe_with_api("http://api.openai.com", "en", "sk-test")

        # HTTPS – expect success
        res = svc._transcribe_with_api("https://api.openai.com", "en", "sk-test")
        self.assertEqual(res["text"], "demo")


if __name__ == "__main__":
    unittest.main()
