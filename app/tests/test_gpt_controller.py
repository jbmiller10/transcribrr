from app.models.view_mode import ViewMode
from app.models.recording import Recording
import unittest
from unittest.mock import MagicMock, patch, ANY
import os

# Create stubs for PyQt6
import sys
import types
sys.modules.setdefault('PyQt6', types.ModuleType('PyQt6'))
qt_core = types.ModuleType('PyQt6.QtCore')

# Add stub classes


class QObject:
    def __init__(self, *args, **kwargs): pass


class Signal:
    def __init__(self, *args): pass
    def connect(self, func): pass
    def emit(self, *args): pass
    def disconnect(self): pass


# Assign stub classes to PyQt6 modules
qt_core.QObject = QObject
qt_core.pyqtSignal = Signal

# Assign modules to sys.modules
sys.modules['PyQt6.QtCore'] = qt_core

# Import the Recording dataclass

# Create mock for dependencies before importing the class under test
with patch('app.controllers.gpt_controller.GPT4ProcessingThread') as MockGPT4Thread, \
        patch('app.controllers.gpt_controller.ThreadManager') as MockThreadManager, \
        patch('app.controllers.gpt_controller.get_api_key', return_value='fake-api-key'):

    # Set up mock thread manager
    mock_tm_instance = MagicMock()
    MockThreadManager.instance.return_value = mock_tm_instance

    # Set up mock GPT thread
    mock_thread = MagicMock()
    MockGPT4Thread.return_value = mock_thread

    # Import the class under test
    from app.controllers.gpt_controller import GPTController


