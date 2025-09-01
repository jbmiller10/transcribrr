"""
Unit tests for authentication and API key management functionality.

Tests the secure storage, retrieval, and migration of API keys,
as well as the redaction of sensitive information in logs.
"""

import unittest
from unittest.mock import patch, MagicMock, call, Mock
import logging
from typing import Optional
import sys

# Create a fake PasswordDeleteError exception class
class FakePasswordDeleteError(Exception):
    pass

# Mock keyring module before importing secure module
keyring_mock = Mock()
keyring_errors_mock = Mock()
keyring_errors_mock.PasswordDeleteError = FakePasswordDeleteError

sys.modules['keyring'] = keyring_mock
sys.modules['keyring.errors'] = keyring_errors_mock

# Import keyring explicitly to reference it properly
import keyring
import keyring.errors

# Now import from secure module which will use our mocked keyring
from app.secure import (
    redact,
    SensitiveLogFilter,
    migrate_api_keys,
    get_service_id,
    get_api_key,
    set_api_key,
    REDACTED_TEXT
)


class TestRedaction(unittest.TestCase):
    """Test sensitive information redaction functionality."""
    
    def test_redact_openai_key(self):
        """Test that OpenAI API keys are properly redacted."""
        text = "My key is sk-abc123def456ghi789"
        result = redact(text)
        self.assertEqual(result, f"My key is {REDACTED_TEXT}")
        self.assertNotIn("sk-abc123def456ghi789", result)
    
    def test_redact_huggingface_token(self):
        """Test that HuggingFace tokens are properly redacted."""
        text = "Token: hf_abcdefghij1234567890"
        result = redact(text)
        self.assertEqual(result, f"Token: {REDACTED_TEXT}")
        self.assertNotIn("hf_abcdefghij1234567890", result)
    
    def test_redact_multiple_keys(self):
        """Test that multiple keys in the same text are all redacted."""
        text = "OpenAI: sk-test123456 and HF: hf_test789012"
        result = redact(text)
        self.assertEqual(result, f"OpenAI: {REDACTED_TEXT} and HF: {REDACTED_TEXT}")
        self.assertNotIn("sk-test123456", result)
        self.assertNotIn("hf_test789012", result)
    
    def test_redact_empty_string(self):
        """Test that empty strings are handled correctly."""
        result = redact("")
        self.assertEqual(result, "")
    
    def test_redact_none_input(self):
        """Test that None input is handled correctly."""
        result = redact(None)
        self.assertEqual(result, "")
    
    def test_redact_preserves_non_sensitive_text(self):
        """Test that non-sensitive text is preserved unchanged."""
        text = "This is normal text without any API keys"
        result = redact(text)
        self.assertEqual(result, text)


