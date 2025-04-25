from PyQt6.QtWidgets import (
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QDialog,
    QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QHBoxLayout, QGroupBox,
    QTabWidget, QWidget, QToolTip, QMessageBox, QScrollArea
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize, QThread, QTimer
from PyQt6.QtGui import QIcon
import keyring
import json
import os
import logging
import requests
from openai import OpenAI
import torch
from threading import Lock

from app.path_utils import resource_path
from app.path_utils import resource_path
from app.utils import ConfigManager, PromptManager
from app.PromptManagerDialog import PromptManagerDialog
from app.ThemeManager import ThemeManager
# Use ui_utils for messages
from app.ui_utils import show_error_message, show_info_message, show_confirmation_dialog
logger = logging.getLogger('transcribrr')


class OpenAIModelFetcherThread(QThread):
    """Fetch OpenAI models thread."""
    models_fetched = pyqtSignal(list)
    fetch_error = pyqtSignal(str)

    def __init__(self, api_key):
        super().__init__()
        self.api_key = api_key
        self._lock = Lock()
        self._stop_requested = False

    def request_stop(self):
         with self._lock:
             self._stop_requested = True

    def run(self):
        try:
            if not self.api_key:
                self.fetch_error.emit("No API key provided")
                return

            client = OpenAI(api_key=self.api_key)
            response = client.models.list()

            if self._stop_requested: return

            gpt_models = []
            for model in response.data:
                if self._stop_requested: return
                model_id = model.id
                # Refined filtering
                is_chat_model = (model_id.startswith("gpt-") or model_id.startswith("o1-"))
                is_not_vision = "vision" not in model_id.lower()
                is_not_instruct = "instruct" not in model_id.lower()
                is_not_latest_alias = not model_id.endswith("-latest")

                if is_chat_model and is_not_vision and is_not_instruct and is_not_latest_alias:
                    gpt_models.append(model_id)

            def model_sort_key(model_id):
                if "gpt-4o" in model_id: return 0
                if "o1-" in model_id: return 1 # Keep o1 variants high
                if "gpt-4" in model_id: return 2
                if "gpt-3.5" in model_id: return 3
                return 4 # Other models

            gpt_models.sort(key=model_sort_key)

            if not self._stop_requested:
                self.models_fetched.emit(gpt_models)

        except Exception as e:
            from app.secure import redact
            logger.error(f"Error fetching OpenAI models: {redact(str(e))}")
            if not self._stop_requested:
                # Use generic error message to avoid exposing API key in UI
                if "authentication" in str(e).lower() or "invalid" in str(e).lower():
                    self.fetch_error.emit("Authentication error: Please check your API key")
                else:
                    self.fetch_error.emit(f"Error fetching models: {redact(str(e))}")

    def stop(self):
        self.request_stop()
        self.wait(2000) # Wait up to 2 seconds
        if self.isRunning():
            self.terminate() # Force if needed
            self.wait(1000)


class SettingsDialog(QDialog):
    # settings_changed signal is less critical now ConfigManager handles updates
    # prompts_updated signal is replaced by direct interaction with PromptManager

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Settings')
        self.setMinimumWidth(600)

        self.config_manager = ConfigManager.instance()
        self.prompt_manager = PromptManager.instance()
        self.theme_manager = ThemeManager.instance()

        # Use secure module for versioned keyring service ID
        from app.secure import get_service_id
        self.service_id = get_service_id()
        self.model_fetcher = None
        self.available_openai_models = []

        self.main_layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.main_layout.addWidget(self.tab_widget)

        self.create_api_tab()
        self.create_transcription_tab()
        self.create_gpt_tab()
        self.create_appearance_tab()

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

        self.load_settings()

        # Connect signals for speaker detection toggling
        self.toggle_speaker_detection_checkbox()
        self.hf_api_key_edit.textChanged.connect(self.toggle_speaker_detection_checkbox)
        self.transcription_method_dropdown.currentIndexChanged.connect(self.toggle_speaker_detection_checkbox)
        try:
            self.hw_accel_checkbox.toggled.connect(self.toggle_speaker_detection_checkbox)
        except Exception as e:
            logger.warning(f"Could not connect hardware acceleration toggle signal: {e}")

    def create_api_tab(self):
        api_tab = QWidget()
        api_layout = QVBoxLayout(api_tab)
        api_group = QGroupBox("API Keys (Stored Securely)")
        api_group_layout = QVBoxLayout(api_group)

        # API Key entry
        openai_layout = QVBoxLayout()
        self.openai_api_key_label = QLabel('OpenAI API Key:', self)
        self.openai_api_key_label.setToolTip("Required for GPT processing and OpenAI Whisper API transcription")
        self.openai_api_key_edit = QLineEdit(self)
        self.openai_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # Disable copy/paste and drag-and-drop for security
        self.openai_api_key_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.openai_api_key_edit.setDragEnabled(False)
        openai_info = QLabel("Required for GPT processing and OpenAI Whisper API transcription")
        openai_info.setStyleSheet("color: gray; font-size: 10pt;")
        openai_layout.addWidget(self.openai_api_key_label)
        openai_layout.addWidget(self.openai_api_key_edit)
        openai_layout.addWidget(openai_info)
        api_group_layout.addLayout(openai_layout)
        api_group_layout.addSpacing(10)

        # HF token entry
        hf_layout = QVBoxLayout()
        self.hf_api_key_label = QLabel('HuggingFace Access Token:', self)
        self.hf_api_key_label.setToolTip("Required for speaker detection (diarization)")
        self.hf_api_key_edit = QLineEdit(self)
        self.hf_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        # Disable copy/paste and drag-and-drop for security
        self.hf_api_key_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.hf_api_key_edit.setDragEnabled(False)
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
        transcription_tab = QWidget()
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        transcription_content = QWidget()
        transcription_layout = QVBoxLayout(transcription_content)

        # Transcription method selection
        method_group = QGroupBox("Transcription Method")
        method_layout = QVBoxLayout(method_group)
        self.transcription_method_label = QLabel('Transcription Method:', self)
        self.transcription_method_dropdown = QComboBox(self)
        self.transcription_method_dropdown.addItems(['Local', 'API'])
        self.transcription_method_dropdown.currentIndexChanged.connect(self.update_transcription_ui)
        method_info = QLabel("Local uses your CPU/GPU. API uses OpenAI (requires key).")
        method_info.setStyleSheet("color: gray; font-size: 10pt;")
        method_layout.addWidget(self.transcription_method_label)
        method_layout.addWidget(self.transcription_method_dropdown)
        method_layout.addWidget(method_info)
        transcription_layout.addWidget(method_group)
        transcription_layout.addSpacing(10)

        # Quality Group
        quality_group = QGroupBox("Local Transcription Quality")
        quality_layout = QVBoxLayout(quality_group)
        self.transcription_quality_label = QLabel('Model Quality:', self)
        self.transcription_quality_dropdown = QComboBox(self)
        # Consider making this list dynamic or configurable
        self.transcription_quality_dropdown.addItems([
            'distil-whisper/distil-small.en','distil-whisper/distil-medium.en',
            'distil-whisper/distil-large-v2','distil-whisper/distil-large-v3',
            'openai/whisper-tiny','openai/whisper-base','openai/whisper-small',
            'openai/whisper-medium','openai/whisper-large-v2','openai/whisper-large-v3'
        ])
        quality_info = QLabel("Larger models are more accurate but slower & require more memory.")
        quality_info.setStyleSheet("color: gray; font-size: 10pt;")
        quality_layout.addWidget(self.transcription_quality_label)
        quality_layout.addWidget(self.transcription_quality_dropdown)
        quality_layout.addWidget(quality_info)
        transcription_layout.addWidget(quality_group)
        transcription_layout.addSpacing(10)

        # Options Group
        options_group = QGroupBox("Additional Options")
        options_layout = QVBoxLayout(options_group)
        self.language_label = QLabel('Transcription Language:', self)
        self.language_dropdown = QComboBox(self)
        # Consider generating this list programmatically or from constants
        self.language_dropdown.addItems([
            'English', 'Spanish', 'French', 'German', 'Chinese', 'Japanese', 'Korean',
             'Italian', 'Portuguese', 'Russian', 'Arabic', 'Hindi', 'Dutch', 'Swedish',
             'Turkish', 'Czech', 'Danish', 'Finnish' # Add more as needed
        ])
        self.speaker_detection_checkbox = QCheckBox('Enable Speaker Detection (Requires HF Token)')
        
        # Hardware Acceleration
        self.hw_accel_layout = QHBoxLayout()
        self.hw_accel_checkbox = QCheckBox('Enable Hardware Acceleration (CUDA/MPS)')
        
        # Check available hardware
        try:
            has_cuda = torch.cuda.is_available()
            has_mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
            hw_info = []
            
            if has_cuda:
                hw_info.append("CUDA")
            if has_mps:
                hw_info.append("MPS (Apple Silicon)")
                
            if hw_info:
                accel_tooltip = f"Use hardware acceleration: {', '.join(hw_info)}."
                if has_mps and not has_cuda:
                    accel_tooltip += " Note: Speaker detection is disabled with MPS acceleration."
            else:
                accel_tooltip = "No hardware acceleration detected. CPU will be used."
                
            self.hw_accel_checkbox.setToolTip(accel_tooltip)
        except Exception:
            # Handle case where torch might not be properly installed
            logger.warning("Could not check hardware acceleration availability.")
            hw_info = []
            self.hw_accel_checkbox.setToolTip("Unable to detect hardware acceleration. Enable if your device has GPU support.")
        
        self.hw_accel_layout.addWidget(self.hw_accel_checkbox)
        self.hw_accel_layout.addStretch()
        
        # Removed chunking options
        # Hardware acceleration info
        chunking_info = QLabel("")
        hw_accel_info = QLabel("Hardware acceleration improves speed. On Apple Silicon, speaker detection will be disabled with MPS.")
        hw_accel_info.setStyleSheet("color: gray; font-size: 10pt;")
        
        options_layout.addWidget(self.language_label)
        options_layout.addWidget(self.language_dropdown)
        options_layout.addWidget(self.speaker_detection_checkbox)
        options_layout.addLayout(self.hw_accel_layout)
        options_layout.addWidget(hw_accel_info)
        transcription_layout.addWidget(options_group)
        transcription_layout.addStretch()

        scroll_area.setWidget(transcription_content)
        tab_layout = QVBoxLayout(transcription_tab)
        tab_layout.addWidget(scroll_area)
        self.tab_widget.addTab(transcription_tab, "Transcription")
        self.update_transcription_ui() # Initial UI state

    def create_gpt_tab(self):
        gpt_tab = QWidget()
        gpt_layout = QVBoxLayout(gpt_tab)

        # Model Group
        model_group = QGroupBox("GPT Model")
        model_layout = QVBoxLayout(model_group)
        model_header_layout = QHBoxLayout()
        self.gpt_model_label = QLabel('GPT Model:', self)
        self.refresh_models_button = QPushButton("Refresh Models")
        self.refresh_models_button.setToolTip("Fetch available models from OpenAI")
        self.refresh_models_button.clicked.connect(self.fetch_openai_models)
        model_header_layout.addWidget(self.gpt_model_label)
        model_header_layout.addWidget(self.refresh_models_button)
        self.gpt_model_dropdown = QComboBox(self)
        self.default_models = ['gpt-4o','gpt-4o-mini','gpt-4-turbo','gpt-4','gpt-3.5-turbo','o1-preview']
        self.gpt_model_dropdown.addItems(self.default_models)
        model_status_layout = QHBoxLayout()
        self.model_status_label = QLabel("")
        self.model_status_label.setStyleSheet("color: gray; font-style: italic;")
        model_status_layout.addWidget(self.model_status_label)
        model_status_layout.addStretch()
        model_info = QLabel("GPT-4o recommended. o1-preview is high quality but costly.")
        model_info.setStyleSheet("color: gray; font-size: 10pt;")
        model_layout.addLayout(model_header_layout)
        model_layout.addWidget(self.gpt_model_dropdown)
        model_layout.addLayout(model_status_layout)
        model_layout.addWidget(model_info)
        gpt_layout.addWidget(model_group)
        gpt_layout.addSpacing(10)

        # Parameters Group
        params_group = QGroupBox("Generation Parameters")
        params_layout = QVBoxLayout(params_group)
        tokens_layout = QHBoxLayout()
        self.max_tokens_label = QLabel('Max Tokens:', self)
        self.max_tokens_spinbox = QSpinBox(self)
        self.max_tokens_spinbox.setRange(1, 16000) # Adjust range as needed
        tokens_layout.addWidget(self.max_tokens_label)
        tokens_layout.addWidget(self.max_tokens_spinbox)
        temp_layout = QHBoxLayout()
        self.temperature_label = QLabel('Temperature:', self)
        self.temperature_spinbox = QDoubleSpinBox(self)
        self.temperature_spinbox.setRange(0.0, 2.0)
        self.temperature_spinbox.setSingleStep(0.1)
        temp_layout.addWidget(self.temperature_label)
        temp_layout.addWidget(self.temperature_spinbox)
        params_info = QLabel("Temp: 0=deterministic, 2=creative. Tokens limit output length.")
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

    def create_appearance_tab(self):
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)
        theme_group = QGroupBox("Theme")
        theme_layout = QVBoxLayout(theme_group)
        self.theme_label = QLabel('Application Theme:', self)
        self.theme_dropdown = QComboBox(self)
        self.theme_dropdown.addItems(['Light', 'Dark'])
        current_theme = self.theme_manager.current_theme
        self.theme_dropdown.setCurrentText(current_theme.capitalize())
        preview_layout = QHBoxLayout()
        self.theme_preview = QLabel()
        self.theme_preview.setMinimumSize(300, 150)
        self.theme_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_theme_preview()
        self.theme_dropdown.currentTextChanged.connect(self.update_theme_preview)
        preview_layout.addWidget(self.theme_preview)
        theme_layout.addWidget(self.theme_label)
        theme_layout.addWidget(self.theme_dropdown)
        theme_layout.addLayout(preview_layout)
        appearance_layout.addWidget(theme_group)
        appearance_layout.addStretch()
        self.tab_widget.addTab(appearance_tab, "Appearance")
    # --- UI Logic ---
    def toggle_speaker_detection_checkbox(self):
        try:
            # First, check if we're using API method - speaker detection not compatible with API
            is_local = self.transcription_method_dropdown.currentText() == 'Local'
            if not is_local:
                self.speaker_detection_checkbox.setChecked(False)
                self.speaker_detection_checkbox.setEnabled(False)
                self.speaker_detection_checkbox.setToolTip("Speaker detection requires local transcription method")
                return
                
            has_key = bool(self.hf_api_key_edit.text().strip())
            
            # Safely check hardware acceleration status and available hardware
            try:
                hw_accel_enabled = (hasattr(self, 'hw_accel_checkbox') and 
                                  self.hw_accel_checkbox.isChecked())
                
                # Check if MPS is the only available hardware - only then we need to disable speaker detection
                has_cuda = torch.cuda.is_available()
                has_mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
                
                # Only disable speaker detection for MPS-only devices with hardware acceleration enabled
                mps_only_device = has_mps and not has_cuda
                disable_for_hw = hw_accel_enabled and mps_only_device
            except Exception:
                logger.warning("Error checking hardware status, assuming standard operation")
                disable_for_hw = False
            
            # Disable speaker detection if either no key OR on MPS-only device with HW accel enabled
            can_enable = has_key and not disable_for_hw
            self.speaker_detection_checkbox.setEnabled(can_enable)
            
            if not has_key:
                self.speaker_detection_checkbox.setChecked(False)
                self.speaker_detection_checkbox.setToolTip("HuggingFace Access Token required for speaker detection")
            elif disable_for_hw:
                self.speaker_detection_checkbox.setChecked(False)
                self.speaker_detection_checkbox.setToolTip("Speaker detection is disabled with MPS acceleration")
            else:
                self.speaker_detection_checkbox.setToolTip("Identify different speakers in the audio")
        except Exception as e:
            logger.warning(f"Error in toggle_speaker_detection_checkbox: {e}")
    def update_transcription_ui(self):
        is_local = self.transcription_method_dropdown.currentText() == 'Local'
        # Only enable quality dropdown for local method
        self.transcription_quality_label.setEnabled(is_local)
        self.transcription_quality_dropdown.setEnabled(is_local)
        
        # Speaker detection only works with local transcription
        if not is_local:
            self.speaker_detection_checkbox.setChecked(False)
            self.speaker_detection_checkbox.setEnabled(False)
            self.speaker_detection_checkbox.setToolTip("Speaker detection requires local transcription method")
        else:
            # If using local method, enable/disable based on other factors
            self.toggle_speaker_detection_checkbox()

    def update_theme_preview(self):
        selected_theme = self.theme_dropdown.currentText().lower()
        bg_color, text_color, btn_color, border_color = ("#2B2B2B", "#EEEEEE", "#3A3A3A", "#555555") if selected_theme == 'dark' else ("#FFFFFF", "#202020", "#F5F5F5", "#DDDDDD")
        preview_html = f"""<div style="background-color: {bg_color}; color: {text_color}; padding: 20px; width: 280px; height: 130px; border: 1px solid {border_color}; border-radius: 5px;"> ... </div>""" # Simplified preview
        self.theme_preview.setText(preview_html)

    def fetch_openai_models(self):
        from app.secure import get_api_key
        api_key = get_api_key("OPENAI_API_KEY")
        if not api_key:
            self.model_status_label.setText("API key not found. Add key in API Keys tab.")
            self.model_status_label.setStyleSheet("color: red;")
            return

        self.refresh_models_button.setEnabled(False)
        self.model_status_label.setText("Fetching models...")
        self.model_status_label.setStyleSheet("color: gray;")

        if self.model_fetcher and self.model_fetcher.isRunning():
            self.model_fetcher.stop() # Stop previous fetcher

        self.model_fetcher = OpenAIModelFetcherThread(api_key)
        self.model_fetcher.models_fetched.connect(self.on_models_fetched)
        self.model_fetcher.fetch_error.connect(self.on_model_fetch_error)
        self.model_fetcher.start()

    def on_models_fetched(self, models):
        self.available_openai_models = models
        current_model = self.gpt_model_dropdown.currentText()
        self.gpt_model_dropdown.blockSignals(True)
        self.gpt_model_dropdown.clear()
        self.gpt_model_dropdown.addItems(models if models else self.default_models)
        index = self.gpt_model_dropdown.findText(current_model)
        self.gpt_model_dropdown.setCurrentIndex(index if index >= 0 else 0)
        self.gpt_model_dropdown.blockSignals(False)
        self.refresh_models_button.setEnabled(True)
        self.model_status_label.setText(f"Found {len(models)} models" if models else "Using default models")
        self.model_status_label.setStyleSheet("color: green;" if models else "color: orange;")
        logger.info(f"Fetched {len(models)} models from OpenAI API")

    def on_model_fetch_error(self, error_message):
        self.refresh_models_button.setEnabled(True)
        self.model_status_label.setText(f"Error fetching: {error_message}")
        self.model_status_label.setStyleSheet("color: red;")
        if self.gpt_model_dropdown.count() == 0:
            self.gpt_model_dropdown.addItems(self.default_models)
        logger.error(f"Error fetching OpenAI models: {error_message}")

    # --- Load/Save Logic ---
    def load_settings(self):
        """Load settings."""
        try:
            config = self.config_manager.get_all()

            # Transcription settings
            quality = config.get('transcription_quality')
            index = self.transcription_quality_dropdown.findText(quality)
            self.transcription_quality_dropdown.setCurrentIndex(index if index != -1 else 0)

            method = config.get('transcription_method', '').lower()
            if method == 'api':
                self.transcription_method_dropdown.setCurrentText('API')
            else:
                self.transcription_method_dropdown.setCurrentText('Local')

            language = config.get('transcription_language')
            index = self.language_dropdown.findText(language)
            self.language_dropdown.setCurrentIndex(index if index != -1 else 0)

            self.speaker_detection_checkbox.setChecked(config.get('speaker_detection_enabled', False))
            
            # Hardware acceleration
            self.hw_accel_checkbox.setChecked(config.get('hardware_acceleration_enabled', True))
            
            # Check for incompatibilities between hardware acceleration and speaker detection
            try:
                # Only check for MPS-only devices (no CUDA)
                has_cuda = torch.cuda.is_available()
                has_mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
                mps_only = has_mps and not has_cuda
                
                # If MPS-only device with hardware acceleration enabled, disable speaker detection
                if mps_only and self.hw_accel_checkbox.isChecked():
                    self.speaker_detection_checkbox.setChecked(False)
                    self.speaker_detection_checkbox.setEnabled(False)
            except Exception as e:
                logger.warning(f"Error checking hardware compatibility: {e}")

            # GPT settings
            model = config.get('gpt_model')
            # Don't set index immediately, wait for potential model fetch
            if self.gpt_model_dropdown.findText(model) == -1:
                 if model not in self.default_models: # Add if not default
                      self.gpt_model_dropdown.addItem(model)
                 self.gpt_model_dropdown.setCurrentText(model)
            else:
                 self.gpt_model_dropdown.setCurrentText(model)


            self.max_tokens_spinbox.setValue(config.get('max_tokens', 16000))
            self.temperature_spinbox.setValue(config.get('temperature', 0.7))

            # Appearance settings
            theme = config.get('theme')
            index = self.theme_dropdown.findText(theme.capitalize())
            self.theme_dropdown.setCurrentIndex(index if index != -1 else 0)
            self.update_theme_preview()

            # Load API keys from keyring using secure API
            from app.secure import get_api_key
            hf_key = get_api_key("HF_AUTH_TOKEN") or ''
            openai_key = get_api_key("OPENAI_API_KEY") or ''
            self.hf_api_key_edit.setText(hf_key)
            self.openai_api_key_edit.setText(openai_key)

            # Attempt to fetch models if API key is present
            if openai_key:
                 QTimer.singleShot(200, self.fetch_openai_models) # Short delay

        except Exception as e:
            logger.error(f"Error loading settings: {e}", exc_info=True)
            show_error_message(self, "Configuration Error", f"Failed to load settings: {e}")

    def save_settings(self):
        """Save settings."""
        # --- Save API Keys to Keyring ---
        hf_api_key = self.hf_api_key_edit.text().strip()
        openai_api_key = self.openai_api_key_edit.text().strip()

        try:
            # Use secure API for storing keys
            from app.secure import set_api_key
            
            # Save HuggingFace token
            hf_success = set_api_key("HF_AUTH_TOKEN", hf_api_key)
            
            # Save OpenAI API key
            openai_success = set_api_key("OPENAI_API_KEY", openai_api_key)
            
            if not (hf_success and openai_success):
                from app.ui_utils import safe_error
                safe_error(self, "Keyring Error", "Could not save API keys securely. Check system keyring access.")
        except Exception as e:
            from app.secure import redact
            from app.ui_utils import safe_error
            logger.error(f"Error saving API keys to keyring: {redact(str(e))}")
            safe_error(self, "Keyring Error", f"Could not save API keys securely: {e}")
            # Decide if we should proceed or stop here? For now, proceed with config save.

        # --- Save General Settings via ConfigManager ---

        # Get transcription method and ensure it's properly formatted 
        transcription_method = self.transcription_method_dropdown.currentText()
        if transcription_method.upper() == 'API':
            transcription_method = 'api'
        else:
            transcription_method = 'local'

        config_updates = {
            'transcription_quality': self.transcription_quality_dropdown.currentText(),
            'transcription_method': transcription_method,
            'gpt_model': self.gpt_model_dropdown.currentText(),
            'max_tokens': self.max_tokens_spinbox.value(),
            'temperature': self.temperature_spinbox.value(),
            'speaker_detection_enabled': self.speaker_detection_checkbox.isChecked(),
            'transcription_language': self.language_dropdown.currentText(),
            'theme': self.theme_dropdown.currentText().lower(),
            'hardware_acceleration_enabled': self.hw_accel_checkbox.isChecked()
        }

        try:
            self.config_manager.update(config_updates)
            logger.info("Configuration saved via ConfigManager")

            # The theme will be automatically applied via the ConfigManager signal
            # No need to manually call apply_theme since ThemeManager listens for config changes

        except Exception as e:
             logger.error(f"Error saving configuration: {e}")
             show_error_message(self, "Save Error", f"Failed to save configuration: {e}")


    def accept(self):
        # Validation before saving
        if self.transcription_method_dropdown.currentText() == 'API' and not self.openai_api_key_edit.text().strip():
            from app.ui_utils import safe_error
            safe_error(self, "Missing API Key", "OpenAI API Key is required for API transcription method.")
            self.tab_widget.setCurrentIndex(0)
            self.openai_api_key_edit.setFocus()
            return

        if self.speaker_detection_checkbox.isChecked() and not self.hf_api_key_edit.text().strip():
            from app.ui_utils import safe_error
            safe_error(self, "Missing API Key", "HuggingFace Access Token is required for speaker detection.")
            self.tab_widget.setCurrentIndex(0)
            self.hf_api_key_edit.setFocus()
            return

        self.save_settings() # Consolidate saving logic
        super().accept()

    def reset_to_defaults(self):
        if show_confirmation_dialog(
            self, "Reset to Defaults",
            "Reset all settings (except API keys) to their defaults?",
            QMessageBox.StandardButton.No):

            # Keep the current API keys from the UI fields
            hf_key = self.hf_api_key_edit.text()
            openai_key = self.openai_api_key_edit.text()

            # Reset UI fields to default values from constants
            from app.constants import DEFAULT_CONFIG
            self.transcription_quality_dropdown.setCurrentText(DEFAULT_CONFIG['transcription_quality'])
            self.transcription_method_dropdown.setCurrentText(DEFAULT_CONFIG['transcription_method'].capitalize())
            self.language_dropdown.setCurrentText(DEFAULT_CONFIG['transcription_language'].capitalize())
            self.speaker_detection_checkbox.setChecked(DEFAULT_CONFIG['speaker_detection_enabled'])
            self.hw_accel_checkbox.setChecked(DEFAULT_CONFIG['hardware_acceleration_enabled'])
            self.gpt_model_dropdown.setCurrentText(DEFAULT_CONFIG['gpt_model'])
            self.max_tokens_spinbox.setValue(DEFAULT_CONFIG['max_tokens'])
            self.temperature_spinbox.setValue(DEFAULT_CONFIG['temperature'])
            self.theme_dropdown.setCurrentText(DEFAULT_CONFIG['theme'].capitalize())
            self.update_theme_preview()

            # Restore API key UI fields (they weren't saved yet)
            self.hf_api_key_edit.setText(hf_key)
            self.openai_api_key_edit.setText(openai_key)

            show_info_message(self, "Settings Reset", "Settings have been reset to defaults. Press Save to apply.")

    def open_prompt_manager(self):
        # PromptManagerDialog now interacts directly with PromptManager
        try:
            dialog = PromptManagerDialog(self) # No need to pass prompts
            dialog.exec()
            # No need to connect prompts_saved signal
        except Exception as e:
            logger.error(f"Error opening prompt manager: {e}", exc_info=True)
            show_error_message(self, "Prompt Manager Error", f"Failed to open prompt manager: {e}")

    def closeEvent(self, event):
        # Ensure the model fetcher thread is stopped if the dialog is closed early
        if self.model_fetcher and self.model_fetcher.isRunning():
            self.model_fetcher.stop()
        super().closeEvent(event)