class TestGPTController(unittest.TestCase):
    """Test cases for the GPTController."""

    def setUp(self):
        # Create a mock database manager
        self.db_manager = MagicMock()

        # Create the controller
        self.controller = GPTController(self.db_manager)

        # Create a sample recording
        self.recording = Recording(
            id=123,
            filename="test_recording.mp3",
            file_path="/path/to/test_recording.mp3",
            date_created="2023-01-01 12:00:00",
            duration=60.0,
            raw_transcript="This is a test transcript for GPT processing.",
            processed_text=None
        )

        # Sample config
        self.config = {
            'gpt_model': 'gpt-4o',
            'max_tokens': 16000,
            'temperature': 1.0
        }

        # Test prompt
        self.prompt = "Summarize the following transcript:"

        # BusyGuard mock
        self.busy_guard_mock = MagicMock()
        self.busy_guard_callback = MagicMock(return_value=self.busy_guard_mock)

        # Reset all mocks
        from app.controllers.gpt_controller import GPT4ProcessingThread
        GPT4ProcessingThread.reset_mock()
        mock_thread.reset_mock()

    def test_process(self):
        """Test processing with GPT."""
        # Create completion callback
        completion_callback = MagicMock()

        # Call the method
        result = self.controller.process(
            self.recording, self.prompt, self.config,
            self.busy_guard_callback, completion_callback
        )

        # Verify result
        self.assertTrue(result)

        # Verify thread was created with correct arguments
        from app.controllers.gpt_controller import GPT4ProcessingThread
        GPT4ProcessingThread.assert_called_once()
        call_args = GPT4ProcessingThread.call_args[1]
        self.assertEqual(call_args['transcript'], self.recording.raw_transcript)
        self.assertEqual(call_args['prompt_instructions'], self.prompt)
        self.assertEqual(call_args['gpt_model'], 'gpt-4o')
        self.assertEqual(call_args['max_tokens'], 16000)
        self.assertEqual(call_args['temperature'], 1.0)
        self.assertEqual(call_args['openai_api_key'], 'fake-api-key')

        # Verify BusyGuard was created
        self.busy_guard_callback.assert_called_once()
        busy_args = self.busy_guard_callback.call_args[1]
        self.assertEqual(busy_args['operation_name'], "GPT Processing")
        self.assertEqual(busy_args['spinner'], 'gpt_process')

        # Verify thread was started and signals were connected
        thread = MockGPT4Thread.return_value
        thread.start.assert_called_once()
        thread.completed.connect.assert_called_once()
        thread.update_progress.connect.assert_called_once()
        thread.error.connect.assert_called_once()
        thread.finished.connect.assert_called_once()

        # Verify signal was emitted
        self.controller.gpt_process_started.emit.assert_called_once()

        # Test thread is stored
        self.assertIn('process', self.controller.threads)
        self.assertEqual(self.controller.threads['process']['thread'], thread)

    def test_process_validation(self):
        """Test validation in process method."""
        # Test with no raw transcript
        recording_no_transcript = Recording(
            id=124,
            filename="no_transcript.mp3",
            file_path="/path/to/no_transcript.mp3",
            date_created="2023-01-01 12:00:00",
            duration=60.0,
            raw_transcript=None,
            processed_text=None
        )

        result = self.controller.process(
            recording_no_transcript, self.prompt, self.config,
            self.busy_guard_callback
        )

        # Verify validation failed
        self.assertFalse(result)

        # Test with empty prompt
        result = self.controller.process(
            self.recording, "", self.config,
            self.busy_guard_callback
        )

        # Verify validation failed
        self.assertFalse(result)

        # Test with missing API key
        with patch('app.controllers.gpt_controller.get_api_key', return_value=None):
            result = self.controller.process(
                self.recording, self.prompt, self.config,
                self.busy_guard_callback
            )

            # Verify validation failed
            self.assertFalse(result)

    def test_smart_format(self):
        """Test smart formatting with GPT."""
        # Create completion callback
        completion_callback = MagicMock()

        # Text to format
        text_to_format = "This is a test text to format."

        # Call the method
        result = self.controller.smart_format(
            text_to_format, self.config,
            self.busy_guard_callback, completion_callback
        )

        # Verify result
        self.assertTrue(result)

        # Verify thread was created with correct arguments
        from app.controllers.gpt_controller import GPT4ProcessingThread
        GPT4ProcessingThread.assert_called_once()
        call_args = GPT4ProcessingThread.call_args[1]
        self.assertEqual(call_args['transcript'], text_to_format)
        self.assertIn("Format the following text using HTML", call_args['prompt_instructions'])
        self.assertEqual(call_args['gpt_model'], 'gpt-4o-mini')  # Should use cheaper model
        self.assertEqual(call_args['temperature'], 0.3)  # Should use lower temperature

        # Verify BusyGuard was created
        self.busy_guard_callback.assert_called_once()
        busy_args = self.busy_guard_callback.call_args[1]
        self.assertEqual(busy_args['operation_name'], "Smart Formatting")
        self.assertEqual(busy_args['spinner'], 'smart_format')

        # Test thread is stored
        self.assertIn('smart_format', self.controller.threads)

    def test_refine(self):
        """Test refinement processing with GPT."""
        # Create processed recording
        processed_recording = Recording(
            id=125,
            filename="processed.mp3",
            file_path="/path/to/processed.mp3",
            date_created="2023-01-01 12:00:00",
            duration=60.0,
            raw_transcript="Raw transcript for refinement.",
            processed_text="Processed text for refinement."
        )

        # Refinement instructions
        refinement = "Make it more formal."

        # Initial prompt
        initial_prompt = "Summarize the transcript."

        # Processed text
        processed_text = "This is the processed text to refine."

        # Create completion callback
        completion_callback = MagicMock()

        # Call the method
        result = self.controller.refine(
            processed_recording, refinement, initial_prompt, processed_text,
            self.config, self.busy_guard_callback, completion_callback
        )

        # Verify result
        self.assertTrue(result)

        # Verify thread was created with correct arguments
        from app.controllers.gpt_controller import GPT4ProcessingThread
        GPT4ProcessingThread.assert_called_once()
        call_args = GPT4ProcessingThread.call_args[1]

        # Should use messages format for refinement
        self.assertIn('messages', call_args)
        messages = call_args['messages']
        self.assertEqual(len(messages), 4)  # Should have 4 messages

        # Verify system prompt contains refinement instructions
        self.assertEqual(messages[0]['role'], 'system')
        self.assertIn(refinement, messages[0]['content'])

        # Verify user message contains raw transcript
        self.assertEqual(messages[1]['role'], 'user')
        self.assertIn(processed_recording.raw_transcript, messages[1]['content'])

        # Verify assistant message contains processed text
        self.assertEqual(messages[2]['role'], 'assistant')
        self.assertEqual(messages[2]['content'], processed_text)

        # Verify final user message contains refinement instruction
        self.assertEqual(messages[3]['role'], 'user')
        self.assertEqual(messages[3]['content'], refinement)

        # Verify BusyGuard was created
        self.busy_guard_callback.assert_called_once()
        busy_args = self.busy_guard_callback.call_args[1]
        self.assertEqual(busy_args['operation_name'], "Text Refinement")
        self.assertEqual(busy_args['spinner'], 'refinement')

        # Test thread is stored
        self.assertIn('refinement', self.controller.threads)

    def test_cancel(self):
        """Test cancelling a running thread."""
        # Create a mock thread in the threads dict
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True

        self.controller.threads = {
            'test_thread': {
                'thread': mock_thread,
                'busy_guard': MagicMock()
            }
        }

        # Call the method
        self.controller.cancel('test_thread')

        # Verify thread was cancelled
        mock_thread.cancel.assert_called_once()
        self.controller.status_update.emit.assert_called_once()

        # Test cancelling nonexistent thread
        self.controller.status_update.emit.reset_mock()
        self.controller.cancel('nonexistent_thread')

        # Verify no error and no call to emit
        self.controller.status_update.emit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
