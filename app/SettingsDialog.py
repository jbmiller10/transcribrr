from PyQt6.QtWidgets import (
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QDialog,
    QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QHBoxLayout, QGroupBox,
    QTabWidget, QWidget, QToolTip, QMessageBox, QScrollArea
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon
import keyring
import json
import os
import logging
from app.utils import resource_path
from app.PromptManagerDialog import PromptManagerDialog

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()
    prompts_updated = pyqtSignal()

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setMinimumWidth(600)  # Ensure dialog is wide enough
        self.main_window = main_window

        # Define the service identifier for keyring
        self.service_id = "transcription_application"

        # Set up the main layout
        self.main_layout = QVBoxLayout(self)

        # Create tabs for better organization
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_api_tab()
        self.create_transcription_tab()
        self.create_gpt_tab()

        # Add standard dialog button box
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Reset,
            self
        )
        self.main_layout.addWidget(self.button_box)

        self.button_box.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self.accept)
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self.reset_to_defaults)

        # Load settings
        self.load_config()

        # Toggle speaker detection based on API key
        self.toggle_speaker_detection_checkbox()
        self.hf_api_key_edit.textChanged.connect(self.toggle_speaker_detection_checkbox)

    def create_api_tab(self):
        """Create the API Keys tab."""
        api_tab = QWidget()
        api_layout = QVBoxLayout(api_tab)

        # API Keys Group
        api_group = QGroupBox("API Keys")
        api_group_layout = QVBoxLayout(api_group)

        # OpenAI API Key
        openai_layout = QVBoxLayout()
        self.openai_api_key_label = QLabel('OpenAI API Key:', self)
        self.openai_api_key_label.setToolTip("Required for GPT processing and OpenAI Whisper API transcription")
        self.openai_api_key_edit = QLineEdit(self)
        self.openai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)  # Mask the API key
        openai_info = QLabel("Required for GPT processing and OpenAI Whisper API transcription")
        openai_info.setStyleSheet("color: gray; font-size: 10pt;")
        openai_layout.addWidget(self.openai_api_key_label)
        openai_layout.addWidget(self.openai_api_key_edit)
        openai_layout.addWidget(openai_info)
        api_group_layout.addLayout(openai_layout)

        api_group_layout.addSpacing(10)

        # HuggingFace API Key
        hf_layout = QVBoxLayout()
        self.hf_api_key_label = QLabel('HuggingFace Access Token:', self)
        self.hf_api_key_label.setToolTip("Required for speaker detection (diarization)")
        self.hf_api_key_edit = QLineEdit(self)
        self.hf_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)  # Mask the API key
        hf_info = QLabel("Required for speaker detection (diarization)")
        hf_info.setStyleSheet("color: gray; font-size: 10pt;")
        hf_layout.addWidget(self.hf_api_key_label)
        hf_layout.addWidget(self.hf_api_key_edit)
        hf_layout.addWidget(hf_info)
        api_group_layout.addLayout(hf_layout)

        api_layout.addWidget(api_group)
        api_layout.addStretch()

        self.tab_widget.addTab(api_tab, "API Keys")

    def create_transcription_tab(self):
        """Create the Transcription Settings tab."""
        transcription_tab = QWidget()

        # Use ScrollArea to ensure all content is accessible
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        transcription_content = QWidget()
        transcription_layout = QVBoxLayout(transcription_content)

        # Method Group
        method_group = QGroupBox("Transcription Method")
        method_layout = QVBoxLayout(method_group)

        self.transcription_method_label = QLabel('Transcription Method:', self)
        self.transcription_method_dropdown = QComboBox(self)
        self.transcription_method_dropdown.addItems(['Local', 'API'])
        self.transcription_method_dropdown.currentIndexChanged.connect(self.update_transcription_ui)

        method_info = QLabel("Choose between local processing (uses GPU/CPU) or cloud API (requires OpenAI API key)")
        method_info.setStyleSheet("color: gray; font-size: 10pt;")

        method_layout.addWidget(self.transcription_method_label)
        method_layout.addWidget(self.transcription_method_dropdown)
        method_layout.addWidget(method_info)

        transcription_layout.addWidget(method_group)
        transcription_layout.addSpacing(10)

        # Quality Group
        quality_group = QGroupBox("Transcription Quality")
        quality_layout = QVBoxLayout(quality_group)

        self.transcription_quality_label = QLabel(
            'Model Quality: (Larger = higher quality, but slower & uses more VRAM)', self)
        self.transcription_quality_dropdown = QComboBox(self)
        self.transcription_quality_dropdown.addItems([
            'distil-whisper/distil-small.en',
            'distil-whisper/distil-medium.en',
            'distil-whisper/distil-large-v2',
            'distil-whisper/distil-large-v3',
            'openai/whisper-tiny',
            'openai/whisper-base',
            'openai/whisper-small',
            'openai/whisper-medium',
            'openai/whisper-large-v2',
            'openai/whisper-large-v3'
        ])

        quality_info = QLabel("Recommended: distil-whisper/distil-medium.en for a good balance of speed and accuracy")
        quality_info.setStyleSheet("color: gray; font-size: 10pt;")

        quality_layout.addWidget(self.transcription_quality_label)
        quality_layout.addWidget(self.transcription_quality_dropdown)
        quality_layout.addWidget(quality_info)

        transcription_layout.addWidget(quality_group)
        transcription_layout.addSpacing(10)

        # Language and Speaker Detection
        options_group = QGroupBox("Additional Options")
        options_layout = QVBoxLayout(options_group)

        # Language selection
        self.language_label = QLabel('Transcription Language:', self)
        self.language_dropdown = QComboBox(self)
        self.language_dropdown.addItems([
            'English', 'Spanish', 'French', 'German', 'Chinese', 'Japanese',
            'Korean', 'Italian', 'Portuguese', 'Russian', 'Arabic', 'Hindi',
            'Dutch', 'Swedish', 'Turkish', 'Czech', 'Danish', 'Finnish'
        ])

        # Speaker detection/diarization
        self.speaker_detection_checkbox = QCheckBox('Enable Speaker Detection (Requires HF Auth Token)')

        options_layout.addWidget(self.language_label)
        options_layout.addWidget(self.language_dropdown)
        options_layout.addWidget(self.speaker_detection_checkbox)

        transcription_layout.addWidget(options_group)
        transcription_layout.addStretch()

        scroll_area.setWidget(transcription_content)

        # Main layout for the tab
        tab_layout = QVBoxLayout(transcription_tab)
        tab_layout.addWidget(scroll_area)

        self.tab_widget.addTab(transcription_tab, "Transcription")

    def create_gpt_tab(self):
        """Create the GPT Settings tab."""
        gpt_tab = QWidget()
        gpt_layout = QVBoxLayout(gpt_tab)

        # Model Group
        model_group = QGroupBox("GPT Model")
        model_layout = QVBoxLayout(model_group)

        self.gpt_model_label = QLabel('GPT Model: (GPT-4o strongly recommended)', self)
        self.gpt_model_dropdown = QComboBox(self)
        self.gpt_model_dropdown.addItems([
            'gpt-4o',
            'gpt-4o-mini',
            'gpt-4-turbo',
            'gpt-4',
            'gpt-3.5-turbo',
            'o1-preview'
        ])

        model_info = QLabel(
            "GPT-4o offers the best balance of quality and cost. o1-preview is the highest quality but most expensive.")
        model_info.setStyleSheet("color: gray; font-size: 10pt;")

        model_layout.addWidget(self.gpt_model_label)
        model_layout.addWidget(self.gpt_model_dropdown)
        model_layout.addWidget(model_info)

        gpt_layout.addWidget(model_group)
        gpt_layout.addSpacing(10)

        # Parameters Group
        params_group = QGroupBox("Generation Parameters")
        params_layout = QVBoxLayout(params_group)

        # Max Tokens
        tokens_layout = QHBoxLayout()
        self.max_tokens_label = QLabel('Max Tokens (1-16000):', self)
        self.max_tokens_spinbox = QSpinBox(self)
        self.max_tokens_spinbox.setRange(1, 16000)
        self.max_tokens_spinbox.setValue(16000)
        tokens_layout.addWidget(self.max_tokens_label)
        tokens_layout.addWidget(self.max_tokens_spinbox)

        # Temperature
        temp_layout = QHBoxLayout()
        self.temperature_label = QLabel('Temperature (0.0-2.0):', self)
        self.temperature_spinbox = QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        self.temperature_spinbox.setValue(0.7)
        temp_layout.addWidget(self.temperature_label)
        temp_layout.addWidget(self.temperature_spinbox)

        params_info = QLabel("Temperature controls randomness (higher = more creative, lower = more deterministic)")
        params_info.setStyleSheet("color: gray; font-size: 10pt;")

        params_layout.addLayout(tokens_layout)
        params_layout.addLayout(temp_layout)
        params_layout.addWidget(params_info)

        gpt_layout.addWidget(params_group)
        gpt_layout.addSpacing(10)

        # Prompt Templates
        prompts_group = QGroupBox("Prompt Templates")
        prompts_layout = QVBoxLayout(prompts_group)

        self.manage_prompts_button = QPushButton('Manage Prompt Templates')
        self.manage_prompts_button.clicked.connect(self.open_prompt_manager)
        self.manage_prompts_button.setIcon(QIcon(resource_path('icons/edit.svg')))

        prompts_layout.addWidget(self.manage_prompts_button)

        gpt_layout.addWidget(prompts_group)
        gpt_layout.addStretch()

        self.tab_widget.addTab(gpt_tab, "GPT Settings")

    def toggle_speaker_detection_checkbox(self):
        """Enable the speaker detection checkbox only if the HF API key is provided."""
        has_key = bool(self.hf_api_key_edit.text().strip())
        self.speaker_detection_checkbox.setEnabled(has_key)

        if not has_key:
            self.speaker_detection_checkbox.setChecked(False)
            self.speaker_detection_checkbox.setToolTip("HuggingFace Access Token required for speaker detection")
        else:
            self.speaker_detection_checkbox.setToolTip("Identify different speakers in the audio")

    def update_transcription_ui(self):
        """Update UI elements based on the selected transcription method."""
        is_local = self.transcription_method_dropdown.currentText() == 'Local'

        # Enable or disable quality selection for local transcription
        self.transcription_quality_label.setEnabled(is_local)
        self.transcription_quality_dropdown.setEnabled(is_local)

    def load_config(self):
        """Load configuration from config.json."""
        try:
            config_path = resource_path('config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as config_file:
                    config = json.load(config_file)

                    # Set transcription quality
                    quality = config.get('transcription_quality', 'distil-whisper/distil-small.en')
                    index = self.transcription_quality_dropdown.findText(quality)
                    if index != -1:
                        self.transcription_quality_dropdown.setCurrentIndex(index)

                    # Set GPT model
                    model = config.get('gpt_model', 'gpt-4o')
                    index = self.gpt_model_dropdown.findText(model)
                    if index != -1:
                        self.gpt_model_dropdown.setCurrentIndex(index)

                    # Set generation parameters
                    self.max_tokens_spinbox.setValue(config.get('max_tokens', 16000))
                    self.temperature_spinbox.setValue(config.get('temperature', 0.7))

                    # Set language
                    language = config.get('transcription_language', 'English')
                    index = self.language_dropdown.findText(language)
                    if index != -1:
                        self.language_dropdown.setCurrentIndex(index)

                    # Set speaker detection
                    self.speaker_detection_checkbox.setChecked(config.get('speaker_detection_enabled', False))

                    # Set transcription method
                    method = config.get('transcription_method', 'local')
                    index = self.transcription_method_dropdown.findText(method.capitalize())
                    if index != -1:
                        self.transcription_method_dropdown.setCurrentIndex(index)
            else:
                logging.warning(f"Config file not found at {config_path}, using defaults")

            # Load API keys from keyring
            hf_key = keyring.get_password(self.service_id, "HF_AUTH_TOKEN") or ''
            openai_key = keyring.get_password(self.service_id, "OPENAI_API_KEY") or ''
            self.hf_api_key_edit.setText(hf_key)
            self.openai_api_key_edit.setText(openai_key)

        except Exception as e:
            logging.error(f"Error loading config: {e}")
            QMessageBox.warning(self, "Configuration Error",
                                f"Failed to load configuration: {e}\nDefault settings will be used.")

    def save_config(self):
        """Save configuration to config.json."""
        config = {
            'transcription_quality': self.transcription_quality_dropdown.currentText(),
            'transcription_method': self.transcription_method_dropdown.currentText().lower(),
            'gpt_model': self.gpt_model_dropdown.currentText(),
            'max_tokens': self.max_tokens_spinbox.value(),
            'temperature': self.temperature_spinbox.value(),
            'speaker_detection_enabled': self.speaker_detection_checkbox.isChecked(),
            'transcription_language': self.language_dropdown.currentText()
        }

        config_path = resource_path('config.json')
        try:
            # Ensure the directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            with open(config_path, 'w') as config_file:
                json.dump(config, config_file, indent=4)

            logging.info(f"Configuration saved to {config_path}")
            self.settings_changed.emit()

        except Exception as e:
            logging.error(f"Error saving config: {e}")
            QMessageBox.critical(self, "Save Error", f"Failed to save configuration: {e}")

    def accept(self):
        """Handle dialog acceptance and save settings."""
        # Validate required fields based on selected options
        if self.transcription_method_dropdown.currentText() == 'API' and not self.openai_api_key_edit.text().strip():
            QMessageBox.warning(self, "Missing API Key",
                                "OpenAI API Key is required for API transcription method.")
            self.tab_widget.setCurrentIndex(0)  # Switch to API tab
            self.openai_api_key_edit.setFocus()
            return

        if self.speaker_detection_checkbox.isChecked() and not self.hf_api_key_edit.text().strip():
            QMessageBox.warning(self, "Missing API Key",
                                "HuggingFace Access Token is required for speaker detection.")
            self.tab_widget.setCurrentIndex(0)  # Switch to API tab
            self.hf_api_key_edit.setFocus()
            return

        # Save API keys to keyring
        hf_api_key = self.hf_api_key_edit.text().strip()
        openai_api_key = self.openai_api_key_edit.text().strip()

        if hf_api_key:
            keyring.set_password(self.service_id, "HF_AUTH_TOKEN", hf_api_key)

        if openai_api_key:
            keyring.set_password(self.service_id, "OPENAI_API_KEY", openai_api_key)

        # Save configuration
        self.save_config()

        super().accept()

    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        response = QMessageBox.question(
            self, "Reset to Defaults",
            "Are you sure you want to reset all settings to defaults? API keys will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if response == QMessageBox.StandardButton.Yes:
            # Keep the current API keys
            hf_key = self.hf_api_key_edit.text()
            openai_key = self.openai_api_key_edit.text()

            # Reset Transcription settings
            self.transcription_quality_dropdown.setCurrentText('distil-whisper/distil-medium.en')
            self.transcription_method_dropdown.setCurrentText('Local')
            self.language_dropdown.setCurrentText('English')
            self.speaker_detection_checkbox.setChecked(False)

            # Reset GPT settings
            self.gpt_model_dropdown.setCurrentText('gpt-4o')
            self.max_tokens_spinbox.setValue(16000)
            self.temperature_spinbox.setValue(0.7)

            # Restore API keys
            self.hf_api_key_edit.setText(hf_key)
            self.openai_api_key_edit.setText(openai_key)

            QMessageBox.information(self, "Settings Reset", "Settings have been reset to defaults.")

    def open_prompt_manager(self):
        """Open the prompt manager dialog."""
        try:
            dialog = PromptManagerDialog(self.main_window.preset_prompts, self)
            dialog.prompts_saved.connect(self.prompts_saved_handler)
            dialog.exec()
        except AttributeError:
            QMessageBox.warning(self, "Prompt Manager",
                                "Unable to access prompt templates. Please ensure the application is properly initialized.")
        except Exception as e:
            logging.error(f"Error opening prompt manager: {e}")
            QMessageBox.critical(self, "Prompt Manager Error", f"Failed to open prompt manager: {e}")

    def prompts_saved_handler(self):
        """Handle when prompts are saved in PromptManagerDialog."""
        self.prompts_updated.emit()