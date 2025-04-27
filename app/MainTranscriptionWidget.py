import os
import torch
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QHBoxLayout, QLabel,
    QTextEdit, QSplitter, QPushButton,
    QLineEdit, QInputDialog
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal, QSize, Qt, QTimer

from app.TextEditor import TextEditor
from app.threads.TranscriptionThread import TranscriptionThread
from app.threads.GPT4ProcessingThread import GPT4ProcessingThread
from app.SettingsDialog import SettingsDialog
from app.ToggleSwitch import ToggleSwitch
from app.DatabaseManager import DatabaseManager
from app.ResponsiveUI import ResponsiveWidget, ResponsiveSizePolicy
from app.ui_utils import SpinnerManager, FeedbackManager, show_error_message, show_info_message, show_confirmation_dialog
from app.file_utils import is_valid_media_file, check_file_size
from app.path_utils import resource_path
from app.utils import ConfigManager, PromptManager
from app.ThreadManager import ThreadManager
from app.constants import (
     ERROR_INVALID_FILE, ERROR_API_KEY_MISSING,
    SUCCESS_TRANSCRIPTION, SUCCESS_GPT_PROCESSING
)

logger = logging.getLogger('transcribrr')


class MainTranscriptionWidget(ResponsiveWidget):
    # Transcription and GPT workflow signals
    transcription_process_started = pyqtSignal()
    transcription_process_completed = pyqtSignal(str) # Emits final transcript text
    transcription_process_stopped = pyqtSignal()
    gpt_process_started = pyqtSignal()
    gpt_process_completed = pyqtSignal(str) # Emits final processed text
    save_operation_completed = pyqtSignal(str) # Emits status message
    status_update = pyqtSignal(str) # Generic status update signal
    recording_status_updated = pyqtSignal(int, dict) # Signal for recording updates (ID, data)

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
        self.spinner_manager = SpinnerManager(self) # For backward compatibility
        self.feedback_manager = FeedbackManager(self) # Centralized feedback management
        
        # State variables
        self.is_editing_existing_prompt = False
        # self.file_path = None # Stored within current_recording_data
        self.is_transcribing = False
        self.is_processing_gpt4 = False
        self.current_recording_data = None # Store full data of selected item
        self.initial_prompt_instructions = None # Store prompt used for initial processing
        self.last_processed_text_html = None # Store the last HTML processed text

        # Load initial configuration for GPT params (others loaded on demand)
        self._load_gpt_params_from_config()

        # UI Initialization - Create UI elements first before connecting signals or using them
        # Initialize all UI components - first create controls, then add to main content
        self.init_top_toolbar()   # Create the controls first
        self.init_main_content()  # Use the controls in the main content
        
        # Connect signals after UI is fully initialized
        self.connect_signals()

        # Connect to manager signals
        self.prompt_manager.prompts_changed.connect(self.load_prompts_to_dropdown)
        self.config_manager.config_updated.connect(self.handle_config_update)

    def _load_gpt_params_from_config(self):
        """Load only GPT parameters initially."""
        self.gpt_temperature = self.config_manager.get('temperature', 1.0)
        self.gpt_max_tokens = self.config_manager.get('max_tokens', 16000)

    def handle_config_update(self, changed_config):
        """Handle updates pushed from ConfigManager."""
        logger.debug(f"Config updated: {changed_config}")
        # Update relevant internal state if needed
        if 'temperature' in changed_config:
             self.gpt_temperature = changed_config['temperature']
        if 'max_tokens' in changed_config:
             self.gpt_max_tokens = changed_config['max_tokens']
        # Add checks for other relevant config keys if necessary

    def connect_signals(self):
        # Connect signals for TextEditor
        if hasattr(self, 'transcript_text'):
            self.transcript_text.transcription_requested.connect(self.start_transcription)
            self.transcript_text.gpt4_processing_requested.connect(self.start_gpt4_processing)
            self.transcript_text.smart_format_requested.connect(self.start_smart_format_processing)
            self.transcript_text.save_requested.connect(self.save_editor_state)
            
            # Expose our status update signals to TextEditor's status bar
            # This fixes the "Cannot show status message" warnings
            self.status_update.connect(lambda msg: self.transcript_text.show_status_message(msg))

        # Connect toolbar signals
        if hasattr(self, 'mode_switch'):
            self.mode_switch.valueChanged.connect(self.on_mode_switch_changed)
        if hasattr(self, 'settings_button'):
            self.settings_button.clicked.connect(self.open_settings_dialog) # Direct call
        if hasattr(self, 'gpt_prompt_dropdown'):
            self.gpt_prompt_dropdown.currentIndexChanged.connect(self.on_prompt_selection_changed)
        if hasattr(self, 'edit_prompt_button'):
            self.edit_prompt_button.clicked.connect(self.on_edit_prompt_button_clicked)
        if hasattr(self, 'refinement_submit_button'):
            self.refinement_submit_button.clicked.connect(self.start_refinement_processing)

    def init_top_toolbar(self):
        # Create the elements but do not add them to layout here
        # They will be added directly to the editor widget in init_main_content
        self.gpt_prompt_dropdown = QComboBox()
        
        self.edit_prompt_button = QPushButton("Edit") # Shorter text
        self.edit_prompt_button.setToolTip("Edit selected prompt template")
        self.edit_prompt_button.setIcon(QIcon(resource_path('icons/edit.svg')))
        self.edit_prompt_button.setIconSize(QSize(16,16))
        self.edit_prompt_button.setFixedSize(QSize(60, 28)) # Adjust size

        self.raw_transcript_label = QLabel('Raw')
        self.mode_switch = ToggleSwitch()
        self.mode_switch.setValue(0) # Default to raw
        self.gpt_processed_label = QLabel('Processed')

        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon(resource_path('icons/settings.svg')))
        self.settings_button.setToolTip("Open Settings")
        self.settings_button.setIconSize(QSize(18, 18))
        self.settings_button.setFixedSize(28, 28)
        
        # Load prompts only after all UI elements are created
        self.load_prompts_to_dropdown()

    def init_main_content(self):
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.main_splitter)

        # --- Custom Prompt Input Area ---
        self.prompt_widget = QWidget()
        prompt_layout = QVBoxLayout(self.prompt_widget)
        prompt_layout.setContentsMargins(0, 5, 0, 5)
        prompt_layout.setSpacing(5)
        self.custom_prompt_input = QTextEdit()
        self.custom_prompt_input.setPlaceholderText("Enter your custom prompt instructions here...")
        self.custom_prompt_input.setMaximumHeight(120) # Slightly larger max height
        prompt_layout.addWidget(self.custom_prompt_input)

        self.prompt_button_widget = QWidget()
        prompt_button_layout = QHBoxLayout(self.prompt_button_widget)
        prompt_button_layout.setContentsMargins(0,0,0,0)
        self.custom_prompt_save_button = QPushButton("Save as Template")
        self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
        prompt_button_layout.addWidget(self.custom_prompt_save_button)
        prompt_button_layout.addStretch()
        prompt_layout.addWidget(self.prompt_button_widget)
        self.prompt_widget.setVisible(False) # Initially hidden

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
        control_bar.addWidget(QLabel("Prompt:"))
        control_bar.addWidget(self.gpt_prompt_dropdown, 1)  # Allow dropdown to stretch
        control_bar.addWidget(self.edit_prompt_button)
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
        self.transcript_text = TextEditor() # The rich text editor
        editor_layout.addWidget(self.transcript_text)
        
        # Register spinners for toolbar buttons
        self.spinner_manager.create_spinner(
            name='transcribe',
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path('./icons/transcribe.svg'),
            action_tooltip='Start Transcription',
            callback=self.transcript_text.start_transcription
        )
        
        self.spinner_manager.create_spinner(
            name='gpt_process',
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path('./icons/magic_wand.svg'),
            action_tooltip='Process with GPT-4',
            callback=self.transcript_text.process_with_gpt4
        )
        
        self.spinner_manager.create_spinner(
            name='smart_format',
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path('./icons/smart_format.svg'),
            action_tooltip='Smart Format',
            callback=self.transcript_text.smart_format_text
        )
        
        self.spinner_manager.create_spinner(
            name='refinement',
            toolbar=self.transcript_text.toolbar,
            action_icon=resource_path('./icons/quill.svg'),
            action_tooltip='Refine Text',
            callback=self.start_refinement_processing
        )
        
        # Add the editor widget to the main content layout
        content_layout.addWidget(editor_widget)

        # --- Refinement Input Area ---
        self.refinement_widget = QWidget()
        refinement_layout = QHBoxLayout(self.refinement_widget)
        refinement_layout.setContentsMargins(0, 5, 0, 0)
        self.refinement_input = QLineEdit()
        self.refinement_input.setPlaceholderText("Enter refinement instructions (e.g., 'Make it more formal')...")
        self.refinement_submit_button = QPushButton("Refine")
        refinement_layout.addWidget(self.refinement_input, 1)
        refinement_layout.addWidget(self.refinement_submit_button)
        content_layout.addWidget(self.refinement_widget)
        self.refinement_widget.setVisible(False) # Hidden by default

        # --- Add Widgets to Splitter ---
        self.main_splitter.addWidget(self.prompt_widget)
        self.main_splitter.addWidget(self.content_widget)
        self.main_splitter.setSizes([0, 500]) # Initially hide prompt widget

    # Temperature and max tokens settings have been moved to SettingsDialog only

    def load_prompts_to_dropdown(self):
        """Load prompts from PromptManager into the dropdown."""
        prompts = self.prompt_manager.get_prompts()
        current_selection = self.gpt_prompt_dropdown.currentText()

        self.gpt_prompt_dropdown.blockSignals(True)
        self.gpt_prompt_dropdown.clear()

        # Group by category
        categorized_prompts = {}
        for name, data in prompts.items():
            category = data.get("category", "General")
            if category not in categorized_prompts:
                categorized_prompts[category] = []
            categorized_prompts[category].append(name)

        # Add items sorted by category, then name
        for category in sorted(categorized_prompts.keys()):
            prompt_names_in_category = sorted(categorized_prompts[category])
            if category != "General": # Add separator for non-general categories
                 self.gpt_prompt_dropdown.insertSeparator(self.gpt_prompt_dropdown.count())
            for name in prompt_names_in_category:
                # Display as "Name (Category)" for clarity, except for General
                display_name = f"{name} ({category})" if category != "General" else name
                self.gpt_prompt_dropdown.addItem(display_name, name) # Store real name as user data

        # Add Custom Prompt option
        self.gpt_prompt_dropdown.insertSeparator(self.gpt_prompt_dropdown.count())
        self.gpt_prompt_dropdown.addItem("Custom Prompt", "CUSTOM") # Use unique user data

        # Restore selection if possible
        index = self.gpt_prompt_dropdown.findData(current_selection) # Find by real name
        if index == -1 and current_selection == "Custom Prompt":
             index = self.gpt_prompt_dropdown.findData("CUSTOM")

        self.gpt_prompt_dropdown.setCurrentIndex(index if index != -1 else 0)
        self.gpt_prompt_dropdown.blockSignals(False)
        self.on_prompt_selection_changed(self.gpt_prompt_dropdown.currentIndex()) # Trigger update

    def on_prompt_selection_changed(self, index):
        """Handle changes in prompt selection."""
        if not hasattr(self, 'gpt_prompt_dropdown') or not hasattr(self, 'edit_prompt_button'):
            return  # UI not fully initialized yet
            
        selected_data = self.gpt_prompt_dropdown.itemData(index)

        if selected_data == "CUSTOM":
            self.is_editing_existing_prompt = False
            self.show_custom_prompt_input()
            if hasattr(self, 'custom_prompt_input'):
                self.custom_prompt_input.clear()
            if hasattr(self, 'custom_prompt_save_button'):
                self.custom_prompt_save_button.setText("Save as Template")
                try:
                    self.custom_prompt_save_button.clicked.disconnect()
                except TypeError:
                    pass  # No connections to disconnect
                self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
            self.edit_prompt_button.setVisible(False) # Cannot edit the "Custom" option itself
        else:
            # A predefined prompt is selected
            selected_prompt_name = selected_data # Real name stored in UserData
            self.hide_custom_prompt_input()
            self.edit_prompt_button.setVisible(True)
            self.is_editing_existing_prompt = False
            self.edit_prompt_button.setText("Edit")
            self.edit_prompt_button.setToolTip("Edit selected prompt template")


    def show_custom_prompt_input(self):
        """Show the custom prompt input area."""
        if hasattr(self, 'prompt_widget') and hasattr(self, 'custom_prompt_input'):
            self.prompt_widget.setVisible(True)
            self.main_splitter.setSizes([130, self.main_splitter.sizes()[1]]) # Allocate space
            QTimer.singleShot(0, lambda: self.custom_prompt_input.setFocus()) # Set focus after visible

    def hide_custom_prompt_input(self):
        """Hide the custom prompt input area."""
        if hasattr(self, 'prompt_widget'):
            self.prompt_widget.setVisible(False)
            self.main_splitter.setSizes([0, self.main_splitter.sizes()[1] + self.main_splitter.sizes()[0]]) # Collapse

    def on_edit_prompt_button_clicked(self):
        """Handle clicks on the edit prompt button."""
        if self.is_editing_existing_prompt:
            # Cancel editing
            self.hide_custom_prompt_input()
            self.edit_prompt_button.setText("Edit")
            self.edit_prompt_button.setToolTip("Edit selected prompt template")
            self.is_editing_existing_prompt = False
        else:
            # Start editing
            current_index = self.gpt_prompt_dropdown.currentIndex()
            selected_prompt_name = self.gpt_prompt_dropdown.itemData(current_index)

            if selected_prompt_name != "CUSTOM":
                prompt_text = self.prompt_manager.get_prompt_text(selected_prompt_name)
                if prompt_text is not None:
                    self.is_editing_existing_prompt = True
                    self.custom_prompt_input.setPlainText(prompt_text)
                    self.show_custom_prompt_input()
                    self.edit_prompt_button.setText("Cancel")
                    self.edit_prompt_button.setToolTip("Cancel editing")
                    self.custom_prompt_save_button.setText("Save Changes")
                    self.custom_prompt_save_button.clicked.disconnect()
                    self.custom_prompt_save_button.clicked.connect(self.save_edited_prompt)
                else:
                    show_error_message(self, "Error", f"Could not find prompt '{selected_prompt_name}'.")
            else:
                show_info_message(self, "Edit Prompt", "Select a saved prompt template to edit it.")

    def save_custom_prompt_as_template(self):
        """Save the custom prompt as a new template via PromptManager."""
        prompt_text = self.custom_prompt_input.toPlainText().strip()
        if not prompt_text:
            show_error_message(self, "Empty Prompt", "Cannot save an empty prompt.")
            return

        prompt_name, ok = QInputDialog.getText(self, 'Save New Prompt', 'Enter a name for this new prompt template:')
        if ok and prompt_name:
            if self.prompt_manager.get_prompt_text(prompt_name) is not None:
                 if not show_confirmation_dialog(self, "Overwrite Prompt?", f"A prompt named '{prompt_name}' already exists. Overwrite it?"):
                      return

            # Ask for category (optional)
            categories = sorted(list(set(p.get("category", "General") for p in self.prompt_manager.get_prompts().values())))
            if "Custom" not in categories: categories.append("Custom")
            category, ok_cat = QInputDialog.getItem(self, "Select Category", "Choose a category (or type a new one):", categories, 0, True)

            if ok_cat and category:
                if self.prompt_manager.add_prompt(prompt_name, prompt_text, category):
                    show_info_message(self, "Prompt Saved", f"Prompt '{prompt_name}' saved.")
                    self.load_prompts_to_dropdown() # Reload dropdown
                    # Select the newly added prompt
                    new_index = self.gpt_prompt_dropdown.findData(prompt_name)
                    if new_index != -1:
                         self.gpt_prompt_dropdown.setCurrentIndex(new_index)
                    else: # Fallback if findData fails
                         self.hide_custom_prompt_input() # Hide on success anyway
                    self.is_editing_existing_prompt = False # Reset state
                else:
                    show_error_message(self, "Error", f"Failed to save prompt '{prompt_name}'.")
            else:
                 show_info_message(self, "Save Cancelled", "Prompt save cancelled.")


    def save_edited_prompt(self):
        """Save the edited prompt via PromptManager."""
        edited_text = self.custom_prompt_input.toPlainText().strip()
        if not edited_text:
            show_error_message(self, "Empty Prompt", "Prompt text cannot be empty.")
            return

        current_index = self.gpt_prompt_dropdown.currentIndex()
        selected_prompt_name = self.gpt_prompt_dropdown.itemData(current_index)

        if selected_prompt_name != "CUSTOM":
            # Keep existing category unless user changes it (optional enhancement)
            current_category = self.prompt_manager.get_prompt_category(selected_prompt_name) or "General"
            if self.prompt_manager.update_prompt(selected_prompt_name, edited_text, current_category):
                show_info_message(self, "Prompt Updated", f"Prompt '{selected_prompt_name}' updated.")
                self.hide_custom_prompt_input()
                self.edit_prompt_button.setText("Edit")
                self.edit_prompt_button.setToolTip("Edit selected prompt template")
                self.is_editing_existing_prompt = False
                self.load_prompts_to_dropdown() # Reload dropdown to reflect changes (if any display logic depends on text)
                # Re-select the edited prompt
                new_index = self.gpt_prompt_dropdown.findData(selected_prompt_name)
                if new_index != -1: self.gpt_prompt_dropdown.setCurrentIndex(new_index)

            else:
                show_error_message(self, "Error", f"Failed to update prompt '{selected_prompt_name}'.")
        else:
             show_error_message(self, "Error", "Cannot save changes to the 'Custom Prompt' option.")


    # --- Processing Logic ---

    def start_transcription(self):
        if not self.current_recording_data:
            show_error_message(self, 'No Recording Selected', 'Please select a recording to transcribe.')
            return

        # Get transcription parameters from config manager
        config = self.config_manager.get_all()
        transcription_method = config.get('transcription_method', 'local')
        transcription_quality = config.get('transcription_quality', 'openai/whisper-large-v3')
        speaker_detection_enabled = config.get('speaker_detection_enabled', False)
        hardware_acceleration_enabled = config.get('hardware_acceleration_enabled', True)
        language = config.get('transcription_language', 'english')
        chunk_enabled = config.get('chunk_enabled', True) # Needed if file is large
        chunk_duration = config.get('chunk_duration', 5) # Needed if file is large
        
        # Disable speaker detection for API method
        if transcription_method == 'api' and speaker_detection_enabled:
            speaker_detection_enabled = False
            logger.info("Speaker detection disabled for API transcription method")
            
        # Check if we're on an MPS-only device and handle potential conflicts
        try:
            has_cuda = torch.cuda.is_available()
            has_mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
            mps_only_device = has_mps and not has_cuda
            
            # If MPS-only device with hardware acceleration and speaker detection, log a warning
            if mps_only_device and hardware_acceleration_enabled and speaker_detection_enabled:
                logger.warning("Speaker detection may not work with MPS acceleration. User has both enabled.")
        except Exception:
            logger.warning("Could not check hardware compatibility")

        # Get API keys using secure module
        from app.secure import get_api_key
        openai_api_key = get_api_key("OPENAI_API_KEY")
        hf_auth_key = get_api_key("HF_AUTH_TOKEN")

        # Validation checks
        file_path = self.current_recording_data['file_path']
        if not file_path or not os.path.exists(file_path):
            show_error_message(self, "File Error", f"Audio file not found: {file_path}")
            return

        if not is_valid_media_file(file_path):
            show_error_message(self, "Invalid File", ERROR_INVALID_FILE)
            return

        is_valid_size, file_size_mb = check_file_size(file_path)
        # Note: Size check might be less relevant if chunking handles large files
        # if not is_valid_size:
        #     show_error_message(self, "File Too Large", f"{ERROR_FILE_TOO_LARGE} Size: {file_size_mb:.2f}MB")
        #     return

        if transcription_method == 'api' and not openai_api_key:
             from app.ui_utils import safe_error
             safe_error(self, "API Key Missing", ERROR_API_KEY_MISSING.replace("GPT processing", "API transcription"))
             return

        if speaker_detection_enabled and not hf_auth_key:
             from app.ui_utils import safe_error
             safe_error(self, "HF Token Missing", "HuggingFace Token needed for speaker detection (API Keys tab).")
             self.config_manager.set('speaker_detection_enabled', False) # Disable it in config
             self.current_recording_data['speaker_detection_enabled'] = False # Update local state if needed
             # Optionally re-enable the checkbox in settings UI here if needed
             return

        # --- Start Thread with Feedback ---
        self.is_transcribing = True
        
        # Get controls that should be disabled during transcription
        ui_elements = self.get_transcription_ui_elements()
        
        # Setup feedback
        self.feedback_manager.set_ui_busy(True, ui_elements)  
        # Start spinner animation and check the result
        spinner_active = self.feedback_manager.start_spinner('transcribe')
        assert spinner_active, "Spinner 'transcribe' failed to start"
        self.feedback_manager.show_status("Starting transcription...")
        
        # Create progress dialog for transcription
        self.transcription_progress_id = 'transcription'
        self.feedback_manager.start_progress(
            self.transcription_progress_id,
            "Transcription Progress",
            f"Transcribing {os.path.basename(file_path)}...",
            maximum=100,  # Use determinate progress if possible
            cancelable=True,
            cancel_callback=lambda: self.cancel_transcription()
        )
        
        # Emit signals
        self.status_update.emit("Starting transcription...")
        self.transcription_process_started.emit()

        self.transcription_thread = TranscriptionThread(
            file_path=file_path,
            transcription_quality=transcription_quality,
            speaker_detection_enabled=speaker_detection_enabled,
            hf_auth_key=hf_auth_key,
            language=language,
            transcription_method=transcription_method,
            openai_api_key=openai_api_key,
            hardware_acceleration_enabled=hardware_acceleration_enabled,
        )
        self.transcription_thread.completed.connect(self.on_transcription_completed)
        self.transcription_thread.update_progress.connect(self.on_transcription_progress)
        self.transcription_thread.error.connect(self.on_transcription_error)
        self.transcription_thread.finished.connect(self.on_transcription_finished)
        
        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(self.transcription_thread)
        self.transcription_thread.start()
        
    def get_transcription_ui_elements(self):
        """Get UI elements to disable during transcription."""
        elements = []

        # Settings button should always be disabled while a long‑running
        # operation is active so that configuration cannot be changed in the
        # middle of processing.
        if hasattr(self, 'settings_button'):
            elements.append(self.settings_button)

        # Disable the toolbar buttons that could start another operation while
        # the current transcription is still running.  These actions live in
        # the embedded TextEditor instance and are stored in its
        # `_toolbar_actions` dictionary.
        if hasattr(self, 'transcript_text') and hasattr(self.transcript_text, '_toolbar_actions'):
            toolbar_actions = self.transcript_text._toolbar_actions

            # Transcription button – prevent double‑clicks that would start a
            # second concurrent transcription.
            action = toolbar_actions.get('start_transcription')
            if action:
                elements.append(action)

            # While transcribing we also block GPT and smart‑formatting as they
            # both rely on the transcript that is being produced.
            for key in ('process_with_gpt4', 'smart_format'):
                act = toolbar_actions.get(key)
                if act:
                    elements.append(act)

        return elements
        
    def cancel_transcription(self):
        """Cancel an ongoing transcription operation."""
        if self.transcription_thread and self.transcription_thread.isRunning():
            logger.info("User requested cancellation of transcription")
            self.transcription_thread.cancel()
            self.feedback_manager.show_status("Cancelling transcription...")
            
    def on_transcription_progress(self, message):
        """Handle progress updates from transcription thread."""
        self.status_update.emit(message)  # Forward to status bar
        
        # Extract progress information if available - for example, "Processing chunk 2/5..."
        if "chunk" in message.lower() and "/" in message:
            try:
                parts = message.split()
                for part in parts:
                    if "/" in part:
                        current, total = map(int, part.strip(".,").split("/"))
                        # Update progress if we have a determinate operation
                        if hasattr(self, 'transcription_progress_id'):
                            self.feedback_manager.update_progress(
                                self.transcription_progress_id,
                                int(current * 100 / total),
                                message
                            )
                        return
            except (ValueError, IndexError):
                pass  # If parsing fails, treat as indeterminate
                
        # For messages without specific progress percentage, just update the message
        if hasattr(self, 'transcription_progress_id'):
            self.feedback_manager.update_progress(
                self.transcription_progress_id,
                0,  # Keep current progress value
                message
            )

    def on_transcription_completed(self, transcript):
        if not self.current_recording_data:
            return  # Recording deselected during process
        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner('transcribe')

        recording_id = self.current_recording_data['id']
        formatted_field = 'raw_transcript_formatted'
        raw_field = 'raw_transcript'

        # Check if result contains speaker labels (or use a flag from result dict)
        # Simple heuristic: check for typical speaker format like "SPEAKER_00:"
        is_formatted = transcript.strip().startswith("SPEAKER_") and ":" in transcript[:20]

        if is_formatted:
            self.transcript_text.editor.setHtml(f"<pre>{transcript}</pre>") # Basic HTML pre formatting for now
            db_value = f"<pre>{transcript}</pre>"
        else:
            self.transcript_text.editor.setPlainText(transcript)
            db_value = transcript # Store raw text if not formatted

        self.mode_switch.setValue(0) # Show raw view
        self.status_update.emit("Transcription complete. Saving...")
        
        # Update progress dialog
        if hasattr(self, 'transcription_progress_id'):
            self.feedback_manager.update_progress(
                self.transcription_progress_id,
                90,  # Show almost complete
                "Transcription finished. Saving to database..."
            )

        # Define callback for when database update completes
        def on_update_complete():
            self.current_recording_data[raw_field] = transcript # Update local data
            self.current_recording_data[formatted_field] = db_value if is_formatted else None # Store formatted if applicable
            self.status_update.emit(SUCCESS_TRANSCRIPTION)
            self.transcription_process_completed.emit(transcript) # Emit signal
            # Check if the refinement widget should be hidden (likely yes after raw transcription)
            self.refinement_widget.setVisible(False)
            logger.info(f"Transcription saved for recording ID: {recording_id}")
            
            # Update progress to 100%
            if hasattr(self, 'transcription_progress_id'):
                self.feedback_manager.update_progress(
                    self.transcription_progress_id,
                    100,  # Fully complete
                    "Transcription saved successfully!"
                )
            
            # Emit signal to update UI in other components
            status_updates = {
                'has_transcript': True,
                raw_field: transcript,
                formatted_field: db_value if is_formatted else None
            }
            self.recording_status_updated.emit(recording_id, status_updates)

        # Save the raw transcript to the database
        update_data = {raw_field: transcript}
        if is_formatted:
             update_data[formatted_field] = db_value
        else:
             update_data[formatted_field] = None # Clear formatted if saving raw

        self.db_manager.update_recording(recording_id, on_update_complete, **update_data)

    def on_transcription_error(self, error_message):
        # Show error message to user
        show_error_message(self, 'Transcription Error', error_message)
        
        # Update status feedback
        self.status_update.emit(f"Transcription failed: {error_message}")
        
        # Make sure spinner is hidden and progress indicator is closed
        if hasattr(self, 'transcription_progress_id'):
            # Show error message in progress dialog before closing it
            self.feedback_manager.update_progress(
                self.transcription_progress_id,
                0,
                f"Error: {error_message}"
            )
            self.feedback_manager.close_progress(self.transcription_progress_id)
        
        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner('transcribe')
            
        # no need to call finished manually, it will be called

    def on_transcription_finished(self):
        """Called when transcription thread finishes, regardless of success."""
        # Update state flags and UI
        self.is_transcribing = False
        self.update_ui_state()
        
        # Clean up feedback indicators
        self.feedback_manager.stop_spinner('transcribe')  
        if hasattr(self, 'transcription_progress_id'):
            # Show brief completion message before closing the dialog
            if self.transcription_thread and not self.transcription_thread.is_canceled():
                self.feedback_manager.finish_progress(
                    self.transcription_progress_id,
                    "Transcription complete!",
                    auto_close=True,
                    delay=1000  # Show completion for 1 second
                )
            else:
                # Immediate close for cancellation
                self.feedback_manager.close_progress(self.transcription_progress_id)
            
            # Clean up the progress dialog ID
            delattr(self, 'transcription_progress_id')
        
        
        # Clean up thread reference
        self.transcription_thread = None
        logger.info("Transcription thread finished.")

        # Inform listeners that the UI is ready again.
        self.status_update.emit("Ready")

    def start_gpt4_processing(self):
        if not self.current_recording_data:
            show_error_message(self, 'No Recording Selected', 'Please select a recording first.')
            return

        raw_transcript = self.current_recording_data.get('raw_transcript', '')
        if not raw_transcript:
            show_error_message(self, 'No Transcript', 'No transcript available for processing. Please transcribe first.')
            return

        # Get prompt instructions
        self.initial_prompt_instructions = self.get_current_prompt_instructions()
        if not self.initial_prompt_instructions.strip():
             show_error_message(self, 'No Prompt', 'Please select or enter a prompt.')
             return

        # Get API key using secure module
        from app.secure import get_api_key
        openai_api_key = get_api_key("OPENAI_API_KEY")
        if not openai_api_key:
            from app.ui_utils import safe_error
            safe_error(self, "API Key Missing", ERROR_API_KEY_MISSING)
            return

        # Get GPT parameters (already loaded into self.gpt_temperature/max_tokens)
        gpt_model = self.config_manager.get('gpt_model', 'gpt-4o')

        # --- Start Thread with Feedback ---
        self.is_processing_gpt4 = True
        
        # Get UI elements to disable
        ui_elements = self.get_gpt_ui_elements()
        
        # Setup feedback
        self.feedback_manager.set_ui_busy(True, ui_elements)
        # Start spinner animation and check the result
        spinner_active = self.feedback_manager.start_spinner('gpt_process')
        assert spinner_active, "Spinner 'gpt_process' failed to start"
        self.feedback_manager.show_status(f"Starting GPT processing with {gpt_model}...")
        
        # Create indeterminate progress dialog for GPT
        self.gpt_progress_id = 'gpt_process'
        self.feedback_manager.start_progress(
            self.gpt_progress_id,
            "GPT Processing",
            f"Processing transcript with {gpt_model}...",
            maximum=0,  # Indeterminate
            cancelable=True,
            cancel_callback=lambda: self.cancel_gpt_processing()
        )
        
        # Emit signals
        self.status_update.emit(f"Starting GPT processing with {gpt_model}...")
        self.gpt_process_started.emit()

        self.gpt4_processing_thread = GPT4ProcessingThread(
            transcript=raw_transcript, # Base processing always uses raw transcript
            prompt_instructions=self.initial_prompt_instructions,
            gpt_model=gpt_model,
            max_tokens=self.gpt_max_tokens,
            temperature=self.gpt_temperature,
            openai_api_key=openai_api_key
        )
        self.gpt4_processing_thread.completed.connect(self.on_gpt4_processing_completed)
        self.gpt4_processing_thread.update_progress.connect(self.on_gpt_progress)
        self.gpt4_processing_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_processing_thread.finished.connect(self.on_gpt4_processing_finished)
        
        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(self.gpt4_processing_thread)
        self.gpt4_processing_thread.start()
        
    def get_gpt_ui_elements(self):
        """Get UI elements to disable during GPT processing."""
        elements = []

        if hasattr(self, 'settings_button'):
            elements.append(self.settings_button)

        # The prompt dropdown should also be locked so the user cannot change
        # the prompt mid‑processing, which could be confusing.
        if hasattr(self, 'gpt_prompt_dropdown'):
            elements.append(self.gpt_prompt_dropdown)

        # Disable toolbar actions that launch text‑processing tasks so they
        # cannot be triggered again while GPT is already busy.
        if hasattr(self, 'transcript_text') and hasattr(self.transcript_text, '_toolbar_actions'):
            toolbar_actions = self.transcript_text._toolbar_actions
            for key in ('process_with_gpt4', 'smart_format', 'start_transcription'):
                act = toolbar_actions.get(key)
                if act:
                    elements.append(act)

        return elements
        
    def cancel_gpt_processing(self):
        """Cancel an ongoing GPT processing operation."""
        if self.gpt4_processing_thread and self.gpt4_processing_thread.isRunning():
            logger.info("User requested cancellation of GPT processing")
            self.gpt4_processing_thread.cancel()  # Call the thread's cancel method
            self.feedback_manager.show_status("Cancelling GPT processing...")
            
    def on_gpt_progress(self, message):
        """Handle progress updates from GPT thread."""
        # Update status bar
        self.status_update.emit(message)
        
        # Update progress dialog
        if hasattr(self, 'gpt_progress_id'):
            self.feedback_manager.update_progress(
                self.gpt_progress_id,
                0,  # Still indeterminate
                message
            )

    def on_gpt4_processing_completed(self, processed_text):
        if not self.current_recording_data:
            return  # No recording selected
        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner('gpt_process')

        recording_id = self.current_recording_data['id']
        formatted_field = 'processed_text_formatted'
        raw_field = 'processed_text'

        # Preserve formatting if the result looks like HTML
        is_html = "<" in processed_text and ">" in processed_text
        if is_html:
            self.transcript_text.editor.setHtml(processed_text)
            db_value = processed_text
            self.last_processed_text_html = db_value # Store for refinement
        else:
            self.transcript_text.editor.setPlainText(processed_text)
            db_value = processed_text
            self.last_processed_text_html = None # Not HTML

        self.mode_switch.setValue(1) # Switch to processed view
        self.status_update.emit("GPT processing complete. Saving...")

        # Define callback for DB update
        def on_update_complete():
            self.current_recording_data[raw_field] = processed_text # Update local data
            self.current_recording_data[formatted_field] = db_value if is_html else None
            self.status_update.emit(SUCCESS_GPT_PROCESSING)
            self.gpt_process_completed.emit(processed_text) # Emit signal
            self.refinement_widget.setVisible(True) # Show refinement options
            logger.info(f"GPT processing saved for recording ID: {recording_id}")
            
            # Emit signal to update UI in other components
            status_updates = {
                'has_processed': True,
                raw_field: processed_text,
                formatted_field: db_value if is_html else None
            }
            self.recording_status_updated.emit(recording_id, status_updates)

        # Save processed text to DB
        update_data = {raw_field: processed_text}
        if is_html:
             update_data[formatted_field] = db_value
        else:
             update_data[formatted_field] = None # Clear formatted if saving raw

        self.db_manager.update_recording(recording_id, on_update_complete, **update_data)


    def on_gpt4_processing_error(self, error_message):
        # Show error to user
        show_error_message(self, 'GPT Processing Error', error_message)
        
        # Update status
        self.status_update.emit(f"GPT processing failed: {error_message}")
        
        # Reset feedback
        if hasattr(self, 'gpt_progress_id'):
            self.feedback_manager.close_progress(self.gpt_progress_id)
            
        # Reset any processing buttons - now using the more generic toggle mechanism
        if hasattr(self.transcript_text, 'toggle_spinner'):
            # Try to reset all potential processing buttons
            self.transcript_text.toggle_spinner('smart_format')
            self.transcript_text.toggle_spinner('gpt')
            self.transcript_text.toggle_spinner('transcription')
        
        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner('gpt_process')
        
        # Finished signal will handle cleanup

    def on_gpt4_processing_finished(self):
        """Called when GPT processing thread finishes."""
        # Update state flags
        self.is_processing_gpt4 = False
        self.update_ui_state()
        
        # Clean up feedback
        self.feedback_manager.stop_spinner('gpt_process')
        if hasattr(self, 'gpt_progress_id'):
            self.feedback_manager.close_progress(self.gpt_progress_id)
            delattr(self, 'gpt_progress_id')
            
        
        # Clean up thread reference
        self.gpt4_processing_thread = None
        logger.info("GPT processing thread finished.")

        self.status_update.emit("Ready")

    def start_smart_format_processing(self, text_to_format):
        if not text_to_format.strip():
            show_error_message(self, 'Empty Text', 'There is no text to format.')
            return

        from app.secure import get_api_key
        openai_api_key = get_api_key("OPENAI_API_KEY")
        if not openai_api_key:
            from app.ui_utils import safe_error
            safe_error(self, "API Key Missing", ERROR_API_KEY_MISSING)
            return

        # Use a simpler prompt for formatting
        prompt_instructions = "Format the following text using HTML for readability (e.g., paragraphs, lists, bolding). Do not change the content. Output only the HTML."

        gpt_model = 'gpt-4o-mini' # Cheaper/faster model suitable for formatting

        # --- Start Thread with Feedback ---
        self.is_processing_gpt4 = True
        
        # Setup feedback
        ui_elements = self.get_gpt_ui_elements()
        self.feedback_manager.set_ui_busy(True, ui_elements)
        # Start spinner animation and check the result
        spinner_active = self.feedback_manager.start_spinner('smart_format')
        assert spinner_active, "Spinner 'smart_format' failed to start"
        self.feedback_manager.show_status(f"Starting smart formatting with {gpt_model}...")
        
        # Create progress indicator
        self.smart_format_progress_id = 'smart_format'
        self.feedback_manager.start_progress(
            self.smart_format_progress_id,
            "Smart Formatting",
            f"Applying smart formatting with {gpt_model}...",
            maximum=0,  # Indeterminate
            cancelable=True,
            cancel_callback=lambda: self.cancel_smart_formatting()
        )
        
        # Emit signals
        self.status_update.emit(f"Starting smart formatting with {gpt_model}...")
        self.gpt_process_started.emit() # Reuse signal

        self.gpt4_smart_format_thread = GPT4ProcessingThread(
            transcript=text_to_format,
            prompt_instructions=prompt_instructions,
            gpt_model=gpt_model,
            max_tokens=self.gpt_max_tokens, # Use existing setting
            temperature=0.3, # Lower temp for formatting
            openai_api_key=openai_api_key
        )
        self.gpt4_smart_format_thread.completed.connect(self.on_smart_format_completed)
        self.gpt4_smart_format_thread.update_progress.connect(self.on_smart_format_progress)
        self.gpt4_smart_format_thread.error.connect(self.on_smart_format_error)
        self.gpt4_smart_format_thread.finished.connect(self.on_smart_format_finished)
        
        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(self.gpt4_smart_format_thread)
        self.gpt4_smart_format_thread.start()
        
    def cancel_smart_formatting(self):
        """Cancel an ongoing smart formatting operation."""
        if self.gpt4_smart_format_thread and self.gpt4_smart_format_thread.isRunning():
            logger.info("User requested cancellation of smart formatting")
            self.gpt4_smart_format_thread.cancel()
            self.feedback_manager.show_status("Cancelling smart formatting...")
            
    def on_smart_format_progress(self, message):
        """Handle progress updates from smart format thread."""
        self.status_update.emit(message)
        
        if hasattr(self, 'smart_format_progress_id'):
            self.feedback_manager.update_progress(
                self.smart_format_progress_id,
                0,  # Still indeterminate
                message
            )
    
    def on_smart_format_error(self, error_message):
        """Handle errors from smart format thread."""
        # Show error to user
        show_error_message(self, 'Smart Format Error', error_message)
        
        # Update status
        self.status_update.emit(f"Smart formatting failed: {error_message}")
        
        # Reset feedback
        if hasattr(self, 'smart_format_progress_id'):
            self.feedback_manager.close_progress(self.smart_format_progress_id)
            
        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner('smart_format')
            
    def on_smart_format_finished(self):
        """Called when smart formatting thread finishes."""
        # Update state flags
        self.is_processing_gpt4 = False
        self.update_ui_state()
        
        # Clean up feedback
        self.feedback_manager.stop_spinner('smart_format')
        if hasattr(self, 'smart_format_progress_id'):
            self.feedback_manager.close_progress(self.smart_format_progress_id)
            delattr(self, 'smart_format_progress_id')
            
        
        # Clean up thread reference
        self.gpt4_smart_format_thread = None
        logger.info("Smart formatting thread finished.")

        self.status_update.emit("Ready")


    def on_smart_format_completed(self, formatted_html):
        if not self.current_recording_data:
            return  # Check if recording is still selected

        # Reset smart format button state and stop spinner
        if hasattr(self.transcript_text, 'toggle_spinner'):
            self.transcript_text.toggle_spinner('smart_format')
        # Ensure spinner is stopped (redundant cleanup)
        self.feedback_manager.stop_spinner('smart_format')

        recording_id = self.current_recording_data['id']
        current_view_is_raw = (self.mode_switch.value() == 0)

        if formatted_html:
            self.transcript_text.editor.setHtml(formatted_html)
            self.status_update.emit("Smart formatting applied. Saving...")

            # Determine which field to save to based on current view
            if current_view_is_raw:
                 field_to_update = 'raw_transcript_formatted'
                 raw_field = 'raw_transcript' # Keep raw text as is
                 db_update_data = {field_to_update: formatted_html}
            else:
                 field_to_update = 'processed_text_formatted'
                 raw_field = 'processed_text' # Update the processed raw text as well? Maybe not.
                 db_update_data = {field_to_update: formatted_html}
                 # Also update self.last_processed_text_html for refinement
                 self.last_processed_text_html = formatted_html

            def on_update_complete():
                self.current_recording_data[field_to_update] = formatted_html
                # Don't update the underlying raw_transcript or processed_text fields here
                # unless that's the desired behavior. Formatting is separate.
                self.status_update.emit("Smart formatting saved.")
                self.gpt_process_completed.emit(formatted_html) # Reuse signal
                if not current_view_is_raw:
                    self.refinement_widget.setVisible(True) # Show refinement if we were in processed view

            self.db_manager.update_recording(recording_id, on_update_complete, **db_update_data)

        else:
            show_error_message(self, 'Formatting Failed', 'Smart formatting did not return any content.')
            self.status_update.emit("Smart formatting failed.")


    def start_refinement_processing(self):
        if not self.current_recording_data:
            show_error_message(self, "No Recording", "No recording selected for refinement.")
            return

        refinement_instructions = self.refinement_input.text().strip()
        if not refinement_instructions:
            show_error_message(self, "No Instructions", "Please enter refinement instructions.")
            return

        # Get necessary data
        raw_transcript = self.current_recording_data.get('raw_transcript', '')
        # Use the last *saved* processed text as the base for refinement
        last_processed = ""
        if self.last_processed_text_html:
            last_processed = self.last_processed_text_html
        elif self.current_recording_data and 'processed_text' in self.current_recording_data:
            last_processed = self.current_recording_data.get('processed_text', '')
            
        # Use the prompt that *generated* the last_processed text
        initial_prompt = self.initial_prompt_instructions or "No initial prompt recorded."

        if not raw_transcript:
             show_error_message(self, "Missing Data", "Original transcript is missing.")
             return
        if not last_processed:
             show_error_message(self, "Missing Data", "Previous processed text is missing. Please process first.")
             return

        from app.secure import get_api_key
        openai_api_key = get_api_key("OPENAI_API_KEY")
        if not openai_api_key:
            from app.ui_utils import safe_error
            safe_error(self, "API Key Missing", ERROR_API_KEY_MISSING)
            return

        # --- Prepare messages for conversational refinement ---
        system_prompt = (
             f"You are an AI assistant refining previously processed text. "
             f"The original text was processed with the prompt: '{initial_prompt}'. "
             f"Now, apply the following refinement instructions: '{refinement_instructions}'. "
             f"Maintain the original HTML formatting if present in the 'assistant' message. "
             f"Output only the fully refined text, including necessary HTML tags if the input had them."
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f"Original Transcript:\n{raw_transcript}"}, # Provide original as context
            {'role': 'assistant', 'content': last_processed}, # Provide the text to be refined
            {'role': 'user', 'content': refinement_instructions} # The new instruction
        ]

        # --- Start Thread with Feedback ---
        self.is_processing_gpt4 = True
        
        # Set up feedback
        ui_elements = self.get_gpt_ui_elements() + [self.refinement_input, self.refinement_submit_button]
        self.feedback_manager.set_ui_busy(True, ui_elements)
        # Start spinner animation and check the result
        spinner_active = self.feedback_manager.start_spinner('refinement')
        assert spinner_active, "Spinner 'refinement' failed to start"
        self.feedback_manager.show_status("Starting refinement processing...")
        
        # Create progress indicator
        self.refinement_progress_id = 'refinement'
        self.feedback_manager.start_progress(
            self.refinement_progress_id,
            "Text Refinement",
            "Applying refinement instructions...",
            maximum=0,  # Indeterminate
            cancelable=True,
            cancel_callback=lambda: self.cancel_refinement()
        )
        
        # Emit signals
        self.status_update.emit("Starting refinement processing...")
        self.gpt_process_started.emit() # Reuse signal

        gpt_model = self.config_manager.get('gpt_model', 'gpt-4o')
        self.gpt4_refinement_thread = GPT4ProcessingThread(
            transcript="", # Not directly used when messages are provided
            prompt_instructions="", # Not directly used when messages are provided
            gpt_model=gpt_model,
            max_tokens=self.gpt_max_tokens,
            temperature=self.gpt_temperature,
            openai_api_key=openai_api_key,
            messages=messages # Use the constructed messages
        )
        # Connect signals
        self.gpt4_refinement_thread.completed.connect(self.on_refinement_completed)
        self.gpt4_refinement_thread.update_progress.connect(self.on_refinement_progress)
        self.gpt4_refinement_thread.error.connect(self.on_refinement_error)
        self.gpt4_refinement_thread.finished.connect(self.on_refinement_finished)
        
        # Register thread with ThreadManager
        ThreadManager.instance().register_thread(self.gpt4_refinement_thread)
        self.gpt4_refinement_thread.start()
        
    def cancel_refinement(self):
        """Cancel an ongoing refinement operation."""
        if self.gpt4_refinement_thread and self.gpt4_refinement_thread.isRunning():
            logger.info("User requested cancellation of refinement")
            self.gpt4_refinement_thread.cancel()
            self.feedback_manager.show_status("Cancelling refinement...")
            
    def on_refinement_progress(self, message):
        """Handle progress updates from refinement thread."""
        self.status_update.emit(message)
        
        if hasattr(self, 'refinement_progress_id'):
            self.feedback_manager.update_progress(
                self.refinement_progress_id,
                0,  # Still indeterminate
                message
            )
            
    def on_refinement_error(self, error_message):
        """Handle errors from refinement thread."""
        # Show error to user
        show_error_message(self, 'Refinement Error', error_message)
        
        # Update status
        self.status_update.emit(f"Refinement failed: {error_message}")
        
        # Reset feedback
        if hasattr(self, 'refinement_progress_id'):
            self.feedback_manager.close_progress(self.refinement_progress_id)
            
        # Stop spinner; UI re-enable will occur when all operations finish
        self.feedback_manager.stop_spinner('refinement')
        
    def on_refinement_finished(self):
        """Called when refinement thread finishes."""
        # Update state flags
        self.is_processing_gpt4 = False
        self.update_ui_state()
        
        # Clean up feedback
        self.feedback_manager.stop_spinner('refinement')
        if hasattr(self, 'refinement_progress_id'):
            self.feedback_manager.close_progress(self.refinement_progress_id)
            delattr(self, 'refinement_progress_id')
            
        
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
        self.feedback_manager.stop_spinner('refinement')

        if not self.current_recording_data: return

        if refined_text:
            recording_id = self.current_recording_data['id']
            formatted_field = 'processed_text_formatted'
            raw_field = 'processed_text'

            # Update the editor with the refined text
            is_html = "<" in refined_text and ">" in refined_text
            if is_html:
                self.transcript_text.editor.setHtml(refined_text)
                db_value = refined_text
                self.last_processed_text_html = db_value # Update last processed text
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                db_value = refined_text
                self.last_processed_text_html = None

            self.status_update.emit("Refinement complete. Saving...")

            # Define callback for database update completion
            def on_update_complete():
                self.current_recording_data[raw_field] = refined_text # Update local data
                self.current_recording_data[formatted_field] = db_value if is_html else None
                self.status_update.emit("Refinement saved.")
                self.gpt_process_completed.emit(refined_text) # Emit signal
                logger.info(f"Refinement saved for recording ID: {recording_id}")

            # Save the refined text to the database
            update_data = {raw_field: refined_text}
            if is_html:
                 update_data[formatted_field] = db_value
            else:
                 update_data[formatted_field] = None # Clear formatted if saving raw

            self.db_manager.update_recording(recording_id, on_update_complete, **update_data)
        else:
            show_error_message(self, "Refinement Error", "GPT-4 did not return any refined text.")
            self.status_update.emit("Refinement failed.")

    def get_current_prompt_instructions(self):
        """Retrieve the current prompt instructions based on selected prompt."""
        current_index = self.gpt_prompt_dropdown.currentIndex()
        selected_data = self.gpt_prompt_dropdown.itemData(current_index)

        if selected_data == "CUSTOM":
            return self.custom_prompt_input.toPlainText()
        else:
            # Retrieve using the real prompt name stored in UserData
            prompt_name = selected_data
            return self.prompt_manager.get_prompt_text(prompt_name) or ""

    # --- UI State Management ---

    def on_recording_item_selected(self, recording_item: 'RecordingListItem'):
        """Handle the event when a recording item is selected."""
        if not recording_item:
            self.current_recording_data = None
            self.transcript_text.clear()
            self.update_ui_state()
            return

        recording_id = recording_item.get_id()
        logger.info(f"Loading recording ID: {recording_id}")

        # Define callback for database query
        def on_recording_loaded(db_data):
            if db_data:
                self.current_recording_data = {
                    'id': db_data[0],
                    'filename': db_data[1],
                    'file_path': db_data[2],
                    'date_created': db_data[3],
                    'duration': db_data[4],
                    'raw_transcript': db_data[5] or "",
                    'processed_text': db_data[6] or "",
                    'raw_transcript_formatted': db_data[7], # Might be None
                    'processed_text_formatted': db_data[8]  # Might be None
                }
                logger.debug(f"Loaded data: {self.current_recording_data}")

                # Reset processing states for the new item
                self.is_transcribing = False
                self.is_processing_gpt4 = False
                self.initial_prompt_instructions = None # Reset initial prompt
                self.last_processed_text_html = self.current_recording_data.get('processed_text_formatted') # Load last saved formatted

                # Set the editor content based on the mode switch
                self.toggle_transcription_view()
                self.update_ui_state()

            else:
                show_error_message(self, 'Error', f"Could not load recording data for ID: {recording_id}")
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

        is_raw_view = (self.mode_switch.value() == 0)

        if is_raw_view:
            # Show raw transcript (formatted if available, else raw)
            content_to_show = self.current_recording_data.get('raw_transcript_formatted') or \
                              self.current_recording_data.get('raw_transcript', '')
            self.transcript_text.deserialize_text_document(content_to_show)
            self.refinement_widget.setVisible(False)
        else:
            # Show processed text (formatted if available, else raw)
            content_to_show = self.current_recording_data.get('processed_text_formatted') or \
                              self.current_recording_data.get('processed_text', '')
            self.transcript_text.deserialize_text_document(content_to_show)
            # Show refinement only if there is processed text and not currently processing
            can_refine = bool(content_to_show) and not self.is_processing_gpt4
            self.refinement_widget.setVisible(can_refine)
            
        # Ensure editor is properly updated and repainted
        self.transcript_text.repaint()
        self.transcript_text.editor.repaint()

    def on_mode_switch_changed(self, value):
        """Handle changes in the mode switch."""
        self.toggle_transcription_view()
        self.update_ui_state() # Update button states etc.

    def update_ui_state(self):
        """Update the UI elements based on the current state."""
        has_recording = self.current_recording_data is not None
        has_raw_transcript = has_recording and bool(self.current_recording_data.get('raw_transcript'))
        has_processed_text = has_recording and (
            bool(self.current_recording_data.get('processed_text')) or
            bool(self.current_recording_data.get('processed_text_formatted'))
        )
        is_raw_mode = self.mode_switch.value() == 0

        # Enable/disable transcription and GPT processing buttons in TextEditor toolbar
        if hasattr(self.transcript_text, '_toolbar_actions'):
             # Can always transcribe if a recording is selected (will overwrite)
             self.transcript_text._toolbar_actions['start_transcription'].setEnabled(has_recording and not self.is_transcribing)
             # Can process if raw transcript exists and not busy
             self.transcript_text._toolbar_actions['process_with_gpt4'].setEnabled(has_raw_transcript and not self.is_transcribing and not self.is_processing_gpt4)
             # Can smart format if text editor has content and not busy
             can_smart_format = bool(self.transcript_text.toPlainText().strip()) and not self.is_transcribing and not self.is_processing_gpt4
             self.transcript_text._toolbar_actions['smart_format'].setEnabled(can_smart_format)
             # Can save if a recording is selected and not busy
             self.transcript_text._toolbar_actions['save'].setEnabled(has_recording and not self.is_transcribing and not self.is_processing_gpt4)


        # Toggle refinement widget visibility (also handled in toggle_transcription_view)
        show_refine = (not is_raw_mode) and has_processed_text and not self.is_processing_gpt4
        self.refinement_widget.setVisible(show_refine)
        self.refinement_input.setEnabled(show_refine)
        self.refinement_submit_button.setEnabled(show_refine)

        # Enable/disable main dropdowns based on processing state
        processing_busy = self.is_transcribing or self.is_processing_gpt4
        self.gpt_prompt_dropdown.setEnabled(not processing_busy)
        self.edit_prompt_button.setEnabled(not processing_busy and self.gpt_prompt_dropdown.itemData(self.gpt_prompt_dropdown.currentIndex()) != "CUSTOM")
        self.mode_switch.setEnabled(not processing_busy and has_recording) # Can only switch if recording loaded


    def save_editor_state(self):
        """Save the current state of the text editor to the database."""
        if not self.current_recording_data:
            show_error_message(self, 'No Recording Selected', 'Please select a recording to save.')
            return

        recording_id = self.current_recording_data['id']
        editor_html = self.transcript_text.editor.toHtml()
        editor_plain = self.transcript_text.editor.toPlainText()

        if not editor_html: # Should ideally not happen with QTextEdit
            show_error_message(self, 'Save Error', 'Cannot retrieve editor content.')
            return

        is_raw_view = (self.mode_switch.value() == 0)
        update_data = {}

        if is_raw_view:
            # Saving the raw view - update raw_transcript_formatted and raw_transcript
            update_data['raw_transcript_formatted'] = editor_html
            update_data['raw_transcript'] = editor_plain # Store plain text version too
            field_saved = "Raw transcript"
        else:
            # Saving the processed view - update processed_text_formatted and processed_text
            update_data['processed_text_formatted'] = editor_html
            update_data['processed_text'] = editor_plain # Store plain text version
            field_saved = "Processed text"
            self.last_processed_text_html = editor_html # Update last processed state

        # Define callback for database update
        def on_update_complete():
            # Update local cache
            self.current_recording_data.update(update_data)
            show_info_message(self, "Save Successful", f"{field_saved} saved successfully.")
            self.save_operation_completed.emit(f"{field_saved} saved.")

        # Execute database update
        self.db_manager.update_recording(recording_id, on_update_complete, **update_data)


    def open_settings_dialog(self):
        """Open the settings dialog."""
        # SettingsDialog now manages its own state and interacts with managers
        dialog = SettingsDialog(parent=self) # Pass self as parent only
        # No need to connect signals like settings_changed or prompts_updated
        dialog.exec()
