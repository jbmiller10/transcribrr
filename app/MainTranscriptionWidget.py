import os
import torch
import logging
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QPushButton,
    QLineEdit,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal, QSize, Qt, QTimer

from app.models.recording import Recording
from app.models.view_mode import ViewMode
from app.ui_utils.busy_guard import BusyGuard

from app.TextEditor import TextEditor
from app.SettingsDialog import SettingsDialog
from app.ToggleSwitch import ToggleSwitch
from app.DatabaseManager import DatabaseManager
from app.ResponsiveUI import ResponsiveWidget, ResponsiveSizePolicy
from app.ui_utils import (
    SpinnerManager,
    FeedbackManager,
    show_error_message,
    show_info_message,
)
from app.file_utils import is_valid_media_file, check_file_size
from app.path_utils import resource_path
from app.utils import ConfigManager, PromptManager
from app.ThreadManager import ThreadManager
from app.widgets import PromptBar
from app.controllers import TranscriptionController, GPTController
from app.constants import (
    ERROR_INVALID_FILE,
    ERROR_API_KEY_MISSING,
    SUCCESS_TRANSCRIPTION,
    SUCCESS_GPT_PROCESSING,
)

logger = logging.getLogger("transcribrr")


class MainTranscriptionWidget(ResponsiveWidget):
    # Transcription and GPT workflow signals
    transcription_process_started = pyqtSignal()
    transcription_process_completed = pyqtSignal(
        str)  # Emits final transcript text
    transcription_process_stopped = pyqtSignal()
    gpt_process_started = pyqtSignal()
    gpt_process_completed = pyqtSignal(str)  # Emits final processed text
    save_operation_completed = pyqtSignal(str)  # Emits status message
    status_update = pyqtSignal(str)  # Generic status update signal
    recording_status_updated = pyqtSignal(
        int, dict
    )  # Signal for recording updates (ID, data)

    # Internal state for selected recording

    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.setSizePolicy(ResponsiveSizePolicy.expanding())

        # Managers
        self.db_manager = db_manager or DatabaseManager(self)
        self.config_manager = ConfigManager.instance()
        self.prompt_manager = PromptManager.instance()

        # UI feedback managers
        self.spinner_manager = SpinnerManager(
            self)  # For backward compatibility
        self.feedback_manager = FeedbackManager(
            self)  # Centralized feedback management

        # Controllers
        self.transcription_controller = TranscriptionController(
            self.db_manager, self)
        self.gpt_controller = GPTController(self.db_manager, self)

        # State variables
        # self.file_path = None # Stored within current_recording_data
        self.is_transcribing = False
        self.is_processing_gpt4 = False
        self.current_recording_data = None  # Store full data of selected item
        self.initial_prompt_instructions = (
            None  # Store prompt used for initial processing
        )
        self.last_processed_text_html = None  # Store the last HTML processed text
        self.view_mode = ViewMode.RAW  # Store current view mode

        # Load initial configuration for GPT params (others loaded on demand)
        self._load_gpt_params_from_config()

        # UI Initialization - Create UI elements first before connecting signals or using them
        # Initialize all UI components - first create controls, then add to main content
        self.init_top_toolbar()  # Create the controls first
        self.init_main_content()  # Use the controls in the main content

        # Connect signals after UI is fully initialized
        self.connect_signals()

        # Connect to manager signals
        self.config_manager.config_updated.connect(self.handle_config_update)

        # Connect controller signals
        self._connect_controller_signals()

    def _load_gpt_params_from_config(self):
        """Load only GPT parameters initially."""
        self.gpt_temperature = self.config_manager.get("temperature", 1.0)
        self.gpt_max_tokens = self.config_manager.get("max_tokens", 16000)

    def handle_config_update(self, changed_config):
        """Handle updates pushed from ConfigManager."""
        logger.debug(f"Config updated: {changed_config}")
        # Update relevant internal state if needed
        if "temperature" in changed_config:
            self.gpt_temperature = changed_config["temperature"]
        if "max_tokens" in changed_config:
            self.gpt_max_tokens = changed_config["max_tokens"]
        # Add checks for other relevant config keys if necessary

    def _connect_controller_signals(self):
        """Connect signals from controllers to our signals and UI."""
        # Transcription controller signals
        self.transcription_controller.transcription_process_started.connect(
            self.transcription_process_started
        )
        self.transcription_controller.transcription_process_completed.connect(
            self.transcription_process_completed
        )
        self.transcription_controller.transcription_process_stopped.connect(
            self.transcription_process_stopped
        )
        self.transcription_controller.status_update.connect(self.status_update)
        self.transcription_controller.recording_status_updated.connect(
            self.recording_status_updated
        )

        # GPT controller signals
        self.gpt_controller.gpt_process_started.connect(
            self.gpt_process_started)
        self.gpt_controller.gpt_process_completed.connect(
            self.gpt_process_completed)
        self.gpt_controller.status_update.connect(self.status_update)
        self.gpt_controller.recording_status_updated.connect(
            self.recording_status_updated
        )

    def connect_signals(self):
        # Connect signals for TextEditor
        self.transcript_text.transcription_requested.connect(
            self.start_transcription)
        self.transcript_text.gpt4_processing_requested.connect(
            self.start_gpt4_processing
        )
        self.transcript_text.smart_format_requested.connect(
            self.start_smart_format_processing
        )
        self.transcript_text.save_requested.connect(self.save_editor_state)

        # Expose our status update signals to TextEditor's status bar
        # This fixes the "Cannot show status message" warnings
        self.status_update.connect(
            lambda msg: self.transcript_text.show_status_message(msg)
        )

        # Connect toolbar signals
        self.mode_switch.valueChanged.connect(self.on_mode_switch_changed)
        self.settings_button.clicked.connect(
            self.open_settings_dialog)  # Direct call
        self.prompt_bar.instruction_changed.connect(
            self.on_prompt_instructions_changed)
        self.refinement_submit_button.clicked.connect(
            self.start_refinement_processing)

    def init_top_toolbar(self):
        # Create the elements but do not add them to layout here
        # They will be added directly to the editor widget in init_main_content

        # Create the PromptBar component
        self.prompt_bar = PromptBar(self)

        self.raw_transcript_label = QLabel("Raw")
        self.mode_switch = ToggleSwitch()
        self.mode_switch.setValue(ViewMode.RAW)  # Default to raw
        self.gpt_processed_label = QLabel("Processed")

        self.settings_button = QPushButton()
        self.settings_button.setIcon(
            QIcon(resource_path("icons/settings.svg")))
        self.settings_button.setToolTip("Open Settings")
        self.settings_button.setIconSize(QSize(18, 18))
        self.settings_button.setFixedSize(28, 28)

    def init_main_content(self):
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.main_splitter)

        # --- Main Content Widget ---
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)

        # Editor widget with its own controls above
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(5)

        # Control bar above the editor
        control_bar = QHBoxLayout()
        # Add the prompt bar with stretch
        control_bar.addWidget(self.prompt_bar, 1)
        control_bar.addStretch(1)
        control_bar.addWidget(self.raw_transcript_label)
        control_bar.addWidget(self.mode_switch)
        control_bar.addWidget(self.gpt_processed_label)
        control_bar.addStretch(1)
        control_bar.addWidget(self.settings_button)
        editor_layout.addLayout(control_bar)

        # Add some padding above the text editor (spacing without the controls)
        editor_layout.addSpacing(10)

        # Main text editor - now with integrated transcription actions in its toolbar
        self.transcript_text = TextEditor()  # The rich text editor
        editor_layout.addWidget(self.transcript_text)

        # Register spinners for toolbar buttons
        self.spinner_manager.create_spinner(
            name="transcribe",
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path("./icons/transcribe.svg"),
            action_tooltip="Start Transcription",
            callback=self.transcript_text.start_transcription,
        )

        self.spinner_manager.create_spinner(
            name="gpt_process",
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path("./icons/magic_wand.svg"),
            action_tooltip="Process with GPT-4",
            callback=self.transcript_text.process_with_gpt4,
        )

        self.spinner_manager.create_spinner(
            name="smart_format",
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path("./icons/smart_format.svg"),
            action_tooltip="Smart Format",
            callback=self.transcript_text.smart_format_text,
        )

        self.spinner_manager.create_spinner(
            name="refinement",
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path("./icons/quill.svg"),
            action_tooltip="Refine Text",
            callback=self.start_refinement_processing,
        )

        # Add the editor widget to the main content layout
        content_layout.addWidget(editor_widget)

        # --- Refinement Input Area ---
        self.refinement_widget = QWidget()
        refinement_layout = QHBoxLayout(self.refinement_widget)
        refinement_layout.setContentsMargins(0, 5, 0, 0)
        self.refinement_input = QLineEdit()
        self.refinement_input.setPlaceholderText(
            "Enter refinement instructions (e.g., 'Make it more formal')..."
        )
        self.refinement_submit_button = QPushButton("Refine")
        refinement_layout.addWidget(self.refinement_input, 1)
        refinement_layout.addWidget(self.refinement_submit_button)
        content_layout.addWidget(self.refinement_widget)
        self.refinement_widget.setVisible(False)  # Hidden by default

        # --- Add Widget to Splitter ---
        self.main_splitter.addWidget(self.content_widget)

    # Temperature and max tokens settings have been moved to SettingsDialog only

    # --- Thread Management Helpers ---

    def _launch_thread(
        self,
        thread,
        completion_handler,
        progress_handler,
        error_handler,
        finished_handler,
        thread_attr_name=None,
    ):
        """
        Launch a thread with standardized signal connections and registration.

        Args:
            thread: The QThread instance to launch
            completion_handler: Function to connect to thread's completed signal
            progress_handler: Function to connect to thread's update_progress signal
            error_handler: Function to connect to thread's error signal
            finished_handler: Function to connect to thread's finished signal
            thread_attr_name: String name of attribute to store thread instance on self
        """
        # Connect signals
        thread.completed.connect(completion_handler)
        thread.update_progress.connect(progress_handler)
        thread.error.connect(error_handler)
        thread.finished.connect(finished_handler)

        # Store thread reference if attribute name provided
        if thread_attr_name:
            setattr(self, thread_attr_name, thread)

        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(thread)

        # Start the thread
        thread.start()

        return thread

    # --- Processing Logic ---

    def start_transcription(self):
        """Start the transcription process using the TranscriptionController."""
        if not self.current_recording_data:
            show_error_message(
                self,
                "No Recording Selected",
                "Please select a recording to transcribe.",
            )
            return

        # Convert dictionary to Recording object if needed
        recording = self.current_recording_data
        if not isinstance(recording, Recording):
            recording = Recording(
                id=recording["id"],
                filename=recording["filename"],
                file_path=recording["file_path"],
                date_created=recording.get("date_created"),
                duration=recording.get("duration"),
                raw_transcript=recording.get("raw_transcript"),
                processed_text=recording.get("processed_text"),
                raw_transcript_formatted=recording.get(
                    "raw_transcript_formatted"),
                processed_text_formatted=recording.get(
                    "processed_text_formatted"),
                original_source_identifier=recording.get(
                    "original_source_identifier"),
            )

        # Mark UI as busy
        self.is_transcribing = True
        ui_elements = self.get_transcription_ui_elements()

        # Create BusyGuard and start transcription
        def create_busy_guard():
            guard = BusyGuard(
                self.feedback_manager,
                "Transcription",
                ui_elements=ui_elements,
                spinner="transcribe",
                progress=True,
                progress_title="Transcription Progress",
                progress_message=f"Transcribing {os.path.basename(recording.file_path)}...",
                progress_maximum=100,
                progress_cancelable=True,
                cancel_callback=lambda: self.transcription_controller.cancel(),
                status_message="Starting transcription...",
            )
            self.transcription_guard = guard
            self.transcription_guard.__enter__()
            return guard

        # Start transcription and handle potential failure
        if not self.transcription_controller.start(
            recording, self.config_manager.get_all(), create_busy_guard
        ):
            self.is_transcribing = False
            self.transcription_guard.__exit__(None, None, None)
            delattr(self, "transcription_guard")

    def _busy_elements_for(self, *operations):
        """
        Return UI elements to disable for given operation IDs.

        Args:
            *operations: Operation identifiers ('transcribe', 'gpt', 'smart_format', 'refinement')
                         that determine which UI elements should be disabled.

        Returns:
            list[QObject]: List of UI elements to disable during the operations.

        Note:
            When adding new toolbar actions or UI elements that need to be disabled
            during specific operations, update the appropriate mapping dictionaries
            in this method.
        """
        elements = []

        # Settings button is always disabled during any operation
        elements.append(self.settings_button)

        # Toolbar actions to disable per operation type
        # This maps operation types to the toolbar action keys that should be disabled
        toolbar_action_map = {
            "transcribe": ["start_transcription", "process_with_gpt4", "smart_format"],
            "gpt": [
                "start_transcription",
                "process_with_gpt4",
                "smart_format",
                "quill",
            ],
            "smart_format": [
                "start_transcription",
                "process_with_gpt4",
                "smart_format",
                "quill",
            ],
            "refinement": [
                "start_transcription",
                "process_with_gpt4",
                "smart_format",
                "quill",
            ],
        }

        # Additional UI widgets to disable per operation type
        widget_map = {
            "transcribe": [],
            "gpt": [self.prompt_bar],
            "smart_format": [self.prompt_bar],
            "refinement": [
                self.prompt_bar,
                self.refinement_input,
                self.refinement_submit_button,
            ],
        }

        # Add operation-specific toolbar actions
        toolbar_actions = self.transcript_text._toolbar_actions
        for op in operations:
            for key in toolbar_action_map.get(op, []):
                action = toolbar_actions.get(key)
                if action and action not in elements:
                    elements.append(action)

            # Add operation-specific widgets
            for widget in widget_map.get(op, []):
                if widget not in elements:
                    elements.append(widget)

        return elements

    def get_transcription_ui_elements(self):
        """Get UI elements to disable during transcription."""
        return self._busy_elements_for("transcribe")

    def cancel_transcription(self):
        """Cancel an ongoing transcription operation."""
        logger.info("User requested cancellation of transcription")
        self.transcription_controller.cancel()
        self.feedback_manager.show_status("Cancelling transcription...")

    def on_transcription_progress(self, message):
        """Handle progress updates from transcription thread."""
        # This is now primarily handled by the controller, but we can still
        # extract progress information for the BusyGuard if needed

        # Extract progress information if available - for example, "Processing chunk 2/5..."
        if "chunk" in message.lower() and "/" in message:
            try:
                parts = message.split()
                for part in parts:
                    if "/" in part:
                        current, total = map(int, part.strip(".,").split("/"))
                        # Update progress using the BusyGuard instance
                        self.transcription_guard.update_progress(
                            int(current * 100 / total), message
                        )
                        return
            except (ValueError, IndexError):
                pass  # If parsing fails, treat as indeterminate

        # For messages without specific progress percentage, just update the message
        self.transcription_guard.update_progress(
            0, message  # Keep current progress value
        )

    def on_transcription_completed(self, transcript):
        """Handle transcription completion - update UI only."""
        if not self.current_recording_data:
            return  # Recording deselected during process

        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner("transcribe")

        # Check if result contains speaker labels
        is_formatted = (
            transcript.strip().startswith(
                "SPEAKER_") and ":" in transcript[:20]
        )

        # Update the editor with the transcript
        if is_formatted:
            self.transcript_text.editor.setHtml(f"<pre>{transcript}</pre>")
        else:
            self.transcript_text.editor.setPlainText(transcript)

        # Update view mode
        self.mode_switch.setValue(ViewMode.RAW)
        self.view_mode = ViewMode.RAW

        # Hide refinement widget
        self.refinement_widget.setVisible(False)

    def on_transcription_error(self, error_message):
        """Display transcription error to user."""
        # Show error message to user
        show_error_message(self, "Transcription Error", error_message)

        # Exit BusyGuard context to clean up UI state
        self.transcription_guard.__exit__(
            Exception, ValueError(error_message), None)
        delattr(self, "transcription_guard")

    def on_transcription_finished(self):
        """Called when transcription finishes, regardless of success."""
        # Update state flags and UI
        self.is_transcribing = False
        self.update_ui_state()

        # Clean up BusyGuard
        self.transcription_guard.__exit__(None, None, None)
        delattr(self, "transcription_guard")

    def start_gpt4_processing(self):
        """Process current transcript with GPT using the current prompt."""
        if not self.current_recording_data:
            show_error_message(
                self, "No Recording Selected", "Please select a recording first."
            )
            return

        # Check for transcript
        if not self.current_recording_data.get("raw_transcript"):
            show_error_message(
                self,
                "No Transcript",
                "No transcript available for processing. Please transcribe first.",
            )
            return

        # Get prompt instructions
        self.initial_prompt_instructions = self.get_current_prompt_instructions()
        if not self.initial_prompt_instructions.strip():
            show_error_message(self, "No Prompt",
                               "Please select or enter a prompt.")
            return

        # Convert to Recording object if needed
        recording = self.current_recording_data
        if not isinstance(recording, Recording):
            recording = Recording(
                id=recording["id"],
                filename=recording["filename"],
                file_path=recording["file_path"],
                date_created=recording.get("date_created"),
                duration=recording.get("duration"),
                raw_transcript=recording.get("raw_transcript"),
                processed_text=recording.get("processed_text"),
                raw_transcript_formatted=recording.get(
                    "raw_transcript_formatted"),
                processed_text_formatted=recording.get(
                    "processed_text_formatted"),
            )

        # Mark as processing
        self.is_processing_gpt4 = True

        # Get UI elements to disable during processing
        ui_elements = self._busy_elements_for("gpt")

        # Create BusyGuard callback
        def create_busy_guard(
            operation_name,
            spinner,
            progress,
            progress_title,
            progress_message,
            progress_maximum,
            progress_cancelable,
            cancel_callback,
            status_message,
        ):
            guard = BusyGuard(
                self.feedback_manager,
                operation_name,
                ui_elements=ui_elements,
                spinner=spinner,
                progress=progress,
                progress_title=progress_title,
                progress_message=progress_message,
                progress_maximum=progress_maximum,
                progress_cancelable=progress_cancelable,
                cancel_callback=cancel_callback,
                status_message=status_message,
            )
            self.gpt_guard = guard
            self.gpt_guard.__enter__()
            return guard

        # Define completion callback
        def on_completion(processed_text, is_html):
            # Switch to processed view
            self.mode_switch.setValue(ViewMode.PROCESSED)
            self.view_mode = ViewMode.PROCESSED

            # Update editor with processed text
            if is_html:
                self.transcript_text.editor.setHtml(processed_text)
                self.last_processed_text_html = processed_text
            else:
                self.transcript_text.editor.setPlainText(processed_text)
                self.last_processed_text_html = None

            # Show refinement widget
            self.refinement_widget.setVisible(True)

        # Start processing with controller
        success = self.gpt_controller.process(
            recording=recording,
            prompt_instructions=self.initial_prompt_instructions,
            config=self.config_manager.get_all(),
            busy_guard_callback=create_busy_guard,
            completion_callback=on_completion,
        )

        # Handle failure
        if not success:
            self.is_processing_gpt4 = False
            self.gpt_guard.__exit__(None, None, None)
            delattr(self, "gpt_guard")

    def get_gpt_ui_elements(self):
        """Get UI elements to disable during GPT processing."""
        return self._busy_elements_for("gpt")

    def cancel_gpt_processing(self):
        """Cancel an ongoing GPT processing operation."""
        logger.info("User requested cancellation of GPT processing")
        self.gpt_controller.cancel("process")
        self.feedback_manager.show_status("Cancelling GPT processing...")

    def on_gpt_progress(self, message):
        """Handle progress updates from GPT thread."""
        # Update status bar
        self.status_update.emit(message)

        # Update progress dialog
        self.feedback_manager.update_progress(
            self.gpt_progress_id, 0, message  # Still indeterminate
        )

    def on_gpt4_processing_completed(self, processed_text):
        if not self.current_recording_data:
            return  # No recording selected
        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner("gpt_process")

        recording_id = self.current_recording_data["id"]
        formatted_field = "processed_text_formatted"
        raw_field = "processed_text"

        # Preserve formatting if the result looks like HTML
        is_html = "<" in processed_text and ">" in processed_text
        if is_html:
            self.transcript_text.editor.setHtml(processed_text)
            db_value = processed_text
            self.last_processed_text_html = db_value  # Store for refinement
        else:
            self.transcript_text.editor.setPlainText(processed_text)
            db_value = processed_text
            self.last_processed_text_html = None  # Not HTML

        # Switch to processed view
        self.mode_switch.setValue(ViewMode.PROCESSED)
        self.view_mode = ViewMode.PROCESSED  # Keep view_mode in sync with switch
        self.status_update.emit("GPT processing complete. Saving...")

        # Define callback for DB update
        def on_update_complete():
            # Update local data
            self.current_recording_data[raw_field] = processed_text
            self.current_recording_data[formatted_field] = db_value if is_html else None
            self.status_update.emit(SUCCESS_GPT_PROCESSING)
            self.gpt_process_completed.emit(processed_text)  # Emit signal
            self.refinement_widget.setVisible(True)  # Show refinement options
            logger.info(
                f"GPT processing saved for recording ID: {recording_id}")

            # Emit signal to update UI in other components
            status_updates = {
                "has_processed": True,
                raw_field: processed_text,
                formatted_field: db_value if is_html else None,
            }
            self.recording_status_updated.emit(recording_id, status_updates)

        # Save processed text to DB
        update_data = {raw_field: processed_text}
        if is_html:
            update_data[formatted_field] = db_value
        else:
            # Clear formatted if saving raw
            update_data[formatted_field] = None

        self.db_manager.update_recording(
            recording_id, on_update_complete, **update_data
        )

    def on_gpt4_processing_error(self, error_message):
        # Show error to user
        show_error_message(self, "GPT Processing Error", error_message)

        # Update status
        self.status_update.emit(f"GPT processing failed: {error_message}")

        # Reset feedback
        self.feedback_manager.close_progress(self.gpt_progress_id)

        # Reset all potential processing buttons
        self.transcript_text.toggle_spinner("smart_format")
        self.transcript_text.toggle_spinner("gpt")
        self.transcript_text.toggle_spinner("transcription")

        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner("gpt_process")

        # Finished signal will handle cleanup

    def on_gpt4_processing_finished(self):
        """Called when GPT processing thread finishes."""
        # Update state flags
        self.is_processing_gpt4 = False
        self.update_ui_state()

        # Clean up feedback
        self.feedback_manager.stop_spinner("gpt_process")
        self.feedback_manager.close_progress(self.gpt_progress_id)
        delattr(self, "gpt_progress_id")

        # Clean up thread reference
        self.gpt4_processing_thread = None
        logger.info("GPT processing thread finished.")

        self.status_update.emit("Ready")

    def start_smart_format_processing(self, text_to_format):
        """Apply smart formatting to the current text using GPT."""
        if not text_to_format.strip():
            show_error_message(self, "Empty Text",
                               "There is no text to format.")
            return

        # Mark as processing
        self.is_processing_gpt4 = True

        # Get UI elements to disable during processing
        ui_elements = self._busy_elements_for("smart_format")

        # Create BusyGuard callback
        def create_busy_guard(
            operation_name,
            spinner,
            progress,
            progress_title,
            progress_message,
            progress_maximum,
            progress_cancelable,
            cancel_callback,
            status_message,
        ):
            guard = BusyGuard(
                self.feedback_manager,
                operation_name,
                ui_elements=ui_elements,
                spinner=spinner,
                progress=progress,
                progress_title=progress_title,
                progress_message=progress_message,
                progress_maximum=progress_maximum,
                progress_cancelable=progress_cancelable,
                cancel_callback=cancel_callback,
                status_message=status_message,
            )
            self.smart_format_guard = guard
            self.smart_format_guard.__enter__()
            return guard

        # Define completion callback
        def on_completion(formatted_text, is_html):
            # Update editor with formatted text
            if is_html:
                self.transcript_text.editor.setHtml(formatted_text)
            else:
                self.transcript_text.editor.setPlainText(formatted_text)

            # If we're in processed view, update last_processed_text_html for refinement
            if self.view_mode is ViewMode.PROCESSED:
                self.last_processed_text_html = formatted_text if is_html else None
                self.refinement_widget.setVisible(True)

            # Update database if current recording exists
            if self.current_recording_data:
                recording_id = self.current_recording_data["id"]
                field = (
                    "processed_text_formatted"
                    if self.view_mode is ViewMode.PROCESSED
                    else "raw_transcript_formatted"
                )
                update_data = {field: formatted_text if is_html else None}

                def on_update_complete():
                    self.current_recording_data.update(update_data)
                    self.status_update.emit("Smart formatting saved.")

                self.db_manager.update_recording(
                    recording_id, on_update_complete, **update_data
                )

        # Start formatting with controller
        success = self.gpt_controller.smart_format(
            text_to_format=text_to_format,
            config=self.config_manager.get_all(),
            busy_guard_callback=create_busy_guard,
            completion_callback=on_completion,
        )

        # Handle failure
        if not success:
            self.is_processing_gpt4 = False
            self.smart_format_guard.__exit__(None, None, None)
            delattr(self, "smart_format_guard")

    def cancel_smart_formatting(self):
        """Cancel an ongoing smart formatting operation."""
        logger.info("User requested cancellation of smart formatting")
        self.gpt_controller.cancel("smart_format")
        self.feedback_manager.show_status("Cancelling smart formatting...")

    def on_smart_format_progress(self, message):
        """Handle progress updates from smart format thread."""
        self.status_update.emit(message)

        self.feedback_manager.update_progress(
            self.smart_format_progress_id, 0, message  # Still indeterminate
        )

    def on_smart_format_error(self, error_message):
        """Handle errors from smart format thread."""
        # Show error to user
        show_error_message(self, "Smart Format Error", error_message)

        # Update status
        self.status_update.emit(f"Smart formatting failed: {error_message}")

        # Reset feedback
        self.feedback_manager.close_progress(self.smart_format_progress_id)

        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner("smart_format")

    def on_smart_format_finished(self):
        """Called when smart formatting thread finishes."""
        # Update state flags
        self.is_processing_gpt4 = False
        self.update_ui_state()

        # Clean up feedback
        self.feedback_manager.stop_spinner("smart_format")
        self.feedback_manager.close_progress(self.smart_format_progress_id)
        delattr(self, "smart_format_progress_id")

        # Clean up thread reference
        self.gpt4_smart_format_thread = None
        logger.info("Smart formatting thread finished.")

        self.status_update.emit("Ready")

    def on_smart_format_completed(self, formatted_html):
        if not self.current_recording_data:
            return  # Check if recording is still selected

        # Reset smart format button state and stop spinner
        self.transcript_text.toggle_spinner("smart_format")
        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner("smart_format")

        recording_id = self.current_recording_data["id"]
        current_view_is_raw = self.view_mode is ViewMode.RAW

        if formatted_html:
            self.transcript_text.editor.setHtml(formatted_html)
            self.status_update.emit("Smart formatting applied. Saving...")

            # Determine which field to save to based on current view
            if current_view_is_raw:
                field_to_update = "raw_transcript_formatted"
                raw_field = "raw_transcript"  # Keep raw text as is
                db_update_data = {field_to_update: formatted_html}
            else:
                field_to_update = "processed_text_formatted"
                # Update the processed raw text as well? Maybe not.
                raw_field = "processed_text"
                db_update_data = {field_to_update: formatted_html}
                # Also update self.last_processed_text_html for refinement
                self.last_processed_text_html = formatted_html

            def on_update_complete():
                self.current_recording_data[field_to_update] = formatted_html
                # Don't update the underlying raw_transcript or processed_text fields here
                # unless that's the desired behavior. Formatting is separate.
                self.status_update.emit("Smart formatting saved.")
                self.gpt_process_completed.emit(formatted_html)  # Reuse signal
                if not current_view_is_raw:
                    # Show refinement if we were in processed view
                    self.refinement_widget.setVisible(True)

            self.db_manager.update_recording(
                recording_id, on_update_complete, **db_update_data
            )

        else:
            show_error_message(
                self,
                "Formatting Failed",
                "Smart formatting did not return any content.",
            )
            self.status_update.emit("Smart formatting failed.")

    def start_refinement_processing(self):
        """Apply refinement instructions to the processed text."""
        if not self.current_recording_data:
            show_error_message(
                self, "No Recording", "No recording selected for refinement."
            )
            return

        # Get refinement instructions
        refinement_instructions = self.refinement_input.text().strip()
        if not refinement_instructions:
            show_error_message(
                self, "No Instructions", "Please enter refinement instructions."
            )
            return

        # Get necessary data
        # Use the last processed text as the base for refinement
        processed_text = ""
        if self.last_processed_text_html:
            processed_text = self.last_processed_text_html
        elif (
            self.current_recording_data
            and "processed_text" in self.current_recording_data
        ):
            processed_text = self.current_recording_data.get(
                "processed_text", "")

        # Use the prompt that generated the processed text
        initial_prompt = (
            self.initial_prompt_instructions or "No initial prompt recorded."
        )

        # Validate data
        if not self.current_recording_data.get("raw_transcript"):
            show_error_message(self, "Missing Data",
                               "Original transcript is missing.")
            return
        if not processed_text:
            show_error_message(
                self,
                "Missing Data",
                "Previous processed text is missing. Please process first.",
            )
            return

        # Convert to Recording object if needed
        recording = self.current_recording_data
        if not isinstance(recording, Recording):
            recording = Recording(
                id=recording["id"],
                filename=recording["filename"],
                file_path=recording["file_path"],
                date_created=recording.get("date_created"),
                duration=recording.get("duration"),
                raw_transcript=recording.get("raw_transcript"),
                processed_text=recording.get("processed_text"),
                raw_transcript_formatted=recording.get(
                    "raw_transcript_formatted"),
                processed_text_formatted=recording.get(
                    "processed_text_formatted"),
            )

        # Mark as processing
        self.is_processing_gpt4 = True

        # Get UI elements to disable during processing
        ui_elements = self._busy_elements_for("refinement")

        # Create BusyGuard callback
        def create_busy_guard(
            operation_name,
            spinner,
            progress,
            progress_title,
            progress_message,
            progress_maximum,
            progress_cancelable,
            cancel_callback,
            status_message,
        ):
            guard = BusyGuard(
                self.feedback_manager,
                operation_name,
                ui_elements=ui_elements,
                spinner=spinner,
                progress=progress,
                progress_title=progress_title,
                progress_message=progress_message,
                progress_maximum=progress_maximum,
                progress_cancelable=progress_cancelable,
                cancel_callback=cancel_callback,
                status_message=status_message,
            )
            self.refinement_guard = guard
            self.refinement_guard.__enter__()
            return guard

        # Define completion callback
        def on_completion(refined_text, is_html):
            # Update editor with refined text
            if is_html:
                self.transcript_text.editor.setHtml(refined_text)
                self.last_processed_text_html = refined_text
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                self.last_processed_text_html = None

            # Clear the refinement input
            self.refinement_input.clear()

        # Start refinement with controller
        success = self.gpt_controller.refine(
            recording=recording,
            refinement_instructions=refinement_instructions,
            initial_prompt=initial_prompt,
            processed_text=processed_text,
            config=self.config_manager.get_all(),
            busy_guard_callback=create_busy_guard,
            completion_callback=on_completion,
        )

        # Handle failure
        if not success:
            self.is_processing_gpt4 = False
            self.refinement_guard.__exit__(None, None, None)
            delattr(self, "refinement_guard")

    def cancel_refinement(self):
        """Cancel an ongoing refinement operation."""
        logger.info("User requested cancellation of refinement")
        self.gpt_controller.cancel("refinement")
        self.feedback_manager.show_status("Cancelling refinement...")

    def on_refinement_progress(self, message):
        """Handle progress updates from refinement thread."""
        self.status_update.emit(message)

        self.feedback_manager.update_progress(
            self.refinement_progress_id, 0, message  # Still indeterminate
        )

    def on_refinement_error(self, error_message):
        """Handle errors from refinement thread."""
        # Show error to user
        show_error_message(self, "Refinement Error", error_message)

        # Update status
        self.status_update.emit(f"Refinement failed: {error_message}")

        # Reset feedback
        self.feedback_manager.close_progress(self.refinement_progress_id)

        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner("refinement")

    def on_refinement_finished(self):
        """Called when refinement thread finishes."""
        # Update state flags
        self.is_processing_gpt4 = False
        self.update_ui_state()

        # Clean up feedback
        self.feedback_manager.stop_spinner("refinement")
        self.feedback_manager.close_progress(self.refinement_progress_id)
        delattr(self, "refinement_progress_id")

        # Clean up thread reference
        self.gpt4_refinement_thread = None
        logger.info("Refinement thread finished.")

    def on_refinement_completed(self, refined_text):
        """Handle the refined text received from GPT-4."""
        # Re-enable refinement controls first
        self.refinement_input.setEnabled(True)
        self.refinement_input.clear()
        self.refinement_submit_button.setEnabled(True)
        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner("refinement")

        if not self.current_recording_data:
            return

        if refined_text:
            recording_id = self.current_recording_data["id"]
            formatted_field = "processed_text_formatted"
            raw_field = "processed_text"

            # Update the editor with the refined text
            is_html = "<" in refined_text and ">" in refined_text
            if is_html:
                self.transcript_text.editor.setHtml(refined_text)
                db_value = refined_text
                self.last_processed_text_html = db_value  # Update last processed text
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                db_value = refined_text
                self.last_processed_text_html = None

            self.status_update.emit("Refinement complete. Saving...")

            # Define callback for database update completion
            def on_update_complete():
                self.current_recording_data[raw_field] = (
                    refined_text  # Update local data
                )
                self.current_recording_data[formatted_field] = (
                    db_value if is_html else None
                )
                self.status_update.emit("Refinement saved.")
                self.gpt_process_completed.emit(refined_text)  # Emit signal
                logger.info(
                    f"Refinement saved for recording ID: {recording_id}")

            # Save the refined text to the database
            update_data = {raw_field: refined_text}
            if is_html:
                update_data[formatted_field] = db_value
            else:
                # Clear formatted if saving raw
                update_data[formatted_field] = None

            self.db_manager.update_recording(
                recording_id, on_update_complete, **update_data
            )
        else:
            show_error_message(
                self, "Refinement Error", "GPT-4 did not return any refined text."
            )
            self.status_update.emit("Refinement failed.")

    def on_prompt_instructions_changed(self, instructions):
        """Handle changes in prompt instructions from the PromptBar."""
        # This is called when the PromptBar's instruction_changed signal is emitted
        # We don't need to do anything special here since this just keeps us informed
        # of the current prompt text
        pass

    def get_current_prompt_instructions(self):
        """Retrieve the current prompt instructions from the PromptBar."""
        return self.prompt_bar.current_prompt_text()

    # --- UI State Management ---

    def on_recording_item_selected(self, recording_item):
        """Handle the event when a recording item is selected."""
        if not recording_item:
            self.current_recording_data = None
            self.transcript_text.clear()
            self.update_ui_state()
            return

        recording_id = recording_item.get_id()
        logger.info(f"Loading recording ID: {recording_id}")

        # Define callback for database query
        def on_recording_loaded(recording: Recording):
            if recording:
                self.current_recording_data = {
                    "id": recording.id,
                    "filename": recording.filename,
                    "file_path": recording.file_path,
                    "date_created": recording.date_created,
                    "duration": recording.duration,
                    "raw_transcript": recording.raw_transcript or "",
                    "processed_text": recording.processed_text or "",
                    "raw_transcript_formatted": recording.raw_transcript_formatted,  # Might be None
                    "processed_text_formatted": recording.processed_text_formatted,  # Might be None
                }
                logger.debug(f"Loaded data: {self.current_recording_data}")

                # Reset processing states for the new item
                self.is_transcribing = False
                self.is_processing_gpt4 = False
                self.initial_prompt_instructions = None  # Reset initial prompt
                self.last_processed_text_html = (
                    recording.processed_text_formatted
                )  # Load last saved formatted

                # Set the editor content based on the mode switch
                self.toggle_transcription_view()
                self.update_ui_state()

            else:
                show_error_message(
                    self,
                    "Error",
                    f"Could not load recording data for ID: {recording_id}",
                )
                self.current_recording_data = None
                self.transcript_text.clear()
                self.update_ui_state()

        # Fetch data from database manager
        self.db_manager.get_recording_by_id(recording_id, on_recording_loaded)

    def toggle_transcription_view(self):
        """Toggle between raw and processed transcript views based on switch."""
        if not self.current_recording_data:
            self.transcript_text.clear()
            self.refinement_widget.setVisible(False)
            return

        is_raw_view = self.view_mode is ViewMode.RAW

        if is_raw_view:
            # Show raw transcript (formatted if available, else raw)
            content_to_show = self.current_recording_data.get(
                "raw_transcript_formatted"
            ) or self.current_recording_data.get("raw_transcript", "")
            self.transcript_text.deserialize_text_document(content_to_show)
            self.refinement_widget.setVisible(False)
        else:
            # Show processed text (formatted if available, else raw)
            content_to_show = self.current_recording_data.get(
                "processed_text_formatted"
            ) or self.current_recording_data.get("processed_text", "")
            self.transcript_text.deserialize_text_document(content_to_show)
            # Show refinement only if there is processed text and not currently processing
            can_refine = bool(content_to_show) and not self.is_processing_gpt4
            self.refinement_widget.setVisible(can_refine)

        # Ensure editor is properly updated and repainted
        self.transcript_text.repaint()
        self.transcript_text.editor.repaint()

    def on_mode_switch_changed(self, value):
        """Handle changes in the mode switch."""
        self.view_mode = ViewMode.RAW if value == 0 else ViewMode.PROCESSED
        self.toggle_transcription_view()
        self.update_ui_state()  # Update button states etc.

    def update_ui_state(self):
        """Update the UI elements based on the current state."""
        has_recording = self.current_recording_data is not None
        has_raw_transcript = has_recording and bool(
            self.current_recording_data.get("raw_transcript")
        )
        has_processed_text = has_recording and (
            bool(self.current_recording_data.get("processed_text"))
            or bool(self.current_recording_data.get("processed_text_formatted"))
        )
        is_raw_mode = self.view_mode is ViewMode.RAW

        # Enable/disable transcription and GPT processing buttons in TextEditor toolbar
        # Can always transcribe if a recording is selected (will overwrite)
        self.transcript_text._toolbar_actions["start_transcription"].setEnabled(
            has_recording and not self.is_transcribing
        )
        # Can process if raw transcript exists and not busy
        self.transcript_text._toolbar_actions["process_with_gpt4"].setEnabled(
            has_raw_transcript
            and not self.is_transcribing
            and not self.is_processing_gpt4
        )
        # Can smart format if text editor has content and not busy
        can_smart_format = (
            bool(self.transcript_text.toPlainText().strip())
            and not self.is_transcribing
            and not self.is_processing_gpt4
        )
        self.transcript_text._toolbar_actions["smart_format"].setEnabled(
            can_smart_format
        )
        # Can save if a recording is selected and not busy
        self.transcript_text._toolbar_actions["save"].setEnabled(
            has_recording and not self.is_transcribing and not self.is_processing_gpt4
        )

        # Toggle refinement widget visibility (also handled in toggle_transcription_view)
        show_refine = (
            (not is_raw_mode) and has_processed_text and not self.is_processing_gpt4
        )
        self.refinement_widget.setVisible(show_refine)
        self.refinement_input.setEnabled(show_refine)
        self.refinement_submit_button.setEnabled(show_refine)

        # Enable/disable main dropdowns based on processing state
        processing_busy = self.is_transcribing or self.is_processing_gpt4
        # Update the prompt bar enabled state
        self.prompt_bar.setEnabled(not processing_busy)
        # Can only switch if recording loaded
        self.mode_switch.setEnabled(not processing_busy and has_recording)

    def save_editor_state(self):
        """Save the current state of the text editor to the database."""
        if not self.current_recording_data:
            show_error_message(
                self, "No Recording Selected", "Please select a recording to save."
            )
            return

        recording_id = self.current_recording_data["id"]
        editor_html = self.transcript_text.editor.toHtml()
        editor_plain = self.transcript_text.editor.toPlainText()

        if not editor_html:  # Should ideally not happen with QTextEdit
            show_error_message(self, "Save Error",
                               "Cannot retrieve editor content.")
            return

        is_raw_view = self.view_mode is ViewMode.RAW
        update_data = {}

        if is_raw_view:
            # Saving the raw view - update raw_transcript_formatted and raw_transcript
            update_data["raw_transcript_formatted"] = editor_html
            # Store plain text version too
            update_data["raw_transcript"] = editor_plain
            field_saved = "Raw transcript"
        else:
            # Saving the processed view - update processed_text_formatted and processed_text
            update_data["processed_text_formatted"] = editor_html
            # Store plain text version
            update_data["processed_text"] = editor_plain
            field_saved = "Processed text"
            self.last_processed_text_html = editor_html  # Update last processed state

        # Define callback for database update
        def on_update_complete():
            # Update local cache
            self.current_recording_data.update(update_data)
            show_info_message(
                self, "Save Successful", f"{field_saved} saved successfully."
            )
            self.save_operation_completed.emit(f"{field_saved} saved.")

        # Execute database update
        self.db_manager.update_recording(
            recording_id, on_update_complete, **update_data
        )

    def open_settings_dialog(self):
        """Open the settings dialog."""
        # SettingsDialog now manages its own state and interacts with managers
        dialog = SettingsDialog(parent=self)  # Pass self as parent only
        # No need to connect signals like settings_changed or prompts_updated
        dialog.exec()
