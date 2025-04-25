# app/tests/test_secure_redaction.py
import unittest
import sys
import os
import logging
import tempfile
import requests
from unittest.mock import patch, MagicMock, mock_open

# Add the parent directory to the path to import app modules
# Ensure this path adjustment is correct for your structure
if os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')) not in sys.path:
     sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


from app.secure import redact, SensitiveLogFilter, get_service_id
# Import the class needed for patching
from app.threads.GPT4ProcessingThread import GPT4ProcessingThread
# Import OpenAI for the whisper test mocking
from openai import OpenAI

class TestSecureRedaction(unittest.TestCase):
    """Test secure redaction functionality."""

    def test_redact_openai_key(self):
        """Test that OpenAI API keys are redacted."""
        text = "My API key is sk-abcdefghijklmnopqrstuvwxyz1234567890"
        redacted = redact(text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", redacted)
        self.assertIn("***-REDACTED-***", redacted)

    def test_redact_hf_token(self):
        """Test that HuggingFace tokens are redacted."""
        text = "My HF token is hf_abcdefghijklmnopqrstuvwxyz1234567890"
        redacted = redact(text)
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz1234567890", redacted)
        self.assertIn("***-REDACTED-***", redacted)

    def test_redact_multiple_keys(self):
        """Test that multiple keys are redacted."""
        text = """
        OpenAI: sk-abcdefghijklmnopqrstuvwxyz1234567890
        HuggingFace: hf_abcdefghijklmnopqrstuvwxyz1234567890
        """
        redacted = redact(text)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", redacted)
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz1234567890", redacted)
        self.assertEqual(redacted.count("***-REDACTED-***"), 2)

    def test_redact_empty_text(self):
        """Test that empty text is handled gracefully."""
        self.assertEqual(redact(""), "")
        # Assuming redact handles None gracefully, otherwise adjust test or function
        # self.assertEqual(redact(None), "") # Depending on desired behavior for None

    def test_log_filter(self):
        """Test that the log filter redacts sensitive information."""
        log_filter = SensitiveLogFilter()

        # Create a log record with sensitive information
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="API key: sk-abcdefghijklmnopqrstuvwxyz1234567890",
            args=(),
            exc_info=None,
            func="test_func" # Add func attribute
        )

        # Apply the filter
        log_filter.filter(record)

        # Check that the message was redacted
        # Use getMessage() to ensure formatting is applied if args were involved
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", record.getMessage())
        self.assertIn("***-REDACTED-***", record.getMessage())


    def test_log_filter_with_args(self):
        """Test that the log filter redacts sensitive information in args."""
        log_filter = SensitiveLogFilter()

        # Create a log record with sensitive information in args
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="API key: %s",
            args=("sk-abcdefghijklmnopqrstuvwxyz1234567890",),
            exc_info=None,
            func="test_func" # Add func attribute
        )


        # Apply the filter (it modifies record.args in place)
        log_filter.filter(record)

        # Check that the args were redacted (access the modified record.args)
        # Note: record.args *itself* is modified by the filter
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", record.args[0])
        self.assertIn("***-REDACTED-***", record.args[0])

        # Also check the formatted message
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz1234567890", record.getMessage())
        self.assertIn("***-REDACTED-***", record.getMessage())

    def test_service_id_versioning(self):
        """Test that the service ID includes the app version."""
        # Need to import constants within the test if not globally available
        from app.constants import APP_NAME, APP_VERSION

        service_id = get_service_id()
        self.assertIn(APP_NAME.lower(), service_id)
        self.assertIn(APP_VERSION, service_id)
        self.assertEqual(service_id, f"{APP_NAME.lower()}-v{APP_VERSION}")


class TestSecureHTTPS(unittest.TestCase):
    """Test HTTPS validation."""

    @patch('requests.Session.send')
    def test_https_validation_for_openai(self, mock_send):
        """Test that GPT4ProcessingThread uses HTTPS for OpenAI API calls."""
        # Mocking setup
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Test response"}}]}
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_send.return_value = mock_response

        # Create thread instance
        thread = GPT4ProcessingThread(
            transcript="Test", prompt_instructions="Test", gpt_model="gpt-4o",
            max_tokens=100, temperature=0.7, openai_api_key="sk-test"
        )

        # --- Test HTTP case (expecting ValueError) ---
        # Patch the class attribute API_ENDPOINT to force HTTP
        with patch.object(GPT4ProcessingThread, 'API_ENDPOINT', 'http://api.openai.com/v1/chat/completions'):
            # Use assertRaises(Exception) as the exact error might vary
            with self.assertRaises(Exception) as context:
                thread._send_api_request([{"role": "user", "content": "test"}])
            # Check if the raised exception's message contains "HTTPS"
            self.assertIn("HTTPS", str(context.exception), "Exception message should mention HTTPS requirement")

        # --- Test HTTPS case (expecting success) ---
        # Patch the class attribute API_ENDPOINT back to HTTPS (or rely on default)
        with patch.object(GPT4ProcessingThread, 'API_ENDPOINT', 'https://api.openai.com/v1/chat/completions'):
            try:
                # This call should now succeed without raising the ValueError
                thread._send_api_request([{"role": "user", "content": "test"}])
                # Verify the mock was called (optional, but good practice)
                mock_send.assert_called()
            except Exception as e:
                self.fail(f"HTTPS call unexpectedly raised an exception: {e}")


    # --- Reverted test_https_validation_for_whisper ---
    @patch('app.services.transcription_service.OpenAI') # Patch where it's imported
    def test_https_validation_for_whisper(self, mock_openai_constructor):
        """Test that TranscriptionService uses HTTPS for Whisper API calls."""
        from app.services.transcription_service import TranscriptionService

        # Mocking setup
        mock_client = MagicMock()
        mock_transcription_result = MagicMock()
        mock_transcription_result.text = "Test transcription"
        mock_client.audio.transcriptions.create.return_value = mock_transcription_result
        mock_openai_constructor.return_value = mock_client

        # Create a TranscriptionService
        service = TranscriptionService()

        # Test the call within a temporary file context
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp_file:
            # Call the method under test
            service._transcribe_with_api(tmp_file.name, "en", "sk-test")

            # Assertions after the call
            mock_openai_constructor.assert_called_once()
            call_args, call_kwargs = mock_openai_constructor.call_args

            # Check that base_url starts with https
            self.assertIn('base_url', call_kwargs, "base_url missing from OpenAI constructor call")
            self.assertTrue(
                call_kwargs['base_url'].startswith("https://"),
                f"Expected base_url to start with https, but got: {call_kwargs['base_url']}"
            )
            # Check API key
            self.assertIn('api_key', call_kwargs, "api_key missing from OpenAI constructor call")
            self.assertEqual(call_kwargs['api_key'], "sk-test")
    # --- End Reverted test ---


if __name__ == '__main__':
    unittest.main()
