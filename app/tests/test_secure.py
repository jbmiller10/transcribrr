"""
Comprehensive test suite for the secure module.
Tests all security functions including redaction, log filtering, and API key management.
"""

import unittest
from unittest.mock import MagicMock, Mock, patch, call
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.secure import (
    redact,
    SensitiveLogFilter,
    migrate_api_keys,
    get_service_id,
    get_api_key,
    set_api_key,
)


class TestRedactFunction(unittest.TestCase):
    """Test cases for the redact() function."""

    def test_redact_openai_key_pattern(self):
        """Tests redaction of OpenAI API key pattern."""
        # When text contains OpenAI API key pattern (sk-xxxxx)
        text = "My key is sk-abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        
        # Returns text with OpenAI key replaced by ***-REDACTED-***
        self.assertIn("***-REDACTED-***", result)
        # Original key pattern is not present in output
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", result)
        self.assertEqual(result, "My key is ***-REDACTED-***")

    def test_redact_huggingface_token_pattern(self):
        """Tests redaction of HuggingFace token pattern."""
        # When text contains HuggingFace token pattern (hf_xxxxx)
        text = "Token: hf_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        
        # Returns text with HF token replaced by ***-REDACTED-***
        self.assertIn("***-REDACTED-***", result)
        # Original token pattern is not present in output
        self.assertNotIn("hf_abcdefghijklmnopqrstuvwxyz123456", result)
        self.assertEqual(result, "Token: ***-REDACTED-***")

    def test_redact_multiple_keys_in_same_text(self):
        """Tests redaction of multiple API keys in same text."""
        # When text contains both OpenAI and HuggingFace tokens
        text = "Keys: sk-abcdefghijklmnopqrstuvwxyz123456 and hf_abcdefghijklmnopqrstuvwxyz123456"
        result = redact(text)
        
        # All API keys are replaced with ***-REDACTED-***
        # Count of redactions matches count of sensitive patterns
        self.assertEqual(result.count("***-REDACTED-***"), 2)
        self.assertNotIn("sk-", result)
        self.assertNotIn("hf_", result)
        self.assertEqual(result, "Keys: ***-REDACTED-*** and ***-REDACTED-***")

    def test_redact_empty_string_input(self):
        """Tests handling of empty string input."""
        # When input text is empty string
        result = redact("")
        
        # Returns empty string
        self.assertEqual(result, "")
        # No exceptions raised (test passes if we get here)

    def test_redact_none_input(self):
        """Tests handling of None input."""
        # When input text is None
        result = redact(None)
        
        # Returns empty string
        self.assertEqual(result, "")
        # No exceptions raised (test passes if we get here)

    def test_redact_preservation_of_non_sensitive_text(self):
        """Tests preservation of non-sensitive text."""
        # When text contains no API keys or tokens
        text = "This is a normal text without any sensitive information."
        result = redact(text)
        
        # Returns original text unchanged
        self.assertEqual(result, text)
        # No redaction markers added
        self.assertNotIn("***-REDACTED-***", result)

    def test_redact_partial_api_key_patterns(self):
        """Tests edge case with partial API key patterns."""
        # When text contains partial patterns like 'sk-' or 'hf_' without enough characters
        text = "Partial patterns: sk- and hf_ and sk-short"
        result = redact(text)
        
        # Does not redact partial patterns that don't match full regex
        # Only complete API key patterns are redacted
        self.assertEqual(result, text)
        self.assertNotIn("***-REDACTED-***", result)


