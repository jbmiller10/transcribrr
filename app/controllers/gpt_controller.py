"""GPTController for handling GPT processing operations."""

import logging
import os
from typing import Dict, Any, Optional, Callable, List, Union

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.recording import Recording
from app.models.view_mode import ViewMode
from app.ui_utils.busy_guard import BusyGuard
from app.threads.GPT4ProcessingThread import GPT4ProcessingThread
from app.ThreadManager import ThreadManager
from app.secure import get_api_key
from app.constants import ERROR_API_KEY_MISSING, SUCCESS_GPT_PROCESSING

logger = logging.getLogger('transcribrr')


class GPTController(QObject):
    """Controller for handling GPT processing operations."""

    # Signals
    gpt_process_started = pyqtSignal()
    gpt_process_completed = pyqtSignal(str)  # Emits final processed text
    status_update = pyqtSignal(str)  # Generic status update signal
    recording_status_updated = pyqtSignal(int, dict)  # Signal for recording updates (ID, data)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.threads = {}  # Store references to active threads

    def process(self, recording: Recording, prompt_instructions: str, config: Dict[str, Any],
                busy_guard_callback: Callable, completion_callback: Optional[Callable] = None) -> bool:
        """
        Process a recording with GPT.

        Args:
            recording: The Recording object to process
            prompt_instructions: Instructions for GPT processing
            config: Configuration dictionary
            busy_guard_callback: Function that returns a BusyGuard instance
            completion_callback: Optional callback when processing completes successfully

        Returns:
            bool: True if started successfully, False otherwise
        """
        # Verify we have a transcript
        if not recording or not recording.has_raw():
            return False

        # Verify the prompt
        if not prompt_instructions.strip():
            return False

        # Build thread arguments
        thread_args = {
            'transcript': recording.raw_transcript,
            'prompt_instructions': prompt_instructions,
            'gpt_model': config.get('gpt_model', 'gpt-4o'),
            'max_tokens': config.get('max_tokens', 16000),
            'temperature': config.get('temperature', 1.0),
            'openai_api_key': get_api_key("OPENAI_API_KEY"),
        }

        # Verify API key
        if not thread_args['openai_api_key']:
            return False

        # Launch the thread
        busy_guard_config = {
            'operation_name': "GPT Processing",
            'spinner': 'gpt_process',
            'progress': True,
            'progress_title': "GPT Processing",
            'progress_message': f"Processing with {thread_args['gpt_model']}...",
            'progress_maximum': 0,  # Indeterminate
            'progress_cancelable': True,
            'cancel_callback': lambda: self.cancel('process'),
            'status_message': f"Starting GPT processing with {thread_args['gpt_model']}..."
        }

        # Define completion handler that updates the database
        def on_completion(processed_text):
            is_html = "<" in processed_text and ">" in processed_text
            db_value = processed_text

            def on_update_complete():
                # Update statuses and emit signals
                self.status_update.emit(SUCCESS_GPT_PROCESSING)
                self.gpt_process_completed.emit(processed_text)

                # Emit signal for other UI components
                status_updates = {
                    'has_processed': True,
                    'processed_text': processed_text,
                    'processed_text_formatted': db_value if is_html else None
                }
                self.recording_status_updated.emit(recording.id, status_updates)

                # Call the completion callback if provided
                if completion_callback:
                    completion_callback(processed_text, is_html)

            # Save to database
            update_data = {'processed_text': processed_text}
            if is_html:
                update_data['processed_text_formatted'] = db_value
            else:
                update_data['processed_text_formatted'] = None

            self.db_manager.update_recording(recording.id, on_update_complete, **update_data)

        # Start the thread
        return self._launch('process', thread_args, busy_guard_callback,
                            busy_guard_config, on_completion)

    def smart_format(self, text_to_format: str, config: Dict[str, Any],
                     busy_guard_callback: Callable, completion_callback: Optional[Callable] = None) -> bool:
        """
        Apply smart formatting to text.

        Args:
            text_to_format: Text to format
            config: Configuration dictionary
            busy_guard_callback: Function that returns a BusyGuard instance
            completion_callback: Optional callback when formatting completes successfully

        Returns:
            bool: True if started successfully, False otherwise
        """
        # Verify input
        if not text_to_format.strip():
            return False

        # Use a specialized prompt for formatting
        prompt_instructions = "Format the following text using HTML for readability (e.g., paragraphs, lists, bolding). Do not change the content. Output only the HTML."

        # Build thread arguments
        thread_args = {
            'transcript': text_to_format,
            'prompt_instructions': prompt_instructions,
            'gpt_model': 'gpt-4o-mini',  # Use cheaper model for formatting
            'max_tokens': config.get('max_tokens', 16000),
            'temperature': 0.3,  # Lower temperature for formatting
            'openai_api_key': get_api_key("OPENAI_API_KEY"),
        }

        # Verify API key
        if not thread_args['openai_api_key']:
            return False

        # Launch the thread
        busy_guard_config = {
            'operation_name': "Smart Formatting",
            'spinner': 'smart_format',
            'progress': True,
            'progress_title': "Smart Formatting",
            'progress_message': f"Formatting with {thread_args['gpt_model']}...",
            'progress_maximum': 0,  # Indeterminate
            'progress_cancelable': True,
            'cancel_callback': lambda: self.cancel('smart_format'),
            'status_message': f"Starting smart formatting with {thread_args['gpt_model']}..."
        }

        # Define simple completion handler
        def on_completion(formatted_text):
            self.status_update.emit("Smart formatting applied.")
            self.gpt_process_completed.emit(formatted_text)

            # Call the completion callback if provided
            if completion_callback:
                is_html = "<" in formatted_text and ">" in formatted_text
                completion_callback(formatted_text, is_html)

        # Start the thread
        return self._launch('smart_format', thread_args, busy_guard_callback,
                            busy_guard_config, on_completion)

    def refine(self, recording: Recording, refinement_instructions: str,
               initial_prompt: str, processed_text: str, config: Dict[str, Any],
               busy_guard_callback: Callable, completion_callback: Optional[Callable] = None) -> bool:
        """
        Refine previously processed text.

        Args:
            recording: The Recording object with raw transcript
            refinement_instructions: User's refinement instructions
            initial_prompt: Original prompt used for processing
            processed_text: Previously processed text to refine
            config: Configuration dictionary
            busy_guard_callback: Function that returns a BusyGuard instance
            completion_callback: Optional callback when refinement completes successfully

        Returns:
            bool: True if started successfully, False otherwise
        """
        # Validate inputs
        if (not recording or not recording.raw_transcript or
                not refinement_instructions.strip() or not processed_text.strip()):
            return False

        # Prepare conversational messages for refinement
        system_prompt = (
            f"You are an AI assistant refining previously processed text. "
            f"The original text was processed with the prompt: '{initial_prompt}'. "
            f"Now, apply the following refinement instructions: '{refinement_instructions}'. "
            f"Maintain the original HTML formatting if present in the 'assistant' message. "
            f"Output only the fully refined text, including necessary HTML tags if the input had them."
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f"Original Transcript:\n{recording.raw_transcript}"},
            {'role': 'assistant', 'content': processed_text},
            {'role': 'user', 'content': refinement_instructions}
        ]

        # Build thread arguments
        thread_args = {
            'transcript': "",  # Not directly used with messages
            'prompt_instructions': "",  # Not directly used with messages
            'gpt_model': config.get('gpt_model', 'gpt-4o'),
            'max_tokens': config.get('max_tokens', 16000),
            'temperature': config.get('temperature', 1.0),
            'openai_api_key': get_api_key("OPENAI_API_KEY"),
            'messages': messages
        }

        # Verify API key
        if not thread_args['openai_api_key']:
            return False

        # Launch the thread
        busy_guard_config = {
            'operation_name': "Text Refinement",
            'spinner': 'refinement',
            'progress': True,
            'progress_title': "Text Refinement",
            'progress_message': "Applying refinement instructions...",
            'progress_maximum': 0,  # Indeterminate
            'progress_cancelable': True,
            'cancel_callback': lambda: self.cancel('refinement'),
            'status_message': "Starting refinement processing..."
        }

        # Define completion handler that updates the database
        def on_completion(refined_text):
            is_html = "<" in refined_text and ">" in refined_text
            db_value = refined_text

            def on_update_complete():
                # Update statuses and emit signals
                self.status_update.emit("Refinement saved.")
                self.gpt_process_completed.emit(refined_text)

                # Emit signal for other UI components
                status_updates = {
                    'has_processed': True,
                    'processed_text': refined_text,
                    'processed_text_formatted': db_value if is_html else None
                }
                self.recording_status_updated.emit(recording.id, status_updates)

                # Call the completion callback if provided
                if completion_callback:
                    completion_callback(refined_text, is_html)

            # Save to database
            update_data = {'processed_text': refined_text}
            if is_html:
                update_data['processed_text_formatted'] = db_value
            else:
                update_data['processed_text_formatted'] = None

            self.db_manager.update_recording(recording.id, on_update_complete, **update_data)

        # Start the thread
        return self._launch('refinement', thread_args, busy_guard_callback,
                            busy_guard_config, on_completion)

    def _launch(self, thread_id: str, thread_args: Dict[str, Any],
                busy_guard_callback: Callable, busy_guard_config: Dict[str, Any],
                completion_handler: Callable) -> bool:
        """
        Launch a GPT thread with UI feedback.

        Args:
            thread_id: Identifier for the thread
            thread_args: Arguments to pass to GPT4ProcessingThread
            busy_guard_callback: Function that returns a BusyGuard instance
            busy_guard_config: Configuration for the BusyGuard
            completion_handler: Handler for successful completion

        Returns:
            bool: True if thread started successfully
        """
        # Create and initialize the thread
        thread = GPT4ProcessingThread(**thread_args)

        # Create the BusyGuard for UI feedback
        busy_guard = busy_guard_callback(**busy_guard_config)

        # Store thread reference
        self.threads[thread_id] = {
            'thread': thread,
            'busy_guard': busy_guard
        }

        # Define progress handler
        def on_progress(message):
            self.status_update.emit(message)

        # Define error handler
        def on_error(error_message):
            self.status_update.emit(f"Processing failed: {error_message}")

            # Exit the BusyGuard context
            busy_guard.__exit__(Exception, ValueError(error_message), None)

        # Define finished handler
        def on_finished():
            # Update UI state
            busy_guard.__exit__(None, None, None)

            # Clean up thread reference
            if thread_id in self.threads:
                del self.threads[thread_id]

            # Log completion
            logger.info(f"GPT thread '{thread_id}' finished")

            # Reset UI status
            self.status_update.emit("Ready")

        # Connect thread signals
        thread.completed.connect(completion_handler)
        thread.update_progress.connect(on_progress)
        thread.error.connect(on_error)
        thread.finished.connect(on_finished)

        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(thread)

        # Start the thread
        thread.start()

        # Emit signal
        self.gpt_process_started.emit()

        return True

    def cancel(self, thread_id: str) -> None:
        """Cancel a running GPT thread."""
        if thread_id in self.threads and 'thread' in self.threads[thread_id]:
            thread = self.threads[thread_id]['thread']
            if thread and thread.isRunning():
                logger.info(f"Canceling GPT thread '{thread_id}'")
                thread.cancel()
                self.status_update.emit(f"Canceling {thread_id} operation...")
