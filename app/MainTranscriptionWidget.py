import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QMessageBox, QComboBox, QHBoxLayout, QLabel,
    QSizePolicy, QTextEdit, QDoubleSpinBox, QSpinBox, QSplitter, QPushButton, QLineEdit, QFileDialog
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal, QSize, Qt
from app.TextEditor import TextEditor
from app.threads.TranscriptionThread import TranscriptionThread
from app.threads.GPT4ProcessingThread import GPT4ProcessingThread
from app.SettingsDialog import SettingsDialog
from app.ToggleSwitch import ToggleSwitch
from app.utils import resource_path
import docx
import htmldocx
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

        # Load configuration
        self.load_config()

        # Top toolbar layout
        self.top_toolbar = QHBoxLayout()
        self.init_top_toolbar()
        self.layout.addLayout(self.top_toolbar)

        # Main content area
        self.init_main_content()

        # Connect signals and slots
        self.transcript_text.transcription_requested.connect(self.start_transcription)
        self.transcript_text.gpt4_processing_requested.connect(self.start_gpt4_processing)
        self.mode_switch.valueChanged.connect(self.on_mode_switch_changed)
        self.settings_button.clicked.connect(self.request_settings)
        self.transcript_text.save_requested.connect(self.save_editor_state)
        self.gpt_prompt_dropdown.currentIndexChanged.connect(self.on_prompt_selection_changed)

        # Connect smart format signal
        self.transcript_text.smart_format_requested.connect(self.start_smart_format_processing)

        self.file_path = None
        self.is_transcribing = False
        self.is_processing_gpt4 = False

    def load_config(self):
        """Load configuration from config.json."""
        config_path = resource_path('config.json')
        try:
            with open(config_path, 'r') as config_file:
                self.config = json.load(config_file)
        except FileNotFoundError:
            QMessageBox.critical(self, "Configuration Error", f"config.json not found at {config_path}.")
            self.config = {
                "transcription_quality": "openai/whisper-base",
                "transcription_language": "English",
                "gpt_model": "gpt-4",
                "max_tokens": 16000,
                "temperature": 1.0,
                "speaker_detection_enabled": False
            }

    def init_top_toolbar(self):
        """Initialize the top toolbar with dropdowns and settings."""
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
        self.settings_button.setIcon(QIcon(resource_path('icons/settings.svg')))
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

    def init_main_content(self):
        """Initialize the main content area with text editor and refinement components."""
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

        # Add refinement input area (initially hidden)
        self.refinement_widget = QWidget()
        self.refinement_layout = QHBoxLayout(self.refinement_widget)
        self.refinement_layout.setContentsMargins(0, 0, 0, 0)

        self.refinement_input = QLineEdit()
        self.refinement_input.setPlaceholderText("Enter refinement instructions...")
        self.refinement_submit_button = QPushButton("Refine")
        self.refinement_submit_button.clicked.connect(self.start_refinement_processing)

        self.refinement_layout.addWidget(self.refinement_input)
        self.refinement_layout.addWidget(self.refinement_submit_button)

        self.content_layout.addWidget(self.refinement_widget)
        self.refinement_widget.setVisible(False)  # Hidden by default

        # Add widgets to splitter
        self.main_splitter.addWidget(self.prompt_widget)
        self.main_splitter.addWidget(self.content_widget)

        # Initially hide the custom prompt input
        self.custom_prompt_input.setVisible(False)
        self.prompt_button_widget.setVisible(False)
        self.prompt_widget.setVisible(False)

    def init_gpt_parameters(self):
        """Initialize GPT-4 parameter controls based on configuration."""
        # Load existing config or defaults
        try:
            config_path = resource_path("config.json")
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
        except FileNotFoundError:
            # Default values if config.json not found
            config = {
                'temperature': 1.0,
                'max_tokens': 16000
            }

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

    def load_prompts(self):
        """Load preset prompts from preset_prompts.json or initialize defaults."""
        prompts_path = resource_path('preset_prompts.json')
        try:
            with open(prompts_path, 'r') as file:
                self.preset_prompts = json.load(file)
        except FileNotFoundError:
            QMessageBox.warning(self, "Prompts File Not Found", "preset_prompts.json not found. Using default prompts.")
            self.preset_prompts = {
                "Youtube to article": "Transform this raw transcript of a youtube video into a well-structured article, maintaining as much detail as possible. Do not embellish by adding details not mentioned. It is extremely important you keep all details. Your output should come close to matching the number of words of the original transcript.",
                "Translate": "Translate this raw audio transcript into English. You may fix minor transcription errors based on context.",
                "Journal Entry Formatting": "Format this raw audio transcript into a clean, coherent journal entry, maintaining a first-person narrative style.",
                "Meeting Minutes": "Convert this transcript into a structured format of meeting minutes, highlighting key points, decisions made, and action items.",
                "Stream of Consciousness": "Organize the ideas in this raw transcript of a stream of consciousness brainstorm in order to capture all key points in a comprehensive and thorough manner.",
            }
            # Optionally, save the default prompts to the file
            with open(prompts_path, 'w') as file:
                json.dump(self.preset_prompts, file, indent=4, sort_keys=True)

        self.gpt_prompt_dropdown.blockSignals(True)
        self.gpt_prompt_dropdown.clear()
        self.gpt_prompt_dropdown.addItems(self.preset_prompts.keys())
        self.gpt_prompt_dropdown.addItem("Custom Prompt")  # Ensure "Custom Prompt" is added here
        self.gpt_prompt_dropdown.blockSignals(False)

    def on_prompt_selection_changed(self, index):
        """Handle changes in prompt selection."""
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
        """Show the custom prompt input area."""
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
        """Hide the custom prompt input area."""
        self.custom_prompt_input.setVisible(False)
        self.custom_prompt_save_button.setVisible(False)
        self.prompt_button_widget.setVisible(False)
        self.prompt_widget.setVisible(False)
        self.main_splitter.setSizes([0, 500])

    def add_formatting_actions(self):
        """Add text formatting actions to the toolbar."""
        # Implementation remains the same as your existing TextEditor.py

        pass  # Placeholder if needed

    def save_custom_prompt_as_template(self):
        """Save the custom prompt as a new template."""
        prompt_name, ok = QInputDialog.getText(self, 'Save Prompt', 'Enter a name for this prompt template:')
        if ok and prompt_name:
            prompt_text = self.custom_prompt_input.toPlainText()
            if prompt_text.strip() == "":
                QMessageBox.warning(self, "Empty Prompt", "Cannot save an empty prompt.")
                return
            self.preset_prompts[prompt_name] = prompt_text
            # Save to 'preset_prompts.json'
            prompts_path = resource_path("preset_prompts.json")
            try:
                with open(prompts_path, 'w') as file:
                    json.dump(self.preset_prompts, file, indent=4, sort_keys=True)
                QMessageBox.information(self, "Prompt Saved", f"Prompt '{prompt_name}' has been saved.")
                # Reload prompts in the dropdown
                self.load_prompts()
                self.gpt_prompt_dropdown.setCurrentText(prompt_name)
                # Hide the custom prompt input area
                self.hide_custom_prompt_input()
                self.is_editing_existing_prompt = False
                self.custom_prompt_save_button.clicked.disconnect()
                self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
            except Exception as e:
                QMessageBox.critical(self, "Error Saving Prompt", f"An error occurred while saving the prompt: {e}")

    def edit_selected_prompt(self):
        """Enable editing of the selected prompt."""
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
                # Disconnect and connect save button to save_edited_prompt
                self.custom_prompt_save_button.clicked.disconnect()
                self.custom_prompt_save_button.clicked.connect(self.save_edited_prompt)
            else:
                QMessageBox.warning(self, "Edit Prompt", "Cannot edit the 'Custom Prompt' option directly.")

    def save_edited_prompt(self):
        """Save the edited prompt."""
        edited_text = self.custom_prompt_input.toPlainText()
        selected_prompt = self.gpt_prompt_dropdown.currentText()
        if not edited_text.strip():
            QMessageBox.warning(self, "Empty Prompt", "Prompt text cannot be empty.")
            return
        self.preset_prompts[selected_prompt] = edited_text
        # Save to 'preset_prompts.json'
        prompts_path = resource_path("preset_prompts.json")
        try:
            with open(prompts_path, 'w') as file:
                json.dump(self.preset_prompts, file, indent=4, sort_keys=True)
            QMessageBox.information(self, "Prompt Updated", f"Prompt '{selected_prompt}' has been updated.")
            # Hide the custom prompt input area
            self.hide_custom_prompt_input()
            self.edit_prompt_button.setText("Edit Prompt")
            self.is_editing_existing_prompt = False
            # Reconnect the save button to default action
            self.custom_prompt_save_button.clicked.disconnect()
            self.custom_prompt_save_button.clicked.connect(self.save_custom_prompt_as_template)
            # Reload prompts
            self.load_prompts()
            self.gpt_prompt_dropdown.setCurrentText(selected_prompt)
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Prompt", f"An error occurred while saving the prompt: {e}")

    def toggle_spinner(self, spinner_name):
        """Toggle spinner visibility if implemented."""
        # Implementation depends on Spinner Widget
        pass  # Placeholder if needed

    def toggle_transcription_spinner(self):
        """Toggle transcription spinner."""
        self.toggle_spinner('transcription_spinner')

    def toggle_gpt_spinner(self):
        """Toggle GPT-4 spinner."""
        self.toggle_spinner('gpt_spinner')

    def font_family_changed(self, font):
        """Handle font family changes."""
        self.transcript_text.editor.setCurrentFont(font)

    def font_size_changed(self, size):
        """Handle font size changes."""
        try:
            size_float = float(size)
            self.transcript_text.editor.setFontPointSize(size_float)
        except ValueError:
            QMessageBox.warning(self, "Invalid Font Size", "Please enter a valid number for font size.")

    def bold_text(self):
        """Toggle bold formatting."""
        weight = QFont.Weight.Bold if not self.transcript_text.editor.fontWeight() == QFont.Weight.Bold else QFont.Weight.Normal
        self.transcript_text.editor.setFontWeight(weight)

    def italic_text(self):
        """Toggle italic formatting."""
        state = not self.transcript_text.editor.fontItalic()
        self.transcript_text.editor.setFontItalic(state)

    def underline_text(self):
        """Toggle underline formatting."""
        state = not self.transcript_text.editor.fontUnderline()
        self.transcript_text.editor.setFontUnderline(state)

    def strikethrough_text(self):
        """Toggle strikethrough formatting."""
        fmt = self.transcript_text.editor.currentCharFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        self.transcript_text.editor.mergeCurrentCharFormat(fmt)

    def highlight_text(self):
        """Highlight selected text."""
        color = QColorDialog.getColor()
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.transcript_text.editor.mergeCurrentCharFormat(fmt)

    def font_color(self):
        """Change font color."""
        color = QColorDialog.getColor()
        if color.isValid():
            self.transcript_text.editor.setTextColor(color)

    def set_alignment(self, alignment):
        """Set text alignment."""
        self.transcript_text.editor.setAlignment(alignment)

    def bullet_list(self):
        """Create a bullet list."""
        cursor = self.transcript_text.editor.textCursor()
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(list_format)

    def numbered_list(self):
        """Create a numbered list."""
        cursor = self.transcript_text.editor.textCursor()
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.Style.ListDecimal)
        cursor.createList(list_format)

    def increase_indent(self):
        """Increase indent."""
        cursor = self.transcript_text.editor.textCursor()
        if cursor.blockFormat().indent() < 15:
            block_format = cursor.blockFormat()
            block_format.setIndent(block_format.indent() + 1)
            cursor.setBlockFormat(block_format)

    def decrease_indent(self):
        """Decrease indent."""
        cursor = self.transcript_text.editor.textCursor()
        if cursor.blockFormat().indent() > 0:
            block_format = cursor.blockFormat()
            block_format.setIndent(block_format.indent() - 1)
            cursor.setBlockFormat(block_format)

    def export_to_pdf(self):
        """Export transcript to PDF."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to PDF", "", "PDF Files (*.pdf)")
        if file_path:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(file_path)
            self.transcript_text.document().print(printer)
            QMessageBox.information(self, "Export to PDF", f"Document successfully exported to {file_path}")

    def export_to_word(self):
        """Export transcript to Word document."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Word", "", "Word Documents (*.docx)")
        if file_path:
            doc = docx.Document()
            html = self.transcript_text.toHtml()
            new_parser = HtmlToDocx()
            new_parser.add_html_to_document(html, doc)
            doc.save(file_path)
            QMessageBox.information(self, "Export to Word", f"Document successfully exported to {file_path}")

    def export_to_text(self):
        """Export transcript to plain text."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Plain Text", "", "Text Files (*.txt)")
        if file_path:
            plain_text = self.transcript_text.toPlainText()
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(plain_text)
            QMessageBox.information(self, "Export to Text", f"Document successfully exported to {file_path}")

    def serialize_text_document(self):
        """Serialize the text document to HTML."""
        try:
            # Access the QTextEdit within the TextEditor component and get the HTML content
            formatted_text = self.transcript_text.editor.toHtml()
            return formatted_text
        except AttributeError as e:
            print(f"Error accessing text editor document: {e}")
            return None

    def deserialize_text_document(self, text_data):
        """Deserialize and load text into the editor."""
        if text_data:
            self.transcript_text.setHtml(text_data.decode('utf-8') if isinstance(text_data, bytes) else text_data)
        else:
            self.transcript_text.clear()

    def save_editor_state(self):
        """Save the current state of the text editor to the database."""
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording to save.')
            return

        # Determine if we're in raw or processed mode
        if self.mode_switch.value() == 0:  # Raw transcript mode
            formatted_data = self.serialize_text_document()
            if formatted_data is None:
                QMessageBox.critical(self, 'Save Error', 'Could not retrieve the text document. Please try again.')
                return
            field_to_update = 'raw_transcript_formatted'
        else:  # Processed text mode
            formatted_data = self.serialize_text_document()
            if formatted_data is None:
                QMessageBox.critical(self, 'Save Error', 'Could not retrieve the text document. Please try again.')
                return
            field_to_update = 'processed_text_formatted'

        print(f"Formatted data to save: {formatted_data[:100]}")

        recording_id = self.current_selected_item.get_id()
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)

        try:
            update_recording(conn, recording_id, **{field_to_update: formatted_data})
            conn.close()
            QMessageBox.information(self, "Success", "Transcription saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"An error occurred while saving: {e}")
            if conn:
                conn.close()
    def process_with_gpt4(self):
        """Emit signal to start GPT-4 processing."""
        self.gpt4_processing_requested.emit()

    def start_transcription(self):
        """Start the transcription process."""
        self.transcript_text.toggle_transcription_spinner()
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording to transcribe.')
            self.transcript_text.toggle_transcription_spinner()
            return

        config_path = resource_path("config.json")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        transcription_method = config.get('transcription_method', 'local')
        transcription_quality = config.get('transcription_quality', 'openai/whisper-base')
        speaker_detection_enabled = config.get('speaker_detection_enabled', False)
        language = config.get('transcription_language', 'English')
        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")  # Ensure correct retrieval

        self.transcription_thread = TranscriptionThread(
            file_path=self.file_path,
            transcription_method=transcription_method,
            openai_api_key=openai_api_key,
            transcription_quality = transcription_quality,
            speaker_detection_enabled = config.get('speaker_detection_enabled', False),
            hf_auth_key = keyring.get_password("transcription_application", "HF_AUTH_TOKEN"),
            language = config.get('transcription_language', 'English')

        )
        self.transcription_thread.completed.connect(self.on_transcription_completed)
        self.transcription_thread.update_progress.connect(self.on_transcription_progress)
        self.transcription_thread.error.connect(self.on_transcription_error)
        self.transcription_thread.start()
        self.is_transcribing = True
        self.update_ui_state()

    def on_transcription_completed(self, transcript):
        """Handle completion of transcription."""
        self.transcript_text.editor.setPlainText(transcript)
        recording_id = self.current_selected_item.get_id()
        self.mode_switch.setValue(0)
        self.transcript_text.editor.setPlainText(transcript)
        # Save the raw transcript to the database
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)
        update_recording(conn, recording_id, raw_transcript=transcript)
        conn.close()

        # Store the raw transcript text for refinement
        self.raw_transcript_text = transcript

        self.is_transcribing = False
        self.transcript_text.toggle_transcription_spinner()
        self.update_ui_state()

    def on_transcription_progress(self, progress_message):
        """Handle transcription progress updates."""
        self.update_progress.emit(progress_message)

    def on_transcription_error(self, error_message):
        """Handle transcription errors."""
        QMessageBox.critical(self, 'Transcription Error', error_message)
        self.is_transcribing = False
        self.transcript_text.toggle_transcription_spinner()
        self.update_ui_state()

    def get_current_prompt_instructions(self):
        """Retrieve the current prompt instructions based on selected prompt."""
        selected_prompt_key = self.gpt_prompt_dropdown.currentText()
        if selected_prompt_key == "Custom Prompt":
            prompt_instructions = self.custom_prompt_input.toPlainText()
        else:
            prompt_instructions = self.preset_prompts.get(selected_prompt_key, '')
        return prompt_instructions

    def start_refinement_processing(self):
        """Start the refinement processing with additional user instructions."""
        refinement_instructions = self.refinement_input.text().strip()
        if not refinement_instructions:
            QMessageBox.warning(self, "Refinement Instructions", "Please enter refinement instructions.")
            return

        # Ensure necessary variables are initialized
        if not hasattr(self, 'original_transcript') or not self.original_transcript:
            # Try to set self.original_transcript from self.raw_transcript_text
            if hasattr(self, 'raw_transcript_text') and self.raw_transcript_text:
                self.original_transcript = self.raw_transcript_text
            else:
                QMessageBox.critical(self, "Error", "Original transcript is not available.")
                return

        if not hasattr(self, 'initial_processed_text') or not self.initial_processed_text:
            QMessageBox.critical(self, "Error", "Processed text is not available.")
            return

        if not hasattr(self, 'initial_prompt_instructions') or not self.initial_prompt_instructions:
            self.initial_prompt_instructions = self.get_current_prompt_instructions()
            if not self.initial_prompt_instructions:
                QMessageBox.critical(self, "Error", "Initial prompt instructions are not available.")
                return

        # Retrieve the processed text from the editor, preserving HTML if present
        current_processed_text = (
            self.transcript_text.editor.toHtml()
            if self.is_text_html(self.initial_processed_text)
            else self.transcript_text.editor.toPlainText()
        )

        # Update initial_processed_text with current content
        self.initial_processed_text = current_processed_text

        # Start the GPT-4 refinement thread
        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Prepare the system prompt
        system_prompt = (
            f"You are an AI assistant that has previously transformed raw transcribed from audio text according to a user's prompt. "
            f"The user now wants to refine the output based on additional instructions. "
            f"The text may have html formatting. If so, you should try to maintain this formatting and return html accordingly."
            f"Original Prompt: {self.initial_prompt_instructions}\n"
            f"Additional Instructions: {refinement_instructions}\n"
            f"Apply these refinements to the previous output, maintaining any necessary formatting. "
            f"Return the refined text only."
            f"Return the refined text only. If you do include html, do not include code blocks, just return the html."
        )

        # Prepare the messages for OpenAI API
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': self.original_transcript},
            {'role': 'assistant', 'content': self.initial_processed_text},
            {'role': 'user', 'content':f"Additional Instructions: {refinement_instructions}"}
        ]

        # Start the GPT-4 processing thread
        self.gpt4_refinement_thread = GPT4ProcessingThread(
            transcript=self.original_transcript,
            prompt_instructions=system_prompt,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key,
            messages=messages  # Pass the conversation messages
        )
        self.gpt4_refinement_thread.completed.connect(self.on_refinement_completed)
        self.gpt4_refinement_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_refinement_thread.start()

        # Disable the refinement input and button until processing is complete
        self.refinement_input.setEnabled(False)
        self.refinement_submit_button.setEnabled(False)

    def on_refinement_completed(self, refined_text):
        """Handle the refined text received from GPT-4."""
        if refined_text:
            # Update the editor with the new refined text
            if self.is_text_html(refined_text):
                self.transcript_text.editor.setHtml(refined_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                formatted_field = 'processed_text'

            # Update the processed text in the database
            if self.current_selected_item:
                recording_id = self.current_selected_item.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                update_recording(conn, recording_id, **{formatted_field: refined_text})
                conn.close()

            # Update the stored processed text for potential further refinements
            self.initial_processed_text = refined_text

            # Optional: Update conversation history if needed
            # self.conversation_history.append({'sender': 'Assistant', 'message': refined_text})

        else:
            QMessageBox.warning(self, "No Refined Text", "GPT-4 did not return any text.")

        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_input.clear()
        self.refinement_submit_button.setEnabled(True)

        self.is_processing_gpt4 = False
        self.update_ui_state()

    def is_text_html(self, text):
        """Check if the given text is HTML formatted."""
        return bool("<" in text and ">" in text)

    def on_gpt4_processing_error(self, error_message):
        """Handle GPT-4 processing errors."""
        QMessageBox.critical(self, "GPT-4 Processing Error", error_message)
        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_submit_button.setEnabled(True)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def toggle_transcription_view(self):
        """Toggle between raw and processed transcript views."""
        if self.current_selected_item is not None:
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)

            if conn is None:
                QMessageBox.critical(self, "Database Error", "Unable to connect to the database.")
                return

            recording = get_recording_by_id(conn, recording_id)

            if recording is None:
                QMessageBox.warning(self, 'Recording Not Found', f'No recording found with ID: {recording_id}')
                return

            if self.mode_switch.value() == 0:  # 0 is for raw transcript
                raw_formatted = recording[7] if recording[7] else recording[5]
                self.transcript_text.deserialize_text_document(raw_formatted)
                self.refinement_widget.setVisible(False)
            else:  # 1 is for processed text
                processed_formatted = recording[8] if recording[8] else recording[6]
                if processed_formatted:
                    self.transcript_text.deserialize_text_document(processed_formatted)
                    if self.has_processed_text():
                        self.refinement_widget.setVisible(True)
                    else:
                        self.refinement_widget.setVisible(False)
                else:
                    self.transcript_text.editor.clear()
                    self.refinement_widget.setVisible(False)

            conn.close()

    def has_processed_text(self):
        """Check if there's processed text available."""
        if self.current_selected_item is not None:
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)
            conn.close()
            return bool(recording and (recording[6] or recording[8]))  # processed_text or processed_text_formatted
        return False

    def request_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.load_config)
        dialog.prompts_updated.connect(self.load_prompts)
        dialog.exec()

    def start_gpt4_processing(self):
        """Start the initial GPT-4 processing of the transcript."""
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording first.')
            return

        recording_id = self.current_selected_item.get_id()
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)

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
        config_path = resource_path("config.json")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Start the GPT-4 processing thread
        self.gpt4_processing_thread = GPT4ProcessingThread(
            transcript=raw_transcript,
            prompt_instructions=prompt_instructions,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
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
        """Handle completion of GPT-4 processing."""
        if self.current_selected_item:
            # Update the editor with the new processed text
            self.mode_switch.setValue(1)
            if self.is_text_html(processed_text):
                self.transcript_text.editor.setHtml(processed_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(processed_text)
                formatted_field = 'processed_text'
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            update_recording(conn, recording_id, **{formatted_field: processed_text})
            conn.close()
            self.is_processing_gpt4 = False
            self.transcript_text.toggle_gpt_spinner()
            self.update_ui_state()

            # Store necessary data for refinement
            self.initial_processed_text = processed_text
            self.original_transcript = self.raw_transcript_text
            self.initial_prompt_instructions = self.get_current_prompt_instructions()

            # Show the refinement input area
            if self.has_processed_text():
                self.refinement_widget.setVisible(True)

    def on_gpt4_processing_progress(self, progress_message):
        """Handle GPT-4 processing progress updates."""
        self.update_progress.emit(progress_message)

    def on_gpt4_processing_error(self, error_message):
        """Handle GPT-4 processing errors."""
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        # Re-enable the processing flag and update UI
        self.is_processing_gpt4 = False
        self.transcript_text.toggle_gpt_spinner()
        self.update_ui_state()

    def start_smart_format_processing(self, text_to_format):
        """Start smart formatting of the transcript."""
        if not text_to_format.strip():
            QMessageBox.warning(self, 'Empty Text', 'There is no text to format.')
            return

        prompt_instructions = """
        Please intelligently format the following text in HTML based on its context.
        Do not change any of the text - just apply formatting as needed.
        Do not use a code block when returning the html, just provide the html.
        """
        config_path = resource_path("config.json")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Start the GPT-4 processing thread
        self.gpt4_smart_format_thread = GPT4ProcessingThread(
            transcript=text_to_format,
            prompt_instructions=prompt_instructions,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key
        )
        self.gpt4_smart_format_thread.completed.connect(self.on_smart_format_completed)
        self.gpt4_smart_format_thread.update_progress.connect(self.update_progress.emit)
        self.gpt4_smart_format_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_smart_format_thread.start()
        self.is_processing_gpt4 = True
        self.transcript_text.toggle_gpt_spinner()
        self.update_ui_state()

    def on_smart_format_completed(self, formatted_html):
        """Handle completion of smart formatting."""
        if formatted_html:
            self.transcript_text.editor.setHtml(formatted_html)
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            update_recording(conn, recording_id, processed_text_formatted=formatted_html)
            conn.close()
            self.is_processing_gpt4 = False
            self.transcript_text.toggle_gpt_spinner()
            self.update_ui_state()
        else:
            QMessageBox.warning(self, 'Formatting Failed', 'Failed to format the text.')
        # Re-enable the smart format controls if any

    def start_refinement_processing(self):
        """Start the refinement processing with additional user instructions."""
        refinement_instructions = self.refinement_input.text().strip()
        if not refinement_instructions:
            QMessageBox.warning(self, "Refinement Instructions", "Please enter refinement instructions.")
            return

        # Ensure necessary variables are initialized
        if not hasattr(self, 'original_transcript') or not self.original_transcript:
            # Try to set self.original_transcript from self.raw_transcript_text
            if hasattr(self, 'raw_transcript_text') and self.raw_transcript_text:
                self.original_transcript = self.raw_transcript_text
            else:
                QMessageBox.critical(self, "Error", "Original transcript is not available.")
                return

        if not hasattr(self, 'initial_processed_text') or not self.initial_processed_text:
            QMessageBox.critical(self, "Error", "Processed text is not available.")
            return

        if not hasattr(self, 'initial_prompt_instructions') or not self.initial_prompt_instructions:
            self.initial_prompt_instructions = self.get_current_prompt_instructions()
            if not self.initial_prompt_instructions:
                QMessageBox.critical(self, "Error", "Initial prompt instructions are not available.")
                return

        # Retrieve the processed text from the editor, preserving HTML if present
        current_processed_text = (
            self.transcript_text.editor.toHtml()
            if self.is_text_html(self.initial_processed_text)
            else self.transcript_text.editor.toPlainText()
        )

        # Update initial_processed_text with current content
        self.initial_processed_text = current_processed_text

        # Start the GPT-4 refinement thread
        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Prepare the system prompt
        system_prompt = (
            f"You are an AI assistant that has previously transformed text according to a user's prompt. "
            f"The user now wants to refine the output based on additional instructions. "
            f"Original Prompt: {self.initial_prompt_instructions}\n"
            f"Additional Instructions: {refinement_instructions}\n"
            f"Apply these refinements to the previous output, maintaining any necessary formatting. "
            f"Return the refined text only."
        )

        # Prepare the messages for OpenAI API
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': self.original_transcript},
            {'role': 'assistant', 'content': self.initial_processed_text}
        ]

        # Start the GPT-4 processing thread
        self.gpt4_refinement_thread = GPT4ProcessingThread(
            transcript=self.original_transcript,
            prompt_instructions=system_prompt,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key,
            messages=messages  # Pass the conversation messages
        )
        self.gpt4_refinement_thread.completed.connect(self.on_refinement_completed)
        self.gpt4_refinement_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_refinement_thread.start()

        # Disable the refinement input and button until processing is complete
        self.refinement_input.setEnabled(False)
        self.refinement_submit_button.setEnabled(False)

    def on_refinement_completed(self, refined_text):
        """Handle the refined text received from GPT-4."""
        if refined_text:
            # Update the editor with the new refined text
            if self.is_text_html(refined_text):
                self.transcript_text.editor.setHtml(refined_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                formatted_field = 'processed_text'

            # Update the processed text in the database
            if self.current_selected_item:
                recording_id = self.current_selected_item.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                update_recording(conn, recording_id, **{formatted_field: refined_text})
                conn.close()

            # Update the stored processed text for potential further refinements
            self.initial_processed_text = refined_text

        else:
            QMessageBox.warning(self, "No Refined Text", "GPT-4 did not return any text.")

        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_input.clear()
        self.refinement_submit_button.setEnabled(True)

        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_gpt4_processing_error(self, error_message):
        """Handle GPT-4 processing errors."""
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_submit_button.setEnabled(True)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_mode_switch_changed(self):
        """Handle changes in the mode switch to show/hide refinement controls."""
        # Show or hide the refinement widget based on the mode and content
        if self.mode_switch.value() == 1 and self.has_processed_text() and not self.is_processing_gpt4:
            self.refinement_widget.setVisible(True)
        else:
            self.refinement_widget.setVisible(False)
        self.toggle_transcription_view()

    def has_processed_text(self):
        """Check if there's processed text available."""
        if self.current_selected_item is not None:
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)
            conn.close()
            return bool(recording and (recording[6] or recording[8]))  # processed_text or processed_text_formatted
        return False

    def request_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.load_config)
        dialog.prompts_updated.connect(self.load_prompts)
        dialog.exec()

    def start_gpt4_processing(self):
        """Start the initial GPT-4 processing of the transcript."""
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording first.')
            return

        recording_id = self.current_selected_item.get_id()
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)

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
        config_path = resource_path("config.json")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Start the GPT-4 processing thread
        self.gpt4_processing_thread = GPT4ProcessingThread(
            transcript=raw_transcript,
            prompt_instructions=prompt_instructions,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
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
        """Handle completion of GPT-4 processing."""
        if self.current_selected_item:
            # Update the editor with the new processed text
            self.mode_switch.setValue(1)
            if self.is_text_html(processed_text):
                self.transcript_text.editor.setHtml(processed_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(processed_text)
                formatted_field = 'processed_text'
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            update_recording(conn, recording_id, **{formatted_field: processed_text})
            conn.close()
            self.is_processing_gpt4 = False
            self.transcript_text.toggle_gpt_spinner()
            self.update_ui_state()

            # Store necessary data for refinement
            self.initial_processed_text = processed_text
            self.original_transcript = self.raw_transcript_text
            self.initial_prompt_instructions = self.get_current_prompt_instructions()

            # Show the refinement input area if processed text exists
            if self.has_processed_text():
                self.refinement_widget.setVisible(True)

    def on_gpt4_processing_progress(self, progress_message):
        """Handle GPT-4 processing progress updates."""
        self.update_progress.emit(progress_message)

    def on_gpt4_processing_error(self, error_message):
        """Handle GPT-4 processing errors."""
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        # Re-enable the processing flag and update UI
        self.is_processing_gpt4 = False
        self.transcript_text.toggle_gpt_spinner()
        self.update_ui_state()

    def has_processed_text(self):
        """Check if there's processed text available."""
        if self.current_selected_item is not None:
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)
            conn.close()
            return bool(recording and (recording[6] or recording[8]))  # processed_text or processed_text_formatted
        return False

    def start_smart_format_processing(self, text_to_format):
        """Start smart formatting of the transcript."""
        if not text_to_format.strip():
            QMessageBox.warning(self, 'Empty Text', 'There is no text to format.')
            return

        prompt_instructions = """
        Please intelligently format the following text in HTML based on its context.
        Do not change any of the text - just apply formatting as needed.
        Do not use a code block when returning the html, just provide the html.
        """
        config_path = resource_path("config.json")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Start the GPT-4 processing thread
        self.gpt4_smart_format_thread = GPT4ProcessingThread(
            transcript=text_to_format,
            prompt_instructions=prompt_instructions,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key
        )
        self.gpt4_smart_format_thread.completed.connect(self.on_smart_format_completed)
        self.gpt4_smart_format_thread.update_progress.connect(self.update_progress.emit)
        self.gpt4_smart_format_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_smart_format_thread.start()
        self.is_processing_gpt4 = True
        self.transcript_text.toggle_gpt_spinner()
        self.update_ui_state()

    def on_smart_format_completed(self, formatted_html):
        """Handle completion of smart formatting."""
        if formatted_html:
            self.transcript_text.editor.setHtml(formatted_html)
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            update_recording(conn, recording_id, processed_text_formatted=formatted_html)
            conn.close()
            self.is_processing_gpt4 = False
            self.transcript_text.toggle_gpt_spinner()
            self.update_ui_state()
        else:
            QMessageBox.warning(self, 'Formatting Failed', 'Failed to format the text.')
        # Re-enable the smart format controls if any

    def on_recording_item_selected(self, recording_item):
        """Handle the event when a recording item is selected."""
        try:
            self.current_selected_item = recording_item
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)

            if recording:
                self.id = recording[0]
                self.filename = recording[1]
                self.file_path = recording[2]
                self.date_created = recording[3]
                self.duration = recording[4]
                self.raw_transcript_text = recording[5]  # Store raw transcript text

                # Load processed text
                processed_text = recording[6]
                processed_text_formatted = recording[8]

                # Set initial_processed_text based on availability
                if processed_text_formatted:
                    # If there is formatted processed text, use that
                    self.initial_processed_text = processed_text_formatted
                elif processed_text:
                    self.initial_processed_text = processed_text
                else:
                    self.initial_processed_text = None

                # Similarly, handle the raw transcript formatted text
                raw_formatted = recording[7] if recording[7] else recording[5]
                processed_formatted = recording[8] if recording[8] else recording[6]

                if self.mode_switch.value() == 0:  # 0 is for raw transcript
                    self.transcript_text.deserialize_text_document(raw_formatted)
                    self.refinement_widget.setVisible(False)
                else:  # 1 is for processed text
                    if processed_formatted:
                        self.transcript_text.deserialize_text_document(processed_formatted)
                        if self.has_processed_text():
                            self.refinement_widget.setVisible(True)
                        else:
                            self.refinement_widget.setVisible(False)
                    else:
                        self.transcript_text.editor.clear()
                        self.refinement_widget.setVisible(False)

                # Store the prompt instructions
                self.initial_prompt_instructions = self.get_current_prompt_instructions()

            else:
                QMessageBox.warning(self, 'Recording Not Found', "No recording found with the provided ID.")
        except Exception as e:
            QMessageBox.critical(self, 'Error', f"An error occurred: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    def update_ui_state(self):
        """Update the UI state based on current processing flags."""
        # Enable or disable buttons based on the current state
        self.transcript_text._toolbar_actions['start_transcription'].setEnabled(not self.is_transcribing)
        self.transcript_text._toolbar_actions['process_with_gpt4'].setEnabled(
            not self.is_transcribing and not self.is_processing_gpt4 and self.raw_transcript_available()
        )

        # Update Refinement widget visibility
        if self.mode_switch.value() == 1 and self.has_processed_text() and not self.is_processing_gpt4:
            self.refinement_widget.setVisible(True)
        else:
            self.refinement_widget.setVisible(False)

    def raw_transcript_available(self):
        """Check if raw transcript is available."""
        if self.current_selected_item is not None:
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)
            conn.close()
            return bool(recording and recording[5])
        return False

    def on_refinement_completed(self, refined_text):
        """Handle the refined text received from GPT-4."""
        if refined_text:
            # Update the editor with the new refined text
            if self.is_text_html(refined_text):
                self.transcript_text.editor.setHtml(refined_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                formatted_field = 'processed_text'

            # Update the processed text in the database
            if self.current_selected_item:
                recording_id = self.current_selected_item.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                update_recording(conn, recording_id, **{formatted_field: refined_text})
                conn.close()

            # Update the stored processed text for potential further refinements
            self.initial_processed_text = refined_text

        else:
            QMessageBox.warning(self, 'No Refined Text', 'GPT-4 did not return any text.')

        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_input.clear()
        self.refinement_submit_button.setEnabled(True)

        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_gpt4_processing_error(self, error_message):
        """Handle GPT-4 processing errors."""
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_submit_button.setEnabled(True)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_refinement_submit(self):
        """Handle the refinement submission."""
        # This method is already handled by start_refinement_processing
        pass

    def is_text_html(self, text):
        """Check if the given text is HTML formatted."""
        return bool("<" in text and ">" in text)

    def get_current_prompt_instructions(self):
        """Retrieve the current prompt instructions based on selected prompt."""
        selected_prompt_key = self.gpt_prompt_dropdown.currentText()
        if selected_prompt_key == "Custom Prompt":
            prompt_instructions = self.custom_prompt_input.toPlainText()
        else:
            prompt_instructions = self.preset_prompts.get(selected_prompt_key, '')
        return prompt_instructions

    def start_refinement_processing(self):
        """Start the refinement processing with additional user instructions."""
        refinement_instructions = self.refinement_input.text().strip()
        if not refinement_instructions:
            QMessageBox.warning(self, "Refinement Instructions", "Please enter refinement instructions.")
            return

        # Ensure necessary variables are initialized
        if not hasattr(self, 'original_transcript') or not self.original_transcript:
            # Try to set self.original_transcript from self.raw_transcript_text
            if hasattr(self, 'raw_transcript_text') and self.raw_transcript_text:
                self.original_transcript = self.raw_transcript_text
            else:
                QMessageBox.critical(self, "Error", "Original transcript is not available.")
                return

        if not hasattr(self, 'initial_processed_text') or not self.initial_processed_text:
            QMessageBox.critical(self, "Error", "Processed text is not available.")
            return

        if not hasattr(self, 'initial_prompt_instructions') or not self.initial_prompt_instructions:
            self.initial_prompt_instructions = self.get_current_prompt_instructions()
            if not self.initial_prompt_instructions:
                QMessageBox.critical(self, "Error", "Initial prompt instructions are not available.")
                return

        # Retrieve the processed text from the editor, preserving HTML if present
        current_processed_text = (
            self.transcript_text.editor.toHtml()
            if self.is_text_html(self.initial_processed_text)
            else self.transcript_text.editor.toPlainText()
        )

        # Update initial_processed_text with current content
        self.initial_processed_text = current_processed_text

        # Start the GPT-4 refinement thread
        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Prepare the system prompt
        system_prompt = (
            f"You are an AI assistant that has previously transformed text according to a user's prompt. "
            f"The user now wants to refine the output based on additional instructions. "
            f"Original Prompt: {self.initial_prompt_instructions}\n"
            f"Additional Instructions: {refinement_instructions}\n"
            f"Apply these refinements to the previous output, maintaining any necessary formatting. "
            f"Return the refined text only."
        )

        # Prepare the messages for OpenAI API
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': self.original_transcript},
            {'role': 'assistant', 'content': self.initial_processed_text}
        ]

        # Start the GPT-4 processing thread
        self.gpt4_refinement_thread = GPT4ProcessingThread(
            transcript=self.original_transcript,
            prompt_instructions=system_prompt,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
            max_tokens=max_tokens,
            temperature=temperature,
            openai_api_key=openai_api_key,
            messages=messages  # Pass the conversation messages
        )
        self.gpt4_refinement_thread.completed.connect(self.on_refinement_completed)
        self.gpt4_refinement_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_refinement_thread.start()

        # Disable the refinement input and button until processing is complete
        self.refinement_input.setEnabled(False)
        self.refinement_submit_button.setEnabled(False)

    def on_refinement_completed(self, refined_text):
        """Handle the refined text received from GPT-4."""
        if refined_text:
            # Update the editor with the new refined text
            if self.is_text_html(refined_text):
                self.transcript_text.editor.setHtml(refined_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                formatted_field = 'processed_text'

            # Update the processed text in the database
            if self.current_selected_item:
                recording_id = self.current_selected_item.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                update_recording(conn, recording_id, **{formatted_field: refined_text})
                conn.close()

            # Update the stored processed text for potential further refinements
            self.initial_processed_text = refined_text

        else:
            QMessageBox.warning(self, 'No Refined Text', 'GPT-4 did not return any text.')

        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_input.clear()
        self.refinement_submit_button.setEnabled(True)

        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_gpt4_processing_error(self, error_message):
        """Handle GPT-4 processing errors."""
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_submit_button.setEnabled(True)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_mode_switch_changed(self):
        """Handle changes in the mode switch to show/hide refinement controls."""
        # Show or hide the refinement widget based on the mode and content
        if self.mode_switch.value() == 1 and self.has_processed_text() and not self.is_processing_gpt4:
            self.refinement_widget.setVisible(True)
        else:
            self.refinement_widget.setVisible(False)
        self.toggle_transcription_view()

    def has_processed_text(self):
        """Check if there's processed text available."""
        if self.current_selected_item is not None:
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)
            conn.close()
            return bool(recording and (recording[6] or recording[8]))  # processed_text or processed_text_formatted
        return False

    def toggle_transcription_view(self):
        """Toggle between raw and processed transcript views."""
        if self.current_selected_item is not None:
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)

            if conn is None:
                QMessageBox.critical(self, "Database Error", "Unable to connect to the database.")
                return

            recording = get_recording_by_id(conn, recording_id)

            if recording is None:
                QMessageBox.warning(self, 'Recording Not Found', f'No recording found with ID: {recording_id}')
                conn.close()
                return

            if self.mode_switch.value() == 0:  # 0 is for raw transcript
                raw_formatted = recording[7] if recording[7] else recording[5]
                self.transcript_text.deserialize_text_document(raw_formatted)
                self.refinement_widget.setVisible(False)
            else:  # 1 is for processed text
                processed_formatted = recording[8] if recording[8] else recording[6]
                if processed_formatted:
                    self.transcript_text.deserialize_text_document(processed_formatted)
                    if self.has_processed_text():
                        self.refinement_widget.setVisible(True)
                    else:
                        self.refinement_widget.setVisible(False)
                else:
                    self.transcript_text.editor.clear()
                    self.refinement_widget.setVisible(False)

            conn.close()

    def request_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.load_config)
        dialog.prompts_updated.connect(self.load_prompts)
        dialog.exec()

    def start_gpt4_processing(self):
        """Start the initial GPT-4 processing of the transcript."""
        if self.current_selected_item is None:
            QMessageBox.warning(self, 'No Recording Selected', 'Please select a recording first.')
            return

        recording_id = self.current_selected_item.get_id()
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)

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
        config_path = resource_path("config.json")
        with open(config_path, 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")
        if not openai_api_key:
            QMessageBox.critical(self, "API Key Missing", "Please set your OpenAI API key in the settings.")
            return

        temperature = self.temperature_spinbox.value()
        max_tokens = self.max_tokens_spinbox.value()

        # Start the GPT-4 processing thread
        self.gpt4_processing_thread = GPT4ProcessingThread(
            transcript=raw_transcript,
            prompt_instructions=prompt_instructions,
            gpt_model=self.config.get('gpt_model', 'gpt-4'),
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

    def on_transcription_completed(self, transcript):
        """Handle completion of transcription."""
        self.transcript_text.editor.setPlainText(transcript)
        recording_id = self.current_selected_item.get_id()
        self.mode_switch.setValue(0)
        self.transcript_text.editor.setPlainText(transcript)
        # Save the raw transcript to the database
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)
        update_recording(conn, recording_id, raw_transcript=transcript)
        conn.close()

        # Store the raw transcript text for refinement
        self.raw_transcript_text = transcript

        self.is_transcribing = False
        self.transcript_text.toggle_transcription_spinner()
        self.update_ui_state()

    def on_refinement_completed(self, refined_text):
        """Handle the refined text received from GPT-4."""
        if refined_text:
            # Update the editor with the new refined text
            if self.is_text_html(refined_text):
                self.transcript_text.editor.setHtml(refined_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(refined_text)
                formatted_field = 'processed_text'

            # Update the processed text in the database
            if self.current_selected_item:
                recording_id = self.current_selected_item.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                update_recording(conn, recording_id, **{formatted_field: refined_text})
                conn.close()

            # Update the stored processed text for potential further refinements
            self.initial_processed_text = refined_text

        else:
            QMessageBox.warning(self, 'No Refined Text', 'GPT-4 did not return any text.')

        # Re-enable the refinement input fields
        self.refinement_input.setEnabled(True)
        self.refinement_input.clear()
        self.refinement_submit_button.setEnabled(True)

        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_gpt4_processing_completed(self, processed_text):
        """Handle completion of GPT-4 processing."""
        if self.current_selected_item:
            # Update the editor with the new processed text
            self.mode_switch.setValue(1)
            if self.is_text_html(processed_text):
                self.transcript_text.editor.setHtml(processed_text)
                formatted_field = 'processed_text_formatted'
            else:
                self.transcript_text.editor.setPlainText(processed_text)
                formatted_field = 'processed_text'
            recording_id = self.current_selected_item.get_id()
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            update_recording(conn, recording_id, **{formatted_field: processed_text})
            conn.close()
            self.is_processing_gpt4 = False
            self.transcript_text.toggle_gpt_spinner()
            self.update_ui_state()

            # Store necessary data for refinement
            self.initial_processed_text = processed_text
            self.original_transcript = self.raw_transcript_text
            self.initial_prompt_instructions = self.get_current_prompt_instructions()

            # Show the refinement input area if processed text exists
            if self.has_processed_text():
                self.refinement_widget.setVisible(True)

    def on_gpt4_processing_progress(self, progress_message):
        """Handle GPT-4 processing progress updates."""
        self.update_progress.emit(progress_message)

    def process_with_gpt4(self):
        """Emit signal to start GPT-4 processing."""
        self.start_gpt4_processing()

    def toggle_transcription_spinner(self):
        """Toggle transcription spinner (implementation depends on UI)."""
        self.toggle_spinner('transcription_spinner')

    def toggle_gpt_spinner(self):
        """Toggle GPT-4 spinner (implementation depends on UI)."""
        self.toggle_spinner('gpt_spinner')

    def toggle_spinner(self, spinner_name):
        """Toggle spinner visibility if implemented."""
        # Placeholder for spinner functionality
        pass