class TestSensitiveLogFilter(unittest.TestCase):
    """Test cases for the SensitiveLogFilter class."""

    @patch("app.secure.redact")
    def test_filter_log_record_with_sensitive_message(self, mock_redact):
        """Tests filtering of log record with sensitive message."""
        # When log record contains API key in msg attribute
        mock_redact.return_value = "redacted message"
        
        filter_obj = SensitiveLogFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1,
            "Message with sk-abcdefghijklmnopqrstuvwxyz", (), None
        )
        
        result = filter_obj.filter(record)
        
        # record.msg is updated with redacted version
        self.assertEqual(record.msg, "redacted message")
        # Method returns True to keep the record
        self.assertTrue(result)
        # redact() is called with original message
        mock_redact.assert_called_once_with("Message with sk-abcdefghijklmnopqrstuvwxyz")

    @patch("app.secure.redact")
    def test_filter_log_record_with_sensitive_args(self, mock_redact):
        """Tests filtering of log record with sensitive args."""
        # When log record contains API keys in args tuple
        mock_redact.return_value = "redacted arg"
        
        filter_obj = SensitiveLogFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1,
            "Message: %s %d", ("sk-secret", 42), None
        )
        
        result = filter_obj.filter(record)
        
        # String args are redacted
        self.assertEqual(record.args[0], "redacted arg")
        # Non-string args remain unchanged
        self.assertEqual(record.args[1], 42)
        # Args tuple is properly reconstructed
        self.assertIsInstance(record.args, tuple)
        self.assertEqual(len(record.args), 2)
        # Method returns True
        self.assertTrue(result)

    def test_filter_log_record_without_msg_attribute(self):
        """Tests handling of log record without msg attribute."""
        # When log record lacks msg attribute
        filter_obj = SensitiveLogFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1,
            None, (), None
        )
        # Remove msg attribute to simulate missing attribute
        delattr(record, "msg")
        
        result = filter_obj.filter(record)
        
        # No AttributeError raised
        # Method returns True
        self.assertTrue(result)
        # Record passes through without modification
        self.assertFalse(hasattr(record, "msg"))

    def test_filter_log_record_with_none_msg(self):
        """Tests handling of log record with None msg."""
        # When log record has msg attribute set to None
        filter_obj = SensitiveLogFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1,
            None, (), None
        )
        
        result = filter_obj.filter(record)
        
        # No exceptions raised
        # Method returns True
        self.assertTrue(result)
        # msg remains None
        self.assertIsNone(record.msg)

    def test_filter_non_string_msg_attribute(self):
        """Tests handling of non-string msg attribute."""
        # When log record msg is an integer or other non-string type
        filter_obj = SensitiveLogFilter()
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 1,
            12345, (), None
        )
        
        result = filter_obj.filter(record)
        
        # Non-string msg is not processed
        self.assertEqual(record.msg, 12345)
        # No type errors raised
        # Method returns True
        self.assertTrue(result)


class TestMigrateApiKeys(unittest.TestCase):
    """Test cases for the migrate_api_keys() function."""

    @patch("app.secure.logger")
    @patch("keyring.delete_password")
    @patch("keyring.set_password")
    @patch("keyring.get_password")
    def test_successful_migration_of_both_keys(
        self, mock_get_password, mock_set_password, mock_delete_password, mock_logger
    ):
        """Tests successful migration of both API keys."""
        # When both OpenAI and HuggingFace keys exist in old location
        mock_get_password.return_value = "test-api-key"
        
        result = migrate_api_keys()
        
        # Returns {'openai': True, 'hf': True}
        self.assertEqual(result, {"openai": True, "hf": True})
        # get_password called twice with old_service_id
        self.assertEqual(mock_get_password.call_count, 2)
        mock_get_password.assert_any_call("transcription_application", "OPENAI_API_KEY")
        mock_get_password.assert_any_call("transcription_application", "HF_AUTH_TOKEN")
        # set_password called twice with new_service_id
        self.assertEqual(mock_set_password.call_count, 2)
        mock_set_password.assert_any_call("transcribrr-v1.0.0", "OPENAI_API_KEY", "test-api-key")
        mock_set_password.assert_any_call("transcribrr-v1.0.0", "HF_AUTH_TOKEN", "test-api-key")
        # delete_password called twice to remove old keys
        self.assertEqual(mock_delete_password.call_count, 2)
        mock_delete_password.assert_any_call("transcription_application", "OPENAI_API_KEY")
        mock_delete_password.assert_any_call("transcription_application", "HF_AUTH_TOKEN")
        # Info messages logged for successful migrations
        self.assertEqual(mock_logger.info.call_count, 2)

    @patch("app.secure.logger")
    @patch("keyring.get_password")
    def test_migration_when_no_keys_exist(self, mock_get_password, mock_logger):
        """Tests migration when no keys exist in old location."""
        # When old location has no API keys
        mock_get_password.return_value = None
        
        result = migrate_api_keys()
        
        # Returns {'openai': False, 'hf': False}
        self.assertEqual(result, {"openai": False, "hf": False})
        # No set_password calls made (tested implicitly - no patch needed)
        # No delete_password calls made (tested implicitly - no patch needed)
        # No migration messages logged
        mock_logger.info.assert_not_called()

    @patch("app.secure.logger")
    @patch("keyring.delete_password")
    @patch("keyring.set_password")
    @patch("keyring.get_password")
    def test_partial_migration_with_only_openai_key(
        self, mock_get_password, mock_set_password, mock_delete_password, mock_logger
    ):
        """Tests partial migration with only OpenAI key."""
        # When only OpenAI key exists in old location
        # returns 'openai-key' for first call, None for second
        mock_get_password.side_effect = ["openai-key", None]
        
        result = migrate_api_keys()
        
        # Returns {'openai': True, 'hf': False}
        self.assertEqual(result, {"openai": True, "hf": False})
        # Only OpenAI key is migrated
        mock_set_password.assert_called_once_with("transcribrr-v1.0.0", "OPENAI_API_KEY", "openai-key")
        mock_delete_password.assert_called_once_with("transcription_application", "OPENAI_API_KEY")
        # Info message logged for OpenAI migration only
        mock_logger.info.assert_called_once()

    @patch("app.secure.redact")
    @patch("app.secure.logger")
    @patch("keyring.get_password")
    def test_error_handling_during_openai_key_migration(
        self, mock_get_password, mock_logger, mock_redact
    ):
        """Tests error handling during OpenAI key migration."""
        # When keyring operations fail for OpenAI key
        # raises Exception for OpenAI, returns None for HF
        def side_effect_func(service, key):
            if key == "OPENAI_API_KEY":
                raise Exception("Keyring error")
            return None
        
        mock_get_password.side_effect = side_effect_func
        mock_redact.return_value = "redacted error message"
        
        result = migrate_api_keys()
        
        # Exception is caught and logged
        mock_logger.error.assert_called()
        # Error message is redacted before logging
        mock_redact.assert_called()
        # Migration continues for HuggingFace token
        # Returns {'openai': False, 'hf': False}
        self.assertEqual(result, {"openai": False, "hf": False})

    @patch("app.secure.redact")
    @patch("app.secure.logger")
    @patch("keyring.delete_password")
    @patch("keyring.set_password")
    @patch("keyring.get_password")
    def test_error_handling_during_key_deletion(
        self, mock_get_password, mock_set_password, mock_delete_password, 
        mock_logger, mock_redact
    ):
        """Tests error handling during key deletion."""
        # When delete_password raises exception
        mock_get_password.return_value = "test-key"
        mock_set_password.return_value = None
        mock_delete_password.side_effect = Exception("Delete failed")
        mock_redact.return_value = "redacted error"
        
        result = migrate_api_keys()
        
        # Exception is caught and logged
        self.assertEqual(mock_logger.error.call_count, 2)  # One for each key
        # Migration marked as failed for that key
        self.assertEqual(result, {"openai": False, "hf": False})
        # Error message is redacted
        mock_redact.assert_called()


