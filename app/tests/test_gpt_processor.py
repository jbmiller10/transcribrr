"""Tests for GPT processing functionality.

These tests ensure proper behavior of the GPTController and avoid common anti-patterns:
- No Liar tests: All assertions test actual behavior, not just method calls
- No Mystery Guest: All external dependencies are properly mocked
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from typing import Dict, Any

from app.controllers.gpt_controller import GPTController
from app.models.recording import Recording


class TestGPTController(unittest.TestCase):
    """Tests for GPTController."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock database manager
        self.db_manager = Mock()
        
        # Mock API key retrieval
        self.mock_get_api_key = Mock(return_value="test-api-key")
        
        # Mock GPT thread class
        self.mock_thread_class = Mock()
        self.mock_thread_instance = Mock()
        self.mock_thread_class.return_value = self.mock_thread_instance
        
        # Configure thread instance mock
        self.mock_thread_instance.isRunning = Mock(return_value=False)
        self.mock_thread_instance.start = Mock()
        self.mock_thread_instance.cancel = Mock()
        
        # Mock signals on thread
        self.mock_thread_instance.completed = Mock()
        self.mock_thread_instance.completed.connect = Mock()
        self.mock_thread_instance.update_progress = Mock()
        self.mock_thread_instance.update_progress.connect = Mock()
        self.mock_thread_instance.error = Mock()
        self.mock_thread_instance.error.connect = Mock()
        self.mock_thread_instance.finished = Mock()
        self.mock_thread_instance.finished.connect = Mock()
        
        # Create controller with mocked dependencies
        with patch('app.controllers.gpt_controller.get_api_key', self.mock_get_api_key):
            with patch('app.controllers.gpt_controller.GPT4ProcessingThread', self.mock_thread_class):
                self.controller = GPTController(self.db_manager)
                # Override captured dependencies
                self.controller.get_api_key = self.mock_get_api_key
                self.controller._Thread = self.mock_thread_class
        
        # Create test recording with all required fields
        self.recording = Recording(
            id=1,
            filename="test.wav",
            file_path="/path/to/test.wav",
            date_created="2024-01-01 12:00:00",
            duration=120.5,
            raw_transcript="This is a test transcript.",
            processed_text=None
        )
        
        # Create test config
        self.config = {
            "gpt_model": "gpt-4o",
            "max_tokens": 16000,
            "temperature": 1.0
        }
        
        # Mock busy guard callback
        self.busy_guard_mock = Mock()
        self.busy_guard_callback = Mock(return_value=self.busy_guard_mock)
        
        # Mock completion callback
        self.completion_callback = Mock()
    
    def test_process_with_valid_inputs_starts_thread(self):
        """Test that process method starts thread with valid inputs."""
        # Act
        result = self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Returns True for successful start
        self.assertTrue(result)
        
        # Assert: Thread was created with correct parameters
        self.mock_thread_class.assert_called_once_with(
            transcript="This is a test transcript.",
            prompt_instructions="Test prompt",
            gpt_model="gpt-4o",
            max_tokens=16000,
            temperature=1.0,
            openai_api_key="test-api-key"
        )
        
        # Assert: Thread was started
        self.mock_thread_instance.start.assert_called_once()
        
        # Assert: Busy guard was created
        self.busy_guard_callback.assert_called_once_with(
            operation_name="GPT Processing",
            spinner="gpt_process"
        )
        
        # Assert: Thread is stored
        self.assertIn("process", self.controller.threads)
        self.assertEqual(
            self.controller.threads["process"]["thread"],
            self.mock_thread_instance
        )
    
    def test_process_without_transcript_returns_false(self):
        """Test that process returns False when recording has no transcript."""
        # Arrange: Recording without transcript
        recording_no_transcript = Recording(
            id=2,
            filename="empty.wav",
            file_path="/path/to/empty.wav",
            date_created="2024-01-01 12:00:00",
            duration=60.0,
            raw_transcript=None,
            processed_text=None
        )
        
        # Act
        result = self.controller.process(
            recording_no_transcript,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Returns False
        self.assertFalse(result)
        
        # Assert: Thread was not created
        self.mock_thread_class.assert_not_called()
        
        # Assert: Thread was not started
        self.mock_thread_instance.start.assert_not_called()
    
    def test_process_without_prompt_returns_false(self):
        """Test that process returns False when no prompt is provided."""
        # Act
        result = self.controller.process(
            self.recording,
            "",  # Empty prompt
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Returns False
        self.assertFalse(result)
        
        # Assert: Thread was not created
        self.mock_thread_class.assert_not_called()
    
    def test_process_without_api_key_returns_false(self):
        """Test that process returns False when API key is missing."""
        # Arrange: Mock API key retrieval to return None
        self.controller.get_api_key = Mock(return_value=None)
        
        # Act
        result = self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Returns False
        self.assertFalse(result)
        
        # Assert: Thread was not created
        self.mock_thread_class.assert_not_called()
    
    def test_smart_format_creates_thread_with_formatting_prompt(self):
        """Test that smart_format creates thread with correct formatting prompt."""
        # Act
        result = self.controller.smart_format(
            "Text to format",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Returns True
        self.assertTrue(result)
        
        # Assert: Thread was created with formatting parameters
        expected_prompt = (
            "Format the following text using HTML for better readability. "
            "Add appropriate paragraph breaks, emphasis, and structure. "
            "Do not change the actual content or meaning of the text. "
            "Use basic HTML tags like <p>, <strong>, <em>, <h3>, <ul>, <li> etc. "
            "Here is the text to format:"
        )
        self.mock_thread_class.assert_called_once_with(
            transcript="Text to format",
            prompt_instructions=expected_prompt,
            gpt_model="gpt-4o-mini",  # Uses cheaper model
            max_tokens=16000,
            temperature=0.3,  # Lower temperature for formatting
            openai_api_key="test-api-key"
        )
        
        # Assert: Thread was started
        self.mock_thread_instance.start.assert_called_once()
    
    def test_refine_creates_thread_with_message_history(self):
        """Test that refine creates thread with proper message history."""
        # Act
        result = self.controller.refine(
            self.recording,
            "Make it more concise",
            "Original prompt",
            "Current processed text",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Returns True
        self.assertTrue(result)
        
        # Assert: Thread was created with messages parameter
        call_args = self.mock_thread_class.call_args
        self.assertIn('messages', call_args[1])
        
        messages = call_args[1]['messages']
        # Check message structure
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn("Original prompt was: Original prompt", messages[0]['content'])
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn("This is a test transcript", messages[1]['content'])
        self.assertEqual(messages[2]['role'], 'assistant')
        self.assertEqual(messages[2]['content'], 'Current processed text')
        self.assertEqual(messages[3]['role'], 'user')
        self.assertEqual(messages[3]['content'], 'Make it more concise')
    
    def test_cancel_calls_thread_cancel_when_running(self):
        """Test that cancel stops running thread."""
        # Arrange: Start a process first
        self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Configure thread as running
        self.mock_thread_instance.isRunning.return_value = True
        
        # Act
        self.controller.cancel("process")
        
        # Assert: Thread cancel was called
        self.mock_thread_instance.cancel.assert_called_once()
    
    def test_cancel_does_nothing_for_non_running_thread(self):
        """Test that cancel does nothing if thread is not running."""
        # Arrange: Start a process first
        self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Configure thread as not running
        self.mock_thread_instance.isRunning.return_value = False
        
        # Act
        self.controller.cancel("process")
        
        # Assert: Thread cancel was not called
        self.mock_thread_instance.cancel.assert_not_called()
    
    def test_process_completed_updates_database(self):
        """Test that process completion updates database with result."""
        # Arrange: Start a process
        self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Get the connected completion handler
        completion_handler = self.mock_thread_instance.completed.connect.call_args[0][0]
        
        # Act: Simulate thread completion
        completion_handler("Processed result text")
        
        # Assert: Database update was called with correct parameters
        self.db_manager.update_recording.assert_called_once()
        call_args = self.db_manager.update_recording.call_args
        self.assertEqual(call_args[0][0], 1)  # Recording ID
        self.assertIn('processed_text', call_args[1])
        self.assertEqual(call_args[1]['processed_text'], "Processed result text")
    
    def test_process_completed_calls_completion_callback(self):
        """Test that completion callback is called with result."""
        # Arrange: Start a process
        self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Get the connected completion handler
        completion_handler = self.mock_thread_instance.completed.connect.call_args[0][0]
        
        # Act: Simulate thread completion and database update
        completion_handler("Processed result text")
        
        # Simulate database update completion
        db_callback = self.db_manager.update_recording.call_args[0][1]
        db_callback()
        
        # Assert: Completion callback was called with result
        self.completion_callback.assert_called_once_with("Processed result text")
    
    def test_process_finished_cleans_up_thread_reference(self):
        """Test that finished handler removes thread from storage."""
        # Arrange: Start a process
        self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Verify thread is stored
        self.assertIn("process", self.controller.threads)
        
        # Get the connected finished handler
        finished_handler = self.mock_thread_instance.finished.connect.call_args[0][0]
        
        # Act: Simulate thread finished
        finished_handler()
        
        # Assert: Thread reference is removed
        self.assertNotIn("process", self.controller.threads)
    
    def test_multiple_operations_use_different_thread_keys(self):
        """Test that different operations can run concurrently with different keys."""
        # Act: Start multiple operations
        self.controller.process(
            self.recording,
            "Test prompt",
            self.config,
            self.busy_guard_callback,
            None
        )
        
        self.controller.smart_format(
            "Text to format",
            self.config,
            self.busy_guard_callback,
            None
        )
        
        # Reset mock to test refine separately
        self.mock_thread_class.reset_mock()
        self.mock_thread_instance.reset_mock()
        
        self.controller.refine(
            self.recording,
            "Refine this",
            "Original",
            "Current",
            self.config,
            self.busy_guard_callback,
            None
        )
        
        # Assert: Different thread keys are used
        self.assertIn("process", self.controller.threads)
        self.assertIn("smart_format", self.controller.threads)
        self.assertIn("refinement", self.controller.threads)
        
        # Assert: All are different thread instances (in real code)
        self.assertEqual(len(self.controller.threads), 3)
    
    def test_uses_config_values_for_model_and_parameters(self):
        """Test that config values override defaults."""
        # Arrange: Custom config
        custom_config = {
            "gpt_model": "gpt-3.5-turbo",
            "max_tokens": 8000,
            "temperature": 0.5
        }
        
        # Act
        result = self.controller.process(
            self.recording,
            "Test prompt",
            custom_config,
            self.busy_guard_callback,
            self.completion_callback
        )
        
        # Assert: Custom values were used
        self.mock_thread_class.assert_called_once_with(
            transcript="This is a test transcript.",
            prompt_instructions="Test prompt",
            gpt_model="gpt-3.5-turbo",  # Custom model
            max_tokens=8000,  # Custom max tokens
            temperature=0.5,  # Custom temperature
            openai_api_key="test-api-key"
        )


if __name__ == '__main__':
    unittest.main()