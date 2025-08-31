"""GPT Controller for handling AI text processing.

Designed to be importable without Qt installed (e.g., CI). We fall back
to minimal stubs when Qt or thread classes are unavailable; tests patch
these symbols as needed.
"""

import logging
from typing import Dict, Any, Optional, Callable, List

# Qt shims: prefer PyQt6, then PySide6, finally minimal stubs
try:  # Prefer PyQt6
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore
except Exception:  # pragma: no cover - exercised in CI without Qt
    try:  # Allow PySide6
        from PySide6.QtCore import QObject, Signal as pyqtSignal  # type: ignore
    except Exception:
        class QObject:  # type: ignore
            def __init__(self, parent=None) -> None:  # Minimal stub
                pass

        def pyqtSignal(*_args, **_kwargs):  # type: ignore
            class _Signal:
                def connect(self, *_a, **_k):
                    pass

                def emit(self, *_a, **_k):
                    pass

            return _Signal()

from app.models.recording import Recording

# Thread class shim: make attribute available even if thread module can't import
try:
    from app.threads.GPT4ProcessingThread import GPT4ProcessingThread  # type: ignore
except Exception:  # pragma: no cover - CI without Qt/requests
    class GPT4ProcessingThread:  # type: ignore
        pass

from app.ThreadManager import ThreadManager
from app.secure import get_api_key

logger = logging.getLogger("transcribrr")