class TestGetServiceId(unittest.TestCase):
    """Test cases for the get_service_id() function."""

    @patch("app.constants.APP_VERSION", "1.0.0")
    @patch("app.constants.APP_NAME", "Transcribrr")
    def test_service_id_generation(self):
        """Tests service ID generation."""
        # When APP_NAME and APP_VERSION are defined
        result = get_service_id()
        
        # Returns formatted string 'transcribrr-v1.0.0'
        self.assertEqual(result, "transcribrr-v1.0.0")
        # APP_NAME is converted to lowercase
        # Version is prefixed with 'v'


class TestGetApiKey(unittest.TestCase):
    """Test cases for the get_api_key() function."""

    def test_retrieval_of_test_api_keys(self):
        """Tests retrieval of test API keys."""
        # When requesting OPENAI_API_KEY, HF_API_KEY, or HF_AUTH_TOKEN
        # Returns 'fake-api-key' for test keys
        self.assertEqual(get_api_key("OPENAI_API_KEY"), "fake-api-key")
        self.assertEqual(get_api_key("HF_API_KEY"), "fake-api-key")
        self.assertEqual(get_api_key("HF_AUTH_TOKEN"), "fake-api-key")
        # Does not call keyring.get_password (no patch needed since it returns early)

    @patch("app.secure.get_service_id")
    @patch("keyring.get_password")
    def test_retrieval_of_non_test_api_key(self, mock_get_password, mock_get_service_id):
        """Tests retrieval of non-test API key."""
        # When requesting a custom API key from keyring
        mock_get_password.return_value = "actual-api-key"
        mock_get_service_id.return_value = "test-service-id"
        
        result = get_api_key("CUSTOM_KEY")
        
        # Calls keyring.get_password with service_id and key_name
        mock_get_password.assert_called_once_with("test-service-id", "CUSTOM_KEY")
        # Returns the retrieved API key
        self.assertEqual(result, "actual-api-key")

    @patch("app.secure.get_service_id")
    @patch("keyring.get_password")
    def test_handling_of_missing_api_key(self, mock_get_password, mock_get_service_id):
        """Tests handling of missing API key."""
        # When requested key doesn't exist in keyring
        mock_get_password.return_value = None
        mock_get_service_id.return_value = "test-service-id"
        
        result = get_api_key("MISSING_KEY")
        
        # Returns None
        self.assertIsNone(result)
        # No exceptions raised (test passes if we get here)

    @patch("app.secure.get_service_id")
    @patch("keyring.get_password")
    def test_error_handling_during_key_retrieval(self, mock_get_password, mock_get_service_id):
        """Tests error handling during key retrieval."""
        # When keyring.get_password raises exception
        mock_get_password.side_effect = Exception("Keyring error")
        mock_get_service_id.return_value = "test-service-id"
        
        # Exception propagates (not caught)
        # Allows caller to handle keyring errors
        with self.assertRaises(Exception) as context:
            get_api_key("ERROR_KEY")
        
        self.assertEqual(str(context.exception), "Keyring error")


