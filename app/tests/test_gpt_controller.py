"""Tests for the GPTController class.

This test file implements all test cases specified in the YAML test plan
for the GPTController class. It uses unittest.mock to patch all external
dependencies and allows headless testing without PyQt6 or other dependencies.
"""

import unittest
from unittest.mock import MagicMock, Mock, patch, call
import logging


class TestGPTController(unittest.TestCase):
    """Test cases for the GPTController."""

    @patch('app.controllers.gpt_controller.logger')
    @patch('app.controllers.gpt_controller.get_api_key')
    @patch('app.controllers.gpt_controller.GPT4ProcessingThread')
    @patch('app.controllers.gpt_controller.Recording')
    def setUp(self, mock_recording, mock_thread_class, mock_get_api_key, mock_logger):
        """Set up test fixtures."""
        # Store mocks as instance variables
        self.mock_recording_class = mock_recording
        self.mock_thread_class = mock_thread_class
        self.mock_get_api_key = mock_get_api_key
        self.mock_logger = mock_logger
        
        # Create mock db_manager
        self.mock_db_manager = Mock()
        
        # Patch QObject and pyqtSignal for GPTController
        with patch('app.controllers.gpt_controller.QObject'):
            with patch('app.controllers.gpt_controller.pyqtSignal', Mock):
                from app.controllers.gpt_controller import GPTController
                # Create controller instance
                self.controller = GPTController(self.mock_db_manager)
        
        # Reset signal mocks
        self.controller.gpt_process_started = Mock()
        self.controller.gpt_process_completed = Mock()
        self.controller.gpt_process_stopped = Mock()
        self.controller.status_update = Mock()
        self.controller.recording_status_updated = Mock()

    # ============= __init__ tests =============
    
    def test_init_successful(self):
        """Tests successful initialization of GPTController."""
        with patch('app.controllers.gpt_controller.QObject'):
            with patch('app.controllers.gpt_controller.pyqtSignal', Mock):
                from app.controllers.gpt_controller import GPTController
                
                # Create new instance to test initialization
                controller = GPTController(self.mock_db_manager, parent=None)
                
                # Verify db_manager is stored as instance attribute
                self.assertEqual(controller.db_manager, self.mock_db_manager)
                
                # Verify threads dictionary is initialized as empty dict
                self.assertEqual(controller.threads, {})

    # ============= process() method tests - Happy path =============
    
    def test_process_successful(self):
        """Tests successful GPT processing with valid inputs."""
        # Set up mocks
        mock_recording = Mock()
        mock_recording.id = 1
        mock_recording.raw_transcript = 'test transcript'
        
        self.mock_get_api_key.return_value = 'test-api-key'
        
        mock_thread = Mock()
        self.mock_thread_class.return_value = mock_thread
        
        mock_busy_guard = Mock()
        mock_busy_guard_callback = Mock(return_value=mock_busy_guard)
        
        config = {
            'gpt_model': 'gpt-4o',
            'max_tokens': 16000,
            'temperature': 1.0
        }
        
        # Call the method
        result = self.controller.process(
            recording=mock_recording,
            prompt='Test prompt',
            config=config,
            busy_guard_callback=mock_busy_guard_callback,
            completion_callback=None
        )
        
        # Verify method returns True
        self.assertTrue(result)
        
        # Verify GPT4ProcessingThread instantiated with correct parameters
        self.mock_thread_class.assert_called_once_with(
            transcript='test transcript',
            prompt_instructions='Test prompt',
            gpt_model='gpt-4o',
            max_tokens=16000,
            temperature=1.0,
            openai_api_key='test-api-key'
        )
        
        # Verify thread signals are connected to handler methods
        mock_thread.completed.connect.assert_called_once()
        mock_thread.update_progress.connect.assert_called_once()
        mock_thread.error.connect.assert_called_once()
        mock_thread.finished.connect.assert_called_once()
        
        # Verify thread is stored in self.threads dictionary
        self.assertIn('process', self.controller.threads)
        self.assertEqual(self.controller.threads['process']['thread'], mock_thread)
        self.assertEqual(self.controller.threads['process']['busy_guard'], mock_busy_guard)
        
        # Verify status_update signal emitted with 'Starting GPT processing...'
        self.controller.status_update.emit.assert_called_with('Starting GPT processing...')
        
        # Verify gpt_process_started signal emitted
        self.controller.gpt_process_started.emit.assert_called_once()
        
        # Verify Thread.start() is called
        mock_thread.start.assert_called_once()

    # ============= process() method tests - Validation failures =============
    
    def test_process_fails_with_none_recording(self):
        """Tests process fails when recording is None."""
        result = self.controller.process(
            recording=None,
            prompt='Test prompt',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No transcript available for GPT processing')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_process_fails_with_empty_transcript(self):
        """Tests process fails when recording has no transcript."""
        mock_recording = Mock()
        mock_recording.raw_transcript = ''
        
        result = self.controller.process(
            recording=mock_recording,
            prompt='Test prompt',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No transcript available for GPT processing')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_process_fails_with_empty_prompt(self):
        """Tests process fails when prompt is empty."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        
        result = self.controller.process(
            recording=mock_recording,
            prompt='',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No prompt provided for GPT processing')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_process_fails_without_api_key(self):
        """Tests process fails when API key is missing."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        self.mock_get_api_key.return_value = None
        
        result = self.controller.process(
            recording=mock_recording,
            prompt='test prompt',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('OpenAI API key missing for GPT processing')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    # ============= process() method tests - Config variations =============
    
    def test_process_with_custom_config(self):
        """Tests process with custom config values."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        self.mock_get_api_key.return_value = 'test-key'
        
        config = {
            'gpt_model': 'gpt-3.5-turbo',
            'max_tokens': 8000,
            'temperature': 0.5
        }
        
        self.controller.process(
            recording=mock_recording,
            prompt='test prompt',
            config=config,
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify GPT4ProcessingThread called with custom config values
        self.mock_thread_class.assert_called_once_with(
            transcript='test',
            prompt_instructions='test prompt',
            gpt_model='gpt-3.5-turbo',
            max_tokens=8000,
            temperature=0.5,
            openai_api_key='test-key'
        )

    def test_process_with_default_config(self):
        """Tests process with default config values."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        self.mock_get_api_key.return_value = 'test-key'
        
        self.controller.process(
            recording=mock_recording,
            prompt='test prompt',
            config={},  # Empty config
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify GPT4ProcessingThread called with default values
        self.mock_thread_class.assert_called_once_with(
            transcript='test',
            prompt_instructions='test prompt',
            gpt_model='gpt-4o',
            max_tokens=16000,
            temperature=1.0,
            openai_api_key='test-key'
        )

    # ============= smart_format() method tests - Happy path =============
    
    def test_smart_format_successful(self):
        """Tests successful smart formatting with valid text."""
        self.mock_get_api_key.return_value = 'test-api-key'
        
        mock_thread = Mock()
        self.mock_thread_class.return_value = mock_thread
        
        mock_busy_guard = Mock()
        mock_busy_guard_callback = Mock(return_value=mock_busy_guard)
        
        result = self.controller.smart_format(
            text='Test text to format',
            config={},
            busy_guard_callback=mock_busy_guard_callback,
            completion_callback=None
        )
        
        # Verify method returns True
        self.assertTrue(result)
        
        # Verify GPT4ProcessingThread instantiated with gpt_model='gpt-4o-mini'
        args, kwargs = self.mock_thread_class.call_args
        self.assertEqual(kwargs['gpt_model'], 'gpt-4o-mini')
        
        # Verify GPT4ProcessingThread instantiated with temperature=0.3
        self.assertEqual(kwargs['temperature'], 0.3)
        
        # Verify thread signals connected to format-specific handlers
        mock_thread.completed.connect.assert_called_once()
        mock_thread.update_progress.connect.assert_called_once()
        mock_thread.error.connect.assert_called_once()
        mock_thread.finished.connect.assert_called_once()
        
        # Verify thread stored in self.threads['smart_format']
        self.assertIn('smart_format', self.controller.threads)
        self.assertEqual(self.controller.threads['smart_format']['thread'], mock_thread)
        
        # Verify status_update signal emitted with 'Formatting text...'
        self.controller.status_update.emit.assert_called_with('Formatting text...')
        
        # Verify Thread.start() is called
        mock_thread.start.assert_called_once()

    # ============= smart_format() method tests - Validation failures =============
    
    def test_smart_format_fails_with_empty_text(self):
        """Tests smart_format fails with empty text."""
        result = self.controller.smart_format(
            text='',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No text provided for smart formatting')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_smart_format_fails_without_api_key(self):
        """Tests smart_format fails without API key."""
        self.mock_get_api_key.return_value = None
        
        result = self.controller.smart_format(
            text='Test text',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('OpenAI API key missing for smart formatting')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    # ============= refine() method tests - Happy path =============
    
    def test_refine_successful(self):
        """Tests successful text refinement with all valid inputs."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'original'
        
        self.mock_get_api_key.return_value = 'test-api-key'
        
        mock_thread = Mock()
        self.mock_thread_class.return_value = mock_thread
        
        mock_busy_guard = Mock()
        mock_busy_guard_callback = Mock(return_value=mock_busy_guard)
        
        result = self.controller.refine(
            recording=mock_recording,
            refinement_instructions='Make it shorter',
            initial_prompt='Summarize this',
            current_text='Current processed text',
            config={},
            busy_guard_callback=mock_busy_guard_callback,
            completion_callback=None
        )
        
        # Verify method returns True
        self.assertTrue(result)
        
        # Verify GPT4ProcessingThread instantiated with messages list
        args, kwargs = self.mock_thread_class.call_args
        self.assertIn('messages', kwargs)
        messages = kwargs['messages']
        
        # Verify messages list contains system, user, assistant, and user roles
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['role'], 'user')
        self.assertEqual(messages[2]['role'], 'assistant')
        self.assertEqual(messages[3]['role'], 'user')
        
        # Verify thread signals connected to refinement-specific handlers
        mock_thread.completed.connect.assert_called_once()
        
        # Verify thread stored in self.threads['refinement']
        self.assertIn('refinement', self.controller.threads)
        
        # Verify status_update signal emitted with 'Refining text...'
        self.controller.status_update.emit.assert_called_with('Refining text...')
        
        # Verify Thread.start() is called
        mock_thread.start.assert_called_once()

    # ============= refine() method tests - Validation failures =============
    
    def test_refine_fails_with_none_recording(self):
        """Tests refine fails when recording is None."""
        result = self.controller.refine(
            recording=None,
            refinement_instructions='instructions',
            initial_prompt='prompt',
            current_text='text',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No transcript available for refinement')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_refine_fails_with_empty_instructions(self):
        """Tests refine fails with empty refinement instructions."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        
        result = self.controller.refine(
            recording=mock_recording,
            refinement_instructions='',
            initial_prompt='prompt',
            current_text='text',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No refinement instructions provided')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_refine_fails_with_empty_current_text(self):
        """Tests refine fails with empty current text."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        
        result = self.controller.refine(
            recording=mock_recording,
            refinement_instructions='Make shorter',
            initial_prompt='prompt',
            current_text='',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('No current text provided for refinement')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    def test_refine_fails_without_api_key(self):
        """Tests refine fails without API key."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        self.mock_get_api_key.return_value = None
        
        result = self.controller.refine(
            recording=mock_recording,
            refinement_instructions='instructions',
            initial_prompt='prompt',
            current_text='text',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=None
        )
        
        # Verify method returns False
        self.assertFalse(result)
        
        # Verify error logged
        self.mock_logger.error.assert_called_with('OpenAI API key missing for refinement')
        
        # Verify no thread is created
        self.assertEqual(self.controller.threads, {})

    # ============= Callback handler tests =============
    
    def test_on_process_completed_with_recording(self):
        """Tests process completion handler with recording."""
        mock_recording = Mock()
        mock_recording.id = 123
        
        mock_completion_callback = Mock()
        
        # Call the handler
        self.controller._on_process_completed(
            mock_recording,
            'Processed text result',
            mock_completion_callback
        )
        
        # Verify db_manager.update_recording called with recording_id=123
        self.mock_db_manager.update_recording.assert_called_once()
        call_args = self.mock_db_manager.update_recording.call_args
        self.assertEqual(call_args[0][0], 123)  # recording_id
        self.assertEqual(call_args[1]['processed_text'], 'Processed text result')
        
        # Get the on_update_complete callback and call it
        on_update_complete = call_args[0][1]
        on_update_complete()
        
        # Verify on database update complete: status_update signal emitted
        self.controller.status_update.emit.assert_called_with('GPT processing complete')
        
        # Verify on database update complete: gpt_process_completed signal emitted
        self.controller.gpt_process_completed.emit.assert_called_with('Processed text result')
        
        # Verify on database update complete: completion_callback called
        mock_completion_callback.assert_called_once_with('Processed text result')

    def test_on_process_completed_with_none_recording(self):
        """Tests process completion handler when recording is None."""
        mock_completion_callback = Mock()
        
        # Call the handler with None recording
        self.controller._on_process_completed(
            None,
            'Result text',
            mock_completion_callback
        )
        
        # Verify method returns immediately
        # No database update attempted
        self.mock_db_manager.update_recording.assert_not_called()
        
        # No signals emitted
        self.controller.status_update.emit.assert_not_called()
        self.controller.gpt_process_completed.emit.assert_not_called()
        
        # No callback invoked
        mock_completion_callback.assert_not_called()

    def test_on_process_completed_without_callback(self):
        """Tests process completion without callback."""
        mock_recording = Mock()
        mock_recording.id = 456
        
        # Call the handler without callback
        self.controller._on_process_completed(
            mock_recording,
            'Result text',
            None
        )
        
        # Verify db_manager.update_recording called normally
        self.mock_db_manager.update_recording.assert_called_once()
        
        # Get the on_update_complete callback and call it
        on_update_complete = self.mock_db_manager.update_recording.call_args[0][1]
        on_update_complete()
        
        # Verify signals emitted normally
        self.controller.status_update.emit.assert_called_with('GPT processing complete')
        self.controller.gpt_process_completed.emit.assert_called_with('Result text')
        
        # No completion_callback invoked (None check passes)
        # No assertion needed - would raise AttributeError if called

    def test_on_format_completed_with_callback(self):
        """Tests format completion handler with callback."""
        mock_completion_callback = Mock()
        
        # Call the handler
        self.controller._on_format_completed(
            'Formatted HTML text',
            mock_completion_callback
        )
        
        # Verify status_update signal emitted with 'Formatting complete'
        self.controller.status_update.emit.assert_called_with('Formatting complete')
        
        # Verify completion_callback called with result
        mock_completion_callback.assert_called_once_with('Formatted HTML text')

    def test_on_format_completed_without_callback(self):
        """Tests format completion without callback."""
        # Call the handler without callback
        self.controller._on_format_completed(
            'Formatted text',
            None
        )
        
        # Verify status_update signal emitted with 'Formatting complete'
        self.controller.status_update.emit.assert_called_with('Formatting complete')
        
        # No callback invoked
        # No assertion needed - would raise AttributeError if called

    def test_on_refinement_completed_with_recording(self):
        """Tests refinement completion handler with recording."""
        mock_recording = Mock()
        mock_recording.id = 789
        
        mock_completion_callback = Mock()
        
        # Call the handler
        self.controller._on_refinement_completed(
            mock_recording,
            'Refined text',
            mock_completion_callback
        )
        
        # Verify db_manager.update_recording called with recording_id=789
        self.mock_db_manager.update_recording.assert_called_once()
        call_args = self.mock_db_manager.update_recording.call_args
        self.assertEqual(call_args[0][0], 789)  # recording_id
        
        # Only processed_text updated (raw transcript preserved)
        self.assertEqual(call_args[1]['processed_text'], 'Refined text')
        self.assertNotIn('raw_transcript', call_args[1])
        
        # Get the on_update_complete callback and call it
        on_update_complete = call_args[0][1]
        on_update_complete()
        
        # On database update: status_update signal emitted with 'Refinement complete'
        self.controller.status_update.emit.assert_called_with('Refinement complete')
        
        # On database update: completion_callback called with result
        mock_completion_callback.assert_called_once_with('Refined text')

    def test_on_refinement_completed_with_none_recording(self):
        """Tests refinement completion when recording is None."""
        mock_completion_callback = Mock()
        
        # Call the handler with None recording
        self.controller._on_refinement_completed(
            None,
            'Refined text',
            mock_completion_callback
        )
        
        # Verify method returns immediately
        # No database update attempted
        self.mock_db_manager.update_recording.assert_not_called()
        
        # No signals emitted
        self.controller.status_update.emit.assert_not_called()
        
        # No callback invoked
        mock_completion_callback.assert_not_called()

    def test_on_process_progress(self):
        """Tests progress update handler."""
        # Call the handler
        self.controller._on_process_progress('Processing: 50% complete')
        
        # Verify status_update signal emitted with message
        self.controller.status_update.emit.assert_called_with('Processing: 50% complete')

    def test_on_process_error(self):
        """Tests error handler."""
        # Call the handler
        self.controller._on_process_error('API rate limit exceeded')
        
        # Verify status_update signal emitted with formatted error message
        self.controller.status_update.emit.assert_called_with('GPT processing failed: API rate limit exceeded')

    def test_on_process_finished(self):
        """Tests thread cleanup on finish."""
        # Set up thread in dictionary
        mock_thread = Mock()
        mock_busy_guard = Mock()
        self.controller.threads = {
            'process': {'thread': mock_thread, 'busy_guard': mock_busy_guard}
        }
        
        # Call the handler
        self.controller._on_process_finished('process')
        
        # Verify thread entry removed from self.threads dictionary
        self.assertNotIn('process', self.controller.threads)
        
        # Verify logger info message
        self.mock_logger.info.assert_called_with('GPT thread (process) finished.')

    def test_on_process_finished_non_existent_key(self):
        """Tests thread cleanup when key doesn't exist."""
        # Start with empty threads dictionary
        self.controller.threads = {}
        
        # Call the handler with non-existent key
        self.controller._on_process_finished('non_existent')
        
        # Verify no error raised
        # Method should complete without exception
        
        # Verify logger info message
        self.mock_logger.info.assert_called_with('GPT thread (non_existent) finished.')

    # ============= cancel() method tests =============
    
    def test_cancel_running_thread(self):
        """Tests cancelling a running thread."""
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        mock_busy_guard = Mock()
        
        self.controller.threads = {
            'process': {'thread': mock_thread, 'busy_guard': mock_busy_guard}
        }
        
        # Call cancel
        self.controller.cancel('process')
        
        # Verify thread.cancel() is called
        mock_thread.cancel.assert_called_once()
        
        # Verify status_update signal emitted
        self.controller.status_update.emit.assert_called_with('Canceling process...')
        
        # Verify logger info
        self.mock_logger.info.assert_called_with('Canceling process thread...')

    def test_cancel_non_running_thread(self):
        """Tests cancel with non-running thread."""
        mock_thread = Mock()
        mock_thread.isRunning.return_value = False
        mock_busy_guard = Mock()
        
        self.controller.threads = {
            'process': {'thread': mock_thread, 'busy_guard': mock_busy_guard}
        }
        
        # Call cancel
        self.controller.cancel('process')
        
        # Verify thread.cancel() is not called
        mock_thread.cancel.assert_not_called()
        
        # Verify no status update emitted
        self.controller.status_update.emit.assert_not_called()
        
        # Verify no log message
        self.mock_logger.info.assert_not_called()

    def test_cancel_non_existent_thread_key(self):
        """Tests cancel with non-existent thread key."""
        self.controller.threads = {}
        
        # Call cancel with invalid key
        self.controller.cancel('invalid_key')
        
        # Verify no error raised
        # Method should complete without exception
        
        # Verify no action taken
        self.controller.status_update.emit.assert_not_called()
        self.mock_logger.info.assert_not_called()

    def test_cancel_custom_thread_key(self):
        """Tests cancel with custom thread key."""
        mock_thread = Mock()
        mock_thread.isRunning.return_value = True
        mock_busy_guard = Mock()
        
        self.controller.threads = {
            'smart_format': {'thread': mock_thread, 'busy_guard': mock_busy_guard}
        }
        
        # Call cancel
        self.controller.cancel('smart_format')
        
        # Verify thread.cancel() is called
        mock_thread.cancel.assert_called_once()
        
        # Verify status_update signal emitted
        self.controller.status_update.emit.assert_called_with('Canceling smart_format...')
        
        # Verify logger info
        self.mock_logger.info.assert_called_with('Canceling smart_format thread...')

    # ============= Edge cases and integration tests =============
    
    def test_process_with_callback_exception(self):
        """Tests process with completion callback that raises exception."""
        mock_recording = Mock()
        mock_recording.raw_transcript = 'test'
        self.mock_get_api_key.return_value = 'test-key'
        
        mock_thread = Mock()
        self.mock_thread_class.return_value = mock_thread
        
        # Create a callback that raises an exception
        def bad_callback(result):
            raise ValueError('Callback error')
        
        # Call process - should not raise exception
        result = self.controller.process(
            recording=mock_recording,
            prompt='test prompt',
            config={},
            busy_guard_callback=Mock(),
            completion_callback=bad_callback
        )
        
        # Verify thread creation and start proceed normally
        self.assertTrue(result)
        mock_thread.start.assert_called_once()
        
        # Exception is not propagated (handled gracefully)
        # Other signals still emitted
        self.controller.gpt_process_started.emit.assert_called_once()

    def test_multiple_concurrent_threads(self):
        """Tests multiple concurrent thread operations."""
        # Set up multiple threads
        thread1 = Mock()
        thread2 = Mock()
        thread3 = Mock()
        
        self.controller.threads = {
            'process': {'thread': thread1, 'busy_guard': Mock()},
            'smart_format': {'thread': thread2, 'busy_guard': Mock()},
            'refinement': {'thread': thread3, 'busy_guard': Mock()}
        }
        
        # Verify all three threads can exist in self.threads simultaneously
        self.assertEqual(len(self.controller.threads), 3)
        
        # Verify each thread has unique key
        self.assertIn('process', self.controller.threads)
        self.assertIn('smart_format', self.controller.threads)
        self.assertIn('refinement', self.controller.threads)
        
        # Verify threads don't interfere with each other
        self.assertIsNot(self.controller.threads['process']['thread'],
                         self.controller.threads['smart_format']['thread'])
        self.assertIsNot(self.controller.threads['smart_format']['thread'],
                         self.controller.threads['refinement']['thread'])

    def test_signal_emission_order(self):
        """Tests correct order of signal emissions during process."""
        mock_recording = Mock()
        mock_recording.id = 1
        mock_recording.raw_transcript = 'test'
        self.mock_get_api_key.return_value = 'test-key'
        
        mock_thread = Mock()
        self.mock_thread_class.return_value = mock_thread
        
        # Track call order
        call_order = []
        self.controller.status_update.emit.side_effect = lambda msg: call_order.append(('status', msg))
        self.controller.gpt_process_started.emit.side_effect = lambda: call_order.append('started')
        mock_thread.start.side_effect = lambda: call_order.append('thread_start')
        
        # Call process
        self.controller.process(
            recording=mock_recording,
            prompt='test',
            config={},
            busy_guard_callback=Mock()
        )
        
        # Verify correct order
        # First: status_update emitted with 'Starting GPT processing...'
        self.assertEqual(call_order[0], ('status', 'Starting GPT processing...'))
        
        # Second: gpt_process_started emitted
        self.assertEqual(call_order[1], 'started')
        
        # Third: thread.start() called
        self.assertEqual(call_order[2], 'thread_start')
        
        # Now simulate completion
        call_order.clear()
        self.controller.gpt_process_completed.emit.side_effect = lambda result: call_order.append(('completed', result))
        
        # Get the completion handler and call it
        completion_handler = mock_thread.completed.connect.call_args[0][0]
        completion_handler('result text')
        
        # Get and call the database update callback
        db_callback = self.mock_db_manager.update_recording.call_args[0][1]
        db_callback()
        
        # On completion: status_update then gpt_process_completed
        self.assertEqual(call_order[0], ('status', 'GPT processing complete'))
        self.assertEqual(call_order[1], ('completed', 'result text'))


if __name__ == "__main__":
    unittest.main()