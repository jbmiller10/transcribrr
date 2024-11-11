import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QComboBox, QHBoxLayout, QLabel,
    QSizePolicy, QTextEdit, QDoubleSpinBox, QSpinBox, QInputDialog, QSplitter, QPushButton
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal, QSize, Qt
from app.TextEditor import TextEditor
from app.threads.TranscriptionThread import TranscriptionThread
from app.threads.GPT4ProcessingThread import GPT4ProcessingThread
from app.SettingsDialog import SettingsDialog
from app.ToggleSwitch import ToggleSwitch
import traceback
import keyring
from app.database import create_connection, get_recording_by_id, update_recording


class MainTranscriptionWidget(QWidget):
    transcriptionStarted = pyqtSignal()
    transcriptionCompleted = pyqtSignal(str)
    transcriptionStopped = pyqtSignal()
    transcriptionSaved = pyqtSignal(str)
    settingsRequested = pyqtSignal()
    update_progress = pyqtSignal(str)
    current_selected_item = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Initialize state variables
        self.is_editing_existing_prompt = False

        # Top toolbar layout
        self.top_toolbar = QHBoxLayout()
        self.init_top_toolbar()
        self.layout.addLayout(self.top_toolbar)

        # Main splitter
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.main_splitter)

        # Custom prompt input (hidden by default)
        self.custom_prompt_input = QTextEdit()
        self.custom_prompt_input.setPlaceholderText("Enter your custom prompt here...")
        self.custom_prompt_input.setVisible(False)
        self.custom_prompt_input.setMaximumHeight(100)  # Adjust height as needed

        # Custom prompt save button (hidden by default)
        self.custom_prompt_save_button = QPushButton("Save as Template")
        self.custom_prompt_save_button.setVisible(False)
        self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)

        # Edit prompt button (visible when predefined prompt is selected)
        self.edit_prompt_button = QPushButton("Edit Prompt")
        self.edit_prompt_button.setVisible(False)
        self.edit_prompt_button.clicked.connect(self.edit_selected_prompt)

        # Create a widget to hold buttons below the custom prompt input
        self.prompt_button_widget = QWidget()
        self.prompt_button_layout = QHBoxLayout(self.prompt_button_widget)
        self.prompt_button_layout.addWidget(self.custom_prompt_save_button)
        self.prompt_button_layout.addWidget(self.edit_prompt_button)
        self.prompt_button_layout.addStretch()
        self.prompt_button_widget.setVisible(False)

        # Add custom prompt input and buttons to a container widget
        self.prompt_widget = QWidget()
        self.prompt_layout = QVBoxLayout(self.prompt_widget)
        self.prompt_layout.setContentsMargins(0, 0, 0, 0)
        self.prompt_layout.addWidget(self.custom_prompt_input)
        self.prompt_layout.addWidget(self.prompt_button_widget)

        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        # Add GPT-4 parameter controls
        self.init_gpt_parameters()
        self.content_layout.addLayout(self.gpt_parameter_layout)

        # Text editor
        self.transcript_text = TextEditor()
        self.content_layout.addWidget(self.transcript_text)

        # Add widgets to splitter
        self.main_splitter.addWidget(self.prompt_widget)
        self.main_splitter.addWidget(self.content_widget)

        # Initially hide the custom prompt input
        self.custom_prompt_input.setVisible(False)
        self.prompt_button_widget.setVisible(False)
        self.prompt_widget.setVisible(False)

        # Connect signals and slots
        self.transcript_text.transcription_requested.connect(self.start_transcription)
        self.transcript_text.gpt4_processing_requested.connect(self.start_gpt4_processing)
        self.mode_switch.valueChanged.connect(self.toggle_transcription_view)
        self.settings_button.clicked.connect(self.request_settings)
        self.transcript_text.save_requested.connect(self.save_editor_state)
        self.gpt_prompt_dropdown.currentIndexChanged.connect(self.on_prompt_selection_changed)

        # Connect smart format signal
        self.transcript_text.smart_format_requested.connect(self.start_smart_format_processing)

        self.file_path = None
        self.is_transcribing = False
        self.is_processing_gpt4 = False

    def init_top_toolbar(self):
        # Initialize the prompt dropdown
        self.gpt_prompt_dropdown = QComboBox()

        # Load the prompts (this will add "Custom Prompt" as well)
        self.load_prompts()

        # Connect signals
        self.gpt_prompt_dropdown.currentIndexChanged.connect(self.on_prompt_selection_changed)

        # Mode switch and labels
        self.raw_transcript_label = QLabel('Raw Transcript')
        self.mode_switch = ToggleSwitch()
        self.mode_switch.setValue(0)
        self.gpt_processed_label = QLabel('Processed w/ GPT')

        # Settings button
        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon('icons/settings.svg'))
        self.settings_button.setIconSize(QSize(25, 25))
        self.settings_button.setFixedSize(30, 30)

        # Layout adjustments
        self.top_toolbar.addWidget(self.gpt_prompt_dropdown)
        self.top_toolbar.addStretch()
        self.top_toolbar.addWidget(self.raw_transcript_label)
        self.top_toolbar.addWidget(self.mode_switch)
        self.top_toolbar.addWidget(self.gpt_processed_label)
        self.top_toolbar.addStretch()
        self.top_toolbar.addWidget(self.settings_button)

    def init_gpt_parameters(self):
        # Load existing config or defaults
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
        except FileNotFoundError:
            config = {'temperature': 1.0, 'max_tokens': 16000}

        # Temperature control
        self.temperature_label = QLabel("Temperature:")
        self.temperature_spinbox = QDoubleSpinBox()
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setValue(config.get('temperature', 1.0))

        # Max tokens control
        self.max_tokens_label = QLabel("Max Tokens:")
        self.max_tokens_spinbox = QSpinBox()
        self.max_tokens_spinbox.setRange(1, 16000)
        self.max_tokens_spinbox.setValue(config.get('max_tokens', 16000))

        # GPT parameter layout
        self.gpt_parameter_layout = QHBoxLayout()
        self.gpt_parameter_layout.addWidget(self.temperature_label)
        self.gpt_parameter_layout.addWidget(self.temperature_spinbox)
        self.gpt_parameter_layout.addWidget(self.max_tokens_label)
        self.gpt_parameter_layout.addWidget(self.max_tokens_spinbox)
        self.gpt_parameter_layout.addStretch()

    def on_prompt_selection_changed(self, index):
        selected_prompt = self.gpt_prompt_dropdown.currentText()
        if selected_prompt == "Custom Prompt":
            self.is_editing_existing_prompt = False
            self.show_custom_prompt_input()
            self.edit_prompt_button.setVisible(False)
            self.custom_prompt_input.clear()
            self.custom_prompt_save_button.setText("Save as Template")
            self.custom_prompt_save_button.clicked.disconnect()
            self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
        else:
            self.hide_custom_prompt_input()
            self.edit_prompt_button.setVisible(True)
            self.prompt_button_widget.setVisible(True)
            self.prompt_widget.setVisible(True)
            self.is_editing_existing_prompt = False
            self.edit_prompt_button.setText("Edit Prompt")

    def show_custom_prompt_input(self):
        self.prompt_widget.setVisible(True)
        self.custom_prompt_input.setVisible(True)
        self.prompt_button_widget.setVisible(True)
        self.custom_prompt_input.setMaximumHeight(100)
        self.main_splitter.setSizes([100, 400])
        if self.is_editing_existing_prompt:
            self.custom_prompt_save_button.setVisible(True)
            self.custom_prompt_save_button.setText("Save")
        else:
            self.custom_prompt_save_button.setVisible(True)
            self.custom_prompt_save_button.setText("Save as Template")

    def hide_custom_prompt_input(self):
        self.custom_prompt_input.setVisible(False)
        self.custom_prompt_save_button.setVisible(False)
        self.prompt_button_widget.setVisible(False)
        self.prompt_widget.setVisible(False)
        self.main_splitter.setSizes([0, 500])

    def save_custom_prompt_as_template(self):
        prompt_name, ok = QInputDialog.getText(self, 'Save Prompt', 'Enter a name for this prompt template:')
        if ok and prompt_name:
            prompt_text = self.custom_prompt_input.toPlainText()
            self.preset_prompts[prompt_name] = prompt_text
            # Save to 'preset_prompts.json'
            with open('preset_prompts.json', 'w') as f:
                json.dump(self.preset_prompts, f, indent=4)
            QMessageBox.information(self, "Prompt Saved", f"Prompt '{prompt_name}' has been saved.")
            # Reload prompts in the dropdown
            self.load_prompts()
            self.gpt_prompt_dropdown.setCurrentText(prompt_name)
            # Hide the custom prompt input area
            self.hide_custom_prompt_input()
            self.is_editing_existing_prompt = False
            self.custom_prompt_save_button.clicked.disconnect()
            self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)

    def edit_selected_prompt(self):
        if self.is_editing_existing_prompt:
            # Cancel editing
            self.hide_custom_prompt_input()
            self.edit_prompt_button.setText("Edit Prompt")
            self.is_editing_existing_prompt = False
            # Reconnect the save button to default action
            self.custom_prompt_save_button.clicked.disconnect()
            self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
        else:
            # Start editing
            selected_prompt = self.gpt_prompt_dropdown.currentText()
            if selected_prompt in self.preset_prompts:
                self.is_editing_existing_prompt = True
                self.custom_prompt_input.setPlainText(self.preset_prompts[selected_prompt])
                self.show_custom_prompt_input()
                self.edit_prompt_button.setText("Cancel Edit")
                self.custom_prompt_save_button.setText("Save")
                self.custom_prompt_save_button.clicked.disconnect()
                self.custom_prompt_save_button.clicked.connect(self.save_edited_prompt)

    def save_edited_prompt(self):
        edited_text = self.custom_prompt_input.toPlainText()
        selected_prompt = self.gpt_prompt_dropdown.currentText()
        self.preset_prompts[selected_prompt] = edited_text
        # Save to 'preset_prompts.json'
        with open('preset_prompts.json', 'w') as f:
            json.dump(self.preset_prompts, f, indent=4)
        QMessageBox.information(self, "Prompt Updated", f"Prompt '{selected_prompt}' has been updated.")
        # Hide the custom prompt input area
        self.hide_custom_prompt_input()
        self.edit_prompt_button.setText("Edit Prompt")
        self.is_editing_existing_prompt = False
        self.custom_prompt_save_button.clicked.disconnect()
        self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
        # Reload prompts
        self.load_prompts()
        self.gpt_prompt_dropdown.setCurrentText(selected_prompt)

    def request_settings(self):
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.load_config)
        dialog.prompts_updated.connect(self.load_prompts)
        dialog.exec()

    def load_prompts(self):
        try:
            with open('preset_prompts.json', 'r') as file:
                self.preset_prompts = json.load(file)
        except FileNotFoundError:
            print('No existing prompts file found. Using Defaults.')
            self.preset_prompts = {
                "Journal Entry Formatting": "Format this raw audio transcript into a clean, coherent journal entry, maintaining a first-person narrative style.",
                "Meeting Minutes": "Convert this transcript into a structured format of meeting minutes, highlighting key points, decisions made, and action items.",
                "Interview Summary": "Summarize this interview transcript, emphasizing the main questions, responses, and any significant insights or conclusions.",
            }
        self.gpt_prompt_dropdown.blockSignals(True)
        self.gpt_prompt_dropdown.clear()
        self.gpt_prompt_dropdown.addItems(self.preset_prompts.keys())
        self.gpt_prompt_dropdown.addItem("Custom Prompt")  # Ensure "Custom Prompt" is added here
        self.gpt_prompt_dropdown.blockSignals(False)

    def start_transcription(self):
        self.transcript_text.toggle_transcription_spinner()
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording to transcribe.')
            self.transcript_text.toggle_transcription_spinner()
            return

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)
        self.service_id = "transcription_application"
        self.transcription_thread = TranscriptionThread(
            file_path=self.file_path,
            transcription_quality=config.get('transcription_quality', 'medium'),
            speaker_detection_enabled=config.get('speaker_detection_enabled', False),
            hf_auth_key=keyring.get_password(self.service_id, "HF_AUTH_TOKEN")
        )
        self.transcription_thread.completed.connect(self.on_transcription_completed)
        self.transcription_thread.update_progress.connect(self.on_transcription_progress)
        self.transcription_thread.error.connect(self.on_transcription_error)
        self.transcription_thread.start()
        self.is_transcribing = True
        self.update_ui_state()

    def on_transcription_completed(self, transcript):
        self.transcript_text.editor.setPlainText(transcript)
        recording_id = self.current_selected_item.get_id()
        self.mode_switch.setValue(0)
        self.transcript_text.editor.setPlainText(transcript)
        conn = create_connection("./database/database.sqlite")
        update_recording(conn, recording_id, raw_transcript=transcript)
        conn.close()
        self.is_transcribing = False
        self.transcript_text.toggle_transcription_spinner()
        self.update_ui_state()

    def on_transcription_progress(self, progress_message):
        self.update_progress.emit(progress_message)

    def on_transcription_error(self, error_message):
        QMessageBox.critical(self, 'Transcription Error', error_message)
        self.is_transcribing = False
        self.transcript_text.toggle_transcription_spinner()
        self.update_ui_state()

    def start_gpt4_processing(self):
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording first.')
            return

        recording_id = self.current_selected_item.get_id()
        conn = create_connection("./database/database.sqlite")

        if conn is None:
            QMessageBox.critical(self, 'Database Error', 'Unable to connect to the database.')
            return

        recording = get_recording_by_id(conn, recording_id)
        conn.close()

        if recording is None:
            QMessageBox.warning(self, 'Recording Not Found', f'No recording found with ID: {recording_id}')
            return
        raw_transcript = recording[5] if recording else ""

        selected_prompt_key = self.gpt_prompt_dropdown.currentText()
        if selected_prompt_key == "Custom Prompt":
            prompt_instructions = self.custom_prompt_input.toPlainText()
            if not prompt_instructions.strip():
                QMessageBox.warning(self, 'Empty Prompt', 'Please enter a custom prompt or select a predefined one.')
                return
        else:
            prompt_instructions = self.preset_prompts.get(selected_prompt_key, '')

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        self.gpt4_processing_thread = GPT4ProcessingThread(
            transcript=raw_transcript,
            prompt_instructions=prompt_instructions,
            gpt_model=config.get('gpt_model', 'gpt-4'),
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key
        )
        self.gpt4_processing_thread.completed.connect(self.on_gpt4_processing_completed)
        self.gpt4_processing_thread.update_progress.connect(self.on_gpt4_processing_progress)
        self.gpt4_processing_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_processing_thread.start()
        self.is_processing_gpt4 = True
        self.transcript_text.toggle_gpt_spinner()
        self.update_ui_state()

    def on_gpt4_processing_completed(self, processed_text):
        if self.current_selected_item:
            self.mode_switch.setValue(1)
            if "<" in processed_text and ">" in processed_text:
                self.transcript_text.editor.setHtml(processed_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(processed_text)
                formatted_field = 'processed_text'
            recording_id = self.current_selected_item.get_id()
            conn = create_connection("./database/database.sqlite")
            update_recording(conn, recording_id, **{formatted_field: processed_text})
            conn.close()
            self.is_transcribing = False
            self.transcript_text.toggle_gpt_spinner()
            self.update_ui_state()

    def on_gpt4_processing_progress(self, progress_message):
        self.update_progress.emit(progress_message)

    def on_gpt4_processing_error(self, error_message):
        self.transcript_text.toggle_gpt_spinner()
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def toggle_transcription_view(self):
        if self.current_selected_item is not None:
            recording_id = self.current_selected_item.get_id()
            conn = create_connection("./database/database.sqlite")

            if conn is None:
                print("Error! Cannot connect to the database.")
                return

            recording = get_recording_by_id(conn, recording_id)

            if recording is None:
                print(f"No recording found with ID: {recording_id}")
                return

            if self.mode_switch.value() == 0:  # 0 is for raw transcript
                raw_formatted = recording[7] if recording[7] else recording[5]
                self.transcript_text.deserialize_text_document(raw_formatted)
            else:  # 1 is for processed text
                processed_formatted = recording[8] if recording[8] else recording[6]
                self.transcript_text.deserialize_text_document(processed_formatted)

            conn.close()

    def save_editor_state(self):
        if self.mode_switch.value() == 0:  # Raw transcript mode
            formatted_data = self.transcript_text.serialize_text_document()
            field_to_update = 'raw_transcript_formatted'
        else:  # Processed text mode
            formatted_data = self.transcript_text.serialize_text_document()
            field_to_update = 'processed_text_formatted'

        conn = create_connection("./database/database.sqlite")
        update_recording(conn, self.current_selected_item.get_id(), **{field_to_update: formatted_data})
        conn.close()
        QMessageBox.information(self, "Success", "Transcription saved successfully.")

    def update_ui_state(self):
        # Enable or disable buttons based on the current state
        self.transcript_text._toolbar_actions['start_transcription'].setEnabled(not self.is_transcribing)
        self.transcript_text._toolbar_actions['process_with_gpt4'].setEnabled(
            not self.is_transcribing and not self.is_processing_gpt4 and self.raw_transcript_available()
        )

    def raw_transcript_available(self):
        if self.current_selected_item is not None:
            conn = create_connection("./database/database.sqlite")
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)
            conn.close()
            return bool(recording and recording[5])
        return False

    def on_recording_item_selected(self, recording_item):
        try:
            self.current_selected_item = recording_item
            conn = create_connection("./database/database.sqlite")
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)

            if recording:
                self.id = recording[0]
                self.filename = recording[1]
                self.file_path = recording[2]
                self.date_created = recording[3]
                self.duration = recording[4]

                if self.mode_switch.value() == 0:  # 0 is for raw transcript
                    raw_formatted = recording[7] if recording[7] else recording[5]
                    self.transcript_text.deserialize_text_document(raw_formatted)
                else:  # 1 is for processed text
                    processed_formatted = recording[8] if recording[8] else recording[6]
                    self.transcript_text.deserialize_text_document(processed_formatted)
            else:
                print("No recording found with the provided ID.")
        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    def load_config(self):
        # Load configuration if needed
        pass

    def start_smart_format_processing(self, text_to_format):
        if not text_to_format.strip():
            QMessageBox.warning(self, 'Empty Text', 'There is no text to format.')
            return

        prompt_instructions = """
        Please intelligently format the following text in HTML based on its context. 
        Do not change any of the text - just apply formatting as needed. 
        Do not use a code block when returning the html, just provide the html.
        """

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Store the thread as an instance attribute
        self.smart_format_thread = GPT4ProcessingThread(
            transcript=text_to_format,
            prompt_instructions=prompt_instructions,
            gpt_model='gpt-4o-mini',
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key
        )
        self.smart_format_thread.completed.connect(self.on_smart_format_completed)
        self.smart_format_thread.update_progress.connect(self.update_progress.emit)
        self.smart_format_thread.error.connect(self.on_gpt4_processing_error)
        self.smart_format_thread.start()
        self.is_processing_gpt4 = True
        self.transcript_text.toggle_gpt_spinner()
        self.update_ui_state()

    def on_smart_format_completed(self, formatted_html):
        if formatted_html:
            self.transcript_text.toggle_gpt_spinner()
            self.transcript_text.editor.setHtml(formatted_html)
            recording_id = self.current_selected_item.get_id()
            conn = create_connection("./database/database.sqlite")
            # Store the formatted HTML in 'processed_text_formatted'
            update_recording(conn, recording_id, processed_text_formatted=formatted_html)
            conn.close()
        else:
            QMessageBox.warning(self, 'Formatting Failed', 'Failed to format the text.')
        self.is_processing_gpt4 = False
        self.update_ui_state()