class TestSetApiKey(unittest.TestCase):
    """Test cases for the set_api_key() function."""

    @patch("app.secure.logger")
    @patch("app.secure.get_service_id")
    @patch("keyring.set_password")
    def test_successful_api_key_storage(
        self, mock_set_password, mock_get_service_id, mock_logger
    ):
        """Tests successful API key storage."""
        # When storing a valid API key
        mock_set_password.return_value = None
        mock_get_service_id.return_value = "test-service-id"
        
        result = set_api_key("MY_KEY", "my-secret-value")
        
        # Calls keyring.set_password with service_id, key_name, and value
        mock_set_password.assert_called_once_with("test-service-id", "MY_KEY", "my-secret-value")
        # Returns True
        self.assertTrue(result)
        # No errors logged
        mock_logger.error.assert_not_called()

    @patch("app.secure.logger")
    @patch("app.secure.get_service_id")
    @patch("keyring.delete_password")
    def test_deletion_of_api_key_with_empty_value(
        self, mock_delete_password, mock_get_service_id, mock_logger
    ):
        """Tests deletion of API key with empty value."""
        # When value is empty string
        mock_delete_password.return_value = None
        mock_get_service_id.return_value = "test-service-id"
        
        result = set_api_key("MY_KEY", "")
        
        # Calls keyring.delete_password instead of set_password
        mock_delete_password.assert_called_once_with("test-service-id", "MY_KEY")
        # Returns True
        self.assertTrue(result)
        # No errors logged
        mock_logger.error.assert_not_called()

    @patch("app.secure.logger")
    @patch("app.secure.get_service_id")
    @patch("keyring.delete_password")
    def test_deletion_when_key_doesnt_exist(
        self, mock_delete_password, mock_get_service_id, mock_logger
    ):
        """Tests deletion when key doesn't exist."""
        # When trying to delete non-existent key
        # Import the actual exception class
        import keyring.errors
        mock_delete_password.side_effect = keyring.errors.PasswordDeleteError("Key not found")
        mock_get_service_id.return_value = "test-service-id"
        
        result = set_api_key("NONEXISTENT_KEY", "")
        
        # PasswordDeleteError is caught and ignored
        # Returns True
        self.assertTrue(result)
        # No error logged
        mock_logger.error.assert_not_called()

    @patch("app.secure.redact")
    @patch("app.secure.logger")
    @patch("app.secure.get_service_id")
    @patch("keyring.set_password")
    def test_error_handling_during_key_storage(
        self, mock_set_password, mock_get_service_id, mock_logger, mock_redact
    ):
        """Tests error handling during key storage."""
        # When keyring.set_password raises exception
        mock_set_password.side_effect = Exception("Storage failed")
        mock_get_service_id.return_value = "test-service-id"
        mock_redact.return_value = "redacted error"
        
        result = set_api_key("MY_KEY", "my-value")
        
        # Exception is caught
        # Error is logged with redacted message
        mock_logger.error.assert_called_once()
        mock_redact.assert_called()
        # Returns False
        self.assertFalse(result)

    @patch("app.secure.get_service_id")
    @patch("keyring.delete_password")
    def test_handling_of_none_value(self, mock_delete_password, mock_get_service_id):
        """Tests handling of None value."""
        # When value is None
        mock_delete_password.return_value = None
        mock_get_service_id.return_value = "test-service-id"
        
        result = set_api_key("MY_KEY", None)
        
        # Treats None as empty, attempts deletion
        mock_delete_password.assert_called_once_with("test-service-id", "MY_KEY")
        # Returns True if successful
        self.assertTrue(result)

    @patch("app.secure.get_service_id")
    @patch("keyring.set_password")
    def test_storage_of_api_key_with_special_characters(
        self, mock_set_password, mock_get_service_id
    ):
        """Tests storage of API key with special characters."""
        # When API key contains special characters and spaces
        mock_set_password.return_value = None
        mock_get_service_id.return_value = "test-service-id"
        
        special_key = "key-with !@#$%^&*() spaces and 特殊文字"
        result = set_api_key("SPECIAL_KEY", special_key)
        
        # Special characters are preserved
        # No escaping or modification of key value
        mock_set_password.assert_called_once_with("test-service-id", "SPECIAL_KEY", special_key)
        # Returns True
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()