class GPTController(QObject):
    """Controller for handling GPT processing."""

    # Signals
    gpt_process_started = pyqtSignal()
    gpt_process_completed = pyqtSignal(str)  # Emits processed text
    gpt_process_stopped = pyqtSignal()
    status_update = pyqtSignal(str)  # Generic status update signal
    recording_status_updated = pyqtSignal(int, dict)  # Signal for recording updates (ID, data)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.threads = {}  # Store active threads
        # Bind logger at instance-level so tests that patch the module
        # logger during construction can assert calls later.
        self.logger = logger
        # Capture dependencies at construction time so tests that patch them
        # in setUp (and then end the patch) still affect instance behaviour.
        self.get_api_key = get_api_key
        self._Thread = GPT4ProcessingThread

    def process(
        self,
        recording: Recording,
        prompt: str,
        config: Dict[str, Any],
        busy_guard_callback: Callable,
        completion_callback: Optional[Callable] = None,
    ) -> bool:
        """Process a recording with GPT."""
        # Validate inputs
        if not recording or not recording.raw_transcript:
            self.logger.error("No transcript available for GPT processing")
            return False

        if not prompt:
            self.logger.error("No prompt provided for GPT processing")
            return False

        # Get API key
        api_key = self.get_api_key("OPENAI_API_KEY")
        if not api_key:
            self.logger.error("OpenAI API key missing for GPT processing")
            return False

        # Extract config values
        gpt_model = config.get("gpt_model", "gpt-4o")
        max_tokens = config.get("max_tokens", 16000)
        temperature = config.get("temperature", 1.0)

        # Create busy indicator
        busy_guard = busy_guard_callback(
            operation_name="GPT Processing", spinner="gpt_process"
        )

        # Create thread
        thread = self._Thread(
            transcript=recording.raw_transcript,
            prompt_instructions=prompt,
            gpt_model=gpt_model,
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=api_key,
        )

        # Connect signals
        thread.completed.connect(
            lambda result: self._on_process_completed(
                recording, result, completion_callback
            )
        )
        thread.update_progress.connect(self._on_process_progress)
        thread.error.connect(self._on_process_error)
        thread.finished.connect(lambda: self._on_process_finished("process"))

        # Store thread
        self.threads["process"] = {"thread": thread, "busy_guard": busy_guard}

        # Emit signal
        self.status_update.emit("Starting GPT processing...")
        self.gpt_process_started.emit()

        # Start thread
        thread.start()

        return True

    def smart_format(
        self,
        text: str,
        config: Dict[str, Any],
        busy_guard_callback: Callable,
        completion_callback: Optional[Callable] = None,
    ) -> bool:
        """Format text with GPT for display."""
        # Validate inputs
        if not text:
            self.logger.error("No text provided for smart formatting")
            return False

        # Get API key
        api_key = self.get_api_key("OPENAI_API_KEY")
        if not api_key:
            self.logger.error("OpenAI API key missing for smart formatting")
            return False

        # Use cheaper model with lower temperature for format task
        gpt_model = "gpt-4o-mini"
        temperature = 0.3

        # Create busy indicator
        busy_guard = busy_guard_callback(
            operation_name="Smart Formatting", spinner="smart_format"
        )

        # Create formatting prompt
        prompt = (
            "Format the following text using HTML for better readability. "
            "Add appropriate paragraph breaks, emphasis, and structure. "
            "Do not change the actual content or meaning of the text. "
            "Use basic HTML tags like <p>, <strong>, <em>, <h3>, <ul>, <li> etc. "
            "Here is the text to format:"
        )

        # Create thread
        thread = self._Thread(
            transcript=text,
            prompt_instructions=prompt,
            gpt_model=gpt_model,
            max_tokens=16000,
            temperature=temperature,
            openai_api_key=api_key,
        )

        # Connect signals
        thread.completed.connect(
            lambda result: self._on_format_completed(result, completion_callback)
        )
        thread.update_progress.connect(self._on_process_progress)
        thread.error.connect(self._on_process_error)
        thread.finished.connect(lambda: self._on_process_finished("smart_format"))

        # Store thread
        self.threads["smart_format"] = {"thread": thread, "busy_guard": busy_guard}

        # Emit signal
        self.status_update.emit("Formatting text...")

        # Start thread
        thread.start()

        return True

    def refine(
        self,
        recording: Recording,
        refinement_instructions: str,
        initial_prompt: str,
        current_text: str,
        config: Dict[str, Any],
        busy_guard_callback: Callable,
        completion_callback: Optional[Callable] = None,
    ) -> bool:
        """Refine existing processed text with new instructions."""
        # Validate inputs
        if not recording or not recording.raw_transcript:
            self.logger.error("No transcript available for refinement")
            return False

        if not refinement_instructions:
            self.logger.error("No refinement instructions provided")
            return False

        if not current_text:
            self.logger.error("No current text provided for refinement")
            return False

        # Get API key
        api_key = self.get_api_key("OPENAI_API_KEY")
        if not api_key:
            self.logger.error("OpenAI API key missing for refinement")
            return False

        # Extract config values
        gpt_model = config.get("gpt_model", "gpt-4o")
        max_tokens = config.get("max_tokens", 16000)
        temperature = config.get("temperature", 1.0)

        # Create busy indicator
        busy_guard = busy_guard_callback(
            operation_name="Text Refinement", spinner="refinement"
        )

        # Create message format for refinement
        system_prompt = (
            f"You are an expert at refining text. "
            f"Your task is to refine the previous output according to these instructions: "
            f"{refinement_instructions}\n\n"
            f"Original prompt was: {initial_prompt}"
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here is the transcript:\n\n{recording.raw_transcript}"},
            {"role": "assistant", "content": current_text},
            {"role": "user", "content": refinement_instructions},
        ]

        # Create thread
        thread = self._Thread(
            transcript=recording.raw_transcript,
            prompt_instructions=refinement_instructions,
            messages=messages,
            gpt_model=gpt_model,
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=api_key,
        )

        # Connect signals
        thread.completed.connect(
            lambda result: self._on_refinement_completed(
                recording, result, completion_callback
            )
        )
        thread.update_progress.connect(self._on_process_progress)
        thread.error.connect(self._on_process_error)
        thread.finished.connect(lambda: self._on_process_finished("refinement"))

        # Store thread
        self.threads["refinement"] = {"thread": thread, "busy_guard": busy_guard}

        # Emit signal
        self.status_update.emit("Refining text...")

        # Start thread
        thread.start()

        return True

    def _on_process_completed(
        self,
        recording: Recording,
        result: str,
        completion_callback: Optional[Callable] = None,
    ) -> None:
        """Handle completed GPT processing."""
        if not recording:
            return

        recording_id = recording.id

        # Define callback for when database update completes
        def on_update_complete():
            # Emit signals
            self.status_update.emit("GPT processing complete")
            self.gpt_process_completed.emit(result)

            # Call completion callback if provided
            if completion_callback:
                completion_callback(result)

        # Save processed text to database
        self.db_manager.update_recording(
            recording_id, on_update_complete, processed_text=result
        )

    def _on_format_completed(
        self, result: str, completion_callback: Optional[Callable] = None
    ) -> None:
        """Handle completed smart formatting."""
        # Emit signals
        self.status_update.emit("Formatting complete")

        # Call completion callback if provided
        if completion_callback:
            completion_callback(result)

    def _on_refinement_completed(
        self,
        recording: Recording,
        result: str,
        completion_callback: Optional[Callable] = None,
    ) -> None:
        """Handle completed refinement."""
        if not recording:
            return

        recording_id = recording.id

        # Define callback for when database update completes
        def on_update_complete():
            # Emit signals
            self.status_update.emit("Refinement complete")

            # Call completion callback if provided
            if completion_callback:
                completion_callback(result)

        # Only update processed_text, keep raw transcript
        self.db_manager.update_recording(
            recording_id, on_update_complete, processed_text=result
        )

    def _on_process_progress(self, message: str) -> None:
        """Handle progress updates from GPT thread."""
        self.status_update.emit(message)

    def _on_process_error(self, error_message: str) -> None:
        """Handle GPT processing errors."""
        self.status_update.emit(f"GPT processing failed: {error_message}")

    def _on_process_finished(self, thread_key: str) -> None:
        """Called when GPT thread finishes, regardless of success."""
        # Clean up thread reference
        if thread_key in self.threads:
            del self.threads[thread_key]

        self.logger.info(f"GPT thread ({thread_key}) finished.")

    def cancel(self, thread_key: str = "process") -> None:
        """Cancel current GPT processing if running."""
        if thread_key in self.threads:
            thread_info = self.threads[thread_key]
            thread = thread_info["thread"]
            if thread and thread.isRunning():
                self.logger.info(f"Canceling {thread_key} thread...")
                thread.cancel()
                self.status_update.emit(f"Canceling {thread_key}...")
