from PyQt6.QtWidgets import (
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QDialog,
    QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox
)
from PyQt6.QtCore import pyqtSignal
import keyring
import json
from app.utils import resource_path
from app.PromptManagerDialog import PromptManagerDialog


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()
    prompts_updated = pyqtSignal()

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.main_window = main_window
        layout = QVBoxLayout(self)

        # Define the service identifier for keyring
        self.service_id = "transcription_application"

        # Create labels and line edits for the API keys
        self.hf_api_key_label = QLabel('HuggingFace Access Token:', self)
        self.hf_api_key_edit = QLineEdit(self)
        self.openai_api_key_label = QLabel('OpenAI API Key:', self)
        self.openai_api_key_edit = QLineEdit(self)

        # Load existing API keys
        existing_hf_key = keyring.get_password(self.service_id, "HF_AUTH_TOKEN")
        existing_openai_key = keyring.get_password(self.service_id, "OPENAI_API_KEY")
        self.hf_api_key_edit.setText(existing_hf_key or '')
        self.openai_api_key_edit.setText(existing_openai_key or '')

        # Transcription Quality
        self.transcription_quality_label = QLabel('Transcription Quality: (Larger = higher quality, but slower & uses more VRAM)', self)
        self.transcription_quality_dropdown = QComboBox(self)
        self.transcription_quality_dropdown.addItems(['distil-whisper/distil-small.en',
                                                     'distil-whisper/distil-medium.en',
                                                     'distil-whisper/distil-large-v2',
                                                     'distil-whisper/distil-large-v3',
                                                     'openai/whisper-tiny',
                                                     'openai/whisper-base',
                                                     'openai/whisper-small',
                                                     'openai/whisper-medium',
                                                     'openai/whisper-large-v2',
                                                     'openai/whisper-large-v3'])

        # GPT Model Selection
        self.gpt_model_label = QLabel('GPT Model: (GPT-4o strongly recommended.)', self)
        self.gpt_model_dropdown = QComboBox(self)
        self.gpt_model_dropdown.addItems(['gpt-4-turbo','gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo', 'gpt-4','o1-preview'])

        # Max Tokens
        self.max_tokens_label = QLabel('Max Tokens (0-16000):', self)
        self.max_tokens_spinbox = QSpinBox(self)
        self.max_tokens_spinbox.setRange(0, 16000)
        self.max_tokens_spinbox.setValue(16000)  # Default value or load from config

        # Temperature
        self.temperature_label = QLabel('Temperature (0.0-2.0):', self)
        self.temperature_spinbox = QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setValue(0.7)  # Default value or load from config

        # Translation Language Selection
        self.language_label = QLabel('Transcription Language:', self)
        self.language_dropdown = QComboBox(self)
        self.language_dropdown.addItems([
            'English', 'Spanish', 'French', 'German', 'Chinese', 'Japanese',
            'Korean', 'Italian', 'Portuguese', 'Russian', 'Arabic', 'Hindi',
            'Dutch', 'Swedish', 'Turkish', 'Czech', 'Danish', 'Finnish'
            # Add more languages as needed
        ])

        # Speaker detection/diarization
        self.speaker_detection_checkbox = QCheckBox('Enable Speaker Detection (Requires HF Auth Token)')
        self.toggle_speaker_detection_checkbox()

        # Prompt manager
        self.manage_prompts_button = QPushButton('Manage Prompts')
        self.manage_prompts_button.clicked.connect(self.open_prompt_manager)

        # Add the widgets to the layout
        layout.addWidget(self.gpt_model_label)
        layout.addWidget(self.gpt_model_dropdown)
        layout.addWidget(self.max_tokens_label)
        layout.addWidget(self.max_tokens_spinbox)
        layout.addWidget(self.temperature_label)
        layout.addWidget(self.temperature_spinbox)
        layout.addWidget(self.language_label)  # Add language label
        layout.addWidget(self.language_dropdown)  # Add language dropdown
        layout.addWidget(self.speaker_detection_checkbox)
        layout.addWidget(self.hf_api_key_label)
        layout.addWidget(self.hf_api_key_edit)
        layout.addWidget(self.openai_api_key_label)
        layout.addWidget(self.openai_api_key_edit)
        layout.addWidget(self.transcription_quality_label)
        layout.addWidget(self.transcription_quality_dropdown)
        layout.addWidget(self.manage_prompts_button)

        # Load the config file
        self.load_config()
        self.toggle_speaker_detection_checkbox()
        self.hf_api_key_edit.textChanged.connect(self.toggle_speaker_detection_checkbox)

        # Add standard dialog button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        layout.addWidget(button_box)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

    def accept(self):
        hf_api_key = self.hf_api_key_edit.text()
        openai_api_key = self.openai_api_key_edit.text()
        transcription_quality = self.transcription_quality_dropdown.currentText()
        transcription_language = self.language_dropdown.currentText()  # Get selected language

        # Save the API keys
        keyring.set_password(self.service_id, "HF_AUTH_TOKEN", hf_api_key)
        keyring.set_password(self.service_id, "OPENAI_API_KEY", openai_api_key)

        # Save the transcription quality and language
        config = {
            'transcription_quality': transcription_quality,
            'transcription_language': transcription_language,  # Save language
            'gpt_model': self.gpt_model_dropdown.currentText(),
            'max_tokens': self.max_tokens_spinbox.value(),
            'temperature': self.temperature_spinbox.value(),
            'speaker_detection_enabled': self.speaker_detection_checkbox.isChecked(),
        }
        config_path = resource_path('config.json')
        with open(config_path, 'w') as config_file:
            json.dump(config, config_file, indent=4)
        self.settings_changed.emit()
        super().accept()

    def load_config(self):
        try:
            config_path = resource_path('config.json')
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
                self.transcription_quality_dropdown.setCurrentText(config.get('transcription_quality', 'distil-whisper/distil-small.en'))
                self.gpt_model_dropdown.setCurrentText(config.get('gpt_model', 'gpt-4o'))
                self.max_tokens_spinbox.setValue(config.get('max_tokens', 16000))
                self.temperature_spinbox.setValue(config.get('temperature', 0.7))
                self.language_dropdown.setCurrentText(config.get('transcription_language', 'English'))  # Load language
                self.speaker_detection_checkbox.setChecked(config.get('speaker_detection_enabled', True))
        except FileNotFoundError:
            # Set default values if config file doesn't exist
            self.transcription_quality_dropdown.setCurrentText('distil-whisper/distil-small.en')
            self.gpt_model_dropdown.setCurrentText('gpt-4o')
            self.max_tokens_spinbox.setValue(16000)
            self.temperature_spinbox.setValue(0.7)
            self.language_dropdown.setCurrentText('English')  # Default language
            self.speaker_detection_checkbox.setChecked(True)

    def save_config(self):
        config = {
            'transcription_quality': self.transcription_quality_dropdown.currentText(),
            'gpt_model': self.gpt_model_dropdown.currentText(),
            'max_tokens': self.max_tokens_spinbox.value(),
            'temperature': self.temperature_spinbox.value(),
            'speaker_detection_enabled': self.speaker_detection_checkbox.isChecked(),
            'transcription_language': self.language_dropdown.currentText()  # Ensure language is saved
        }
        config_path = resource_path('config.json')
        with open(config_path, 'w') as config_file:
            json.dump(config, config_file, indent=4)
        self.settings_changed.emit()

    def open_prompt_manager(self):
        dialog = PromptManagerDialog(self.main_window.preset_prompts, self)
        dialog.prompts_saved.connect(self.prompts_saved_handler)
        dialog.exec()

    def prompts_saved_handler(self):
        self.prompts_updated.emit()  # When PromptManagerDialog saves prompts, emit the signal

    def toggle_speaker_detection_checkbox(self):
        # Enable the speaker detection checkbox only if the Hugging Face API key is provided
        if self.hf_api_key_edit.text().strip():
            self.speaker_detection_checkbox.setEnabled(True)
        else:
            self.speaker_detection_checkbox.setChecked(False)  # Uncheck if API key is removed
            self.speaker_detection_checkbox.setEnabled(False)