class TestSensitiveLogFilter(unittest.TestCase):
    """Test the logging filter for sensitive information."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.filter = SensitiveLogFilter()
        self.logger = logging.getLogger("test_logger")
    
    def test_filter_redacts_message_with_api_key(self):
        """Test that API keys in log messages are redacted."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Using API key: sk-secretkey123456",
            args=(),
            exc_info=None
        )
        
        result = self.filter.filter(record)
        self.assertTrue(result)  # Filter should always return True
        self.assertEqual(record.msg, f"Using API key: {REDACTED_TEXT}")
        self.assertNotIn("sk-secretkey123456", record.msg)
    
    def test_filter_redacts_args_with_api_keys(self):
        """Test that API keys in log arguments are redacted."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Key: %s, Status: %s",
            args=("sk-secret789abcdef", "Active"),  # API key must have 10+ chars after prefix
            exc_info=None
        )
        
        result = self.filter.filter(record)
        self.assertTrue(result)
        self.assertEqual(record.args[0], REDACTED_TEXT)
        self.assertEqual(record.args[1], "Active")  # Non-sensitive arg unchanged
        self.assertNotIn("sk-secret789abcdef", record.args[0])
    
    def test_filter_handles_non_string_args(self):
        """Test that non-string arguments are handled correctly."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Count: %d, Key: %s",
            args=(42, "hf_token1234567890"),  # HF token must have 10+ chars after prefix
            exc_info=None
        )
        
        result = self.filter.filter(record)
        self.assertTrue(result)
        self.assertEqual(record.args[0], 42)  # Integer unchanged
        self.assertEqual(record.args[1], REDACTED_TEXT)
    
    def test_filter_handles_missing_attributes(self):
        """Test that records without msg or args attributes are handled."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=None,
            args=None,
            exc_info=None
        )
        
        result = self.filter.filter(record)
        self.assertTrue(result)  # Should not crash and should return True


class TestKeyMigration(unittest.TestCase):
    """Test API key migration functionality."""
    
    @patch('app.secure.logger')
    def test_migrate_both_keys_successfully(self, mock_logger):
        """Test successful migration of both OpenAI and HuggingFace keys."""
        with patch('keyring.get_password') as mock_get, \
             patch('keyring.set_password') as mock_set, \
             patch('keyring.delete_password') as mock_delete:
            # Setup mock responses
            mock_get.side_effect = [
            "sk-oldkey123",  # OpenAI key in old location
            "hf_oldtoken456"  # HF token in old location
            ]
            
            result = migrate_api_keys()
            
            # Verify both keys were migrated
            self.assertTrue(result["openai"])
            self.assertTrue(result["hf"])
            
            # Verify get_password was called for both keys
            self.assertEqual(mock_get.call_count, 2)
            
            # Verify set_password was called for both keys with new service ID
            self.assertEqual(mock_set.call_count, 2)
            
            # Verify delete_password was called for both old keys
            self.assertEqual(mock_delete.call_count, 2)
            
            # Verify success was logged
            self.assertEqual(mock_logger.info.call_count, 2)
    
    @patch('app.secure.logger')
    def test_migrate_no_keys_found(self, mock_logger):
        """Test migration when no keys are found in old location."""
        with patch('keyring.get_password', return_value=None) as mock_get, \
             patch('keyring.set_password') as mock_set, \
             patch('keyring.delete_password') as mock_delete:
            
            result = migrate_api_keys()
            
            # Verify no keys were migrated
            self.assertFalse(result["openai"])
            self.assertFalse(result["hf"])
            
            # Verify set_password was never called
            mock_set.assert_not_called()
            
            # Verify delete_password was never called
            mock_delete.assert_not_called()
    
    @patch('app.secure.logger')
    def test_migrate_handles_errors_gracefully(self, mock_logger):
        """Test that migration errors are handled and logged properly."""
        with patch('keyring.get_password', side_effect=Exception("Keyring error")):
            
            result = migrate_api_keys()
            
            # Verify migration failed for both
            self.assertFalse(result["openai"])
            self.assertFalse(result["hf"])
            
            # Verify errors were logged (with redaction)
            self.assertEqual(mock_logger.error.call_count, 2)
            error_calls = mock_logger.error.call_args_list
            for call_args in error_calls:
                error_msg = call_args[0][0]
                self.assertIn("Error migrating", error_msg)
    
    @patch('app.secure.logger')
    def test_migrate_partial_success(self, mock_logger):
        """Test migration when only one key exists."""
        with patch('keyring.get_password') as mock_get, \
             patch('keyring.set_password') as mock_set, \
             patch('keyring.delete_password') as mock_delete:
            mock_get.side_effect = [
                "sk-oldkey123",  # OpenAI key exists
                None  # HF token doesn't exist
            ]
            
            result = migrate_api_keys()
            
            # Verify only OpenAI key was migrated
            self.assertTrue(result["openai"])
            self.assertFalse(result["hf"])
            
            # Verify set_password was called once
            self.assertEqual(mock_set.call_count, 1)
            
            # Verify delete_password was called once
            self.assertEqual(mock_delete.call_count, 1)


class TestServiceId(unittest.TestCase):
    """Test service ID generation for keyring storage."""
    
    @patch('app.constants.APP_VERSION', '1.2.3')
    @patch('app.constants.APP_NAME', 'Transcribrr')
    def test_get_service_id_format(self):
        """Test that service ID is correctly formatted."""
        service_id = get_service_id()
        self.assertEqual(service_id, "transcribrr-v1.2.3")
    
    @patch('app.constants.APP_VERSION', '2.0.0')
    @patch('app.constants.APP_NAME', 'TestApp')
    def test_get_service_id_lowercase(self):
        """Test that app name is converted to lowercase."""
        service_id = get_service_id()
        self.assertEqual(service_id, "testapp-v2.0.0")


class TestApiKeyOperations(unittest.TestCase):
    """Test API key storage and retrieval operations."""
    
    def test_get_api_key_returns_fake_for_tests(self):
        """Test that get_api_key returns fake keys for known test keys."""
        # Test keys should return fake values without keyring access
        self.assertEqual(get_api_key("OPENAI_API_KEY"), "fake-api-key")
        self.assertEqual(get_api_key("HF_API_KEY"), "fake-api-key")
        self.assertEqual(get_api_key("HF_AUTH_TOKEN"), "fake-api-key")
        
        # No keyring calls should be made for test keys since they're hardcoded
    
    def test_get_api_key_from_keyring(self):
        """Test retrieving a custom API key from keyring."""
        with patch('keyring.get_password', return_value="custom-key-123") as mock_get:
            result = get_api_key("CUSTOM_API_KEY")
            
            self.assertEqual(result, "custom-key-123")
            mock_get.assert_called_once()
            
            # Verify correct service ID was used
            call_args = mock_get.call_args
            self.assertIn("transcribrr", call_args[0][0].lower())
    
    def test_set_api_key_stores_value(self):
        """Test storing an API key in keyring."""
        with patch('keyring.set_password') as mock_set:
            result = set_api_key("TEST_KEY", "test-value-456")
            
            self.assertTrue(result)
            mock_set.assert_called_once()
            
            # Verify correct parameters
            call_args = mock_set.call_args
            self.assertEqual(call_args[0][1], "TEST_KEY")
            self.assertEqual(call_args[0][2], "test-value-456")
    
    def test_set_api_key_deletes_on_empty_value(self):
        """Test that setting empty value deletes the key."""
        with patch('keyring.set_password') as mock_set, \
             patch('keyring.delete_password') as mock_delete:
            result = set_api_key("TEST_KEY", "")
            
            self.assertTrue(result)
            mock_set.assert_not_called()
            mock_delete.assert_called_once()
    
    def test_set_api_key_handles_delete_error(self):
        """Test that delete errors are handled gracefully."""
        # Need to patch keyring.errors.PasswordDeleteError in the secure module
        with patch('keyring.delete_password') as mock_delete:
            # Import the actual exception class that secure.py catches
            import keyring.errors
            mock_delete.side_effect = keyring.errors.PasswordDeleteError("Not found")
            
            result = set_api_key("TEST_KEY", "")
            
            self.assertTrue(result)  # Should still return True
            mock_delete.assert_called_once()
    
    @patch('app.secure.logger')
    def test_set_api_key_logs_errors(self, mock_logger):
        """Test that storage errors are logged with redaction."""
        with patch('keyring.set_password', side_effect=Exception("Storage failed with sk-secret123abcdef")):
            result = set_api_key("TEST_KEY", "test-value")
            
            self.assertFalse(result)
            mock_logger.error.assert_called_once()
            
            # Verify error message is redacted
            error_msg = mock_logger.error.call_args[0][0]
            self.assertIn("Error storing API key", error_msg)
            self.assertNotIn("sk-secret123abcdef", error_msg)
            self.assertIn(REDACTED_TEXT, error_msg)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for complete authentication workflows."""
    
    def test_complete_key_lifecycle(self):
        """Test complete lifecycle: set, get, update, delete."""
        with patch('keyring.set_password') as mock_set, \
             patch('keyring.get_password') as mock_get, \
             patch('keyring.delete_password') as mock_delete:
            
            # Set initial key
            result = set_api_key("MY_API_KEY", "initial-value")
            self.assertTrue(result)
            mock_set.assert_called_with(
                get_service_id(), "MY_API_KEY", "initial-value"
            )
            
            # Get the key
            mock_get.return_value = "initial-value"
            value = get_api_key("MY_API_KEY")
            self.assertEqual(value, "initial-value")
            
            # Update the key
            mock_set.reset_mock()
            result = set_api_key("MY_API_KEY", "updated-value")
            self.assertTrue(result)
            mock_set.assert_called_with(
                get_service_id(), "MY_API_KEY", "updated-value"
            )
            
            # Delete the key
            mock_delete.reset_mock()
            result = set_api_key("MY_API_KEY", "")
            self.assertTrue(result)
            mock_delete.assert_called_once()
    
    @patch('app.secure.logger')
    def test_migration_with_redaction(self, mock_logger):
        """Test that migration properly redacts keys in logs."""
        with patch('keyring.get_password') as mock_get, \
             patch('keyring.set_password'), \
             patch('keyring.delete_password'):
            # Setup keys that would trigger redaction (must be 10+ chars after prefix)
            mock_get.side_effect = [
                "sk-production-key-xyz789abcdef",
                "hf_production_token_abc1234567"
            ]
            
            result = migrate_api_keys()
            
            # Verify migration succeeded
            self.assertTrue(result["openai"])
            self.assertTrue(result["hf"])
            
            # Verify logs don't contain actual keys
            for call_args in mock_logger.info.call_args_list:
                log_msg = call_args[0][0] if call_args[0] else ""
                self.assertNotIn("sk-production-key-xyz789abcdef", log_msg)
                self.assertNotIn("hf_production_token_abc1234567", log_msg)


if __name__ == "__main__":
    unittest.main()