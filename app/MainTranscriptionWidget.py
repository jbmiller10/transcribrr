import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QMessageBox, QComboBox, QHBoxLayout, QLabel, QSizePolicy
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal, QSize
from app.TextEditor import TextEditor
from app.TranscriptionThread import TranscriptionThread
from app.GPT4ProcessingThread import GPT4ProcessingThread
from app.SettingsDialog import SettingsDialog
from app.ToggleSwitch import ToggleSwitch
import traceback
import keyring


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

        self.transcription_type_combo = QComboBox()
        self.transcription_type_combo.addItems([
            'Journal Entry', 'Meeting Minutes', 'Interview Summary'
        ])
        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon('icons/play.svg'))
        self.play_button.setFixedSize(50, 50)
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon('icons/save.svg'))
        self.save_button.setFixedSize(50, 50)

        self.top_toolbar = QHBoxLayout()
        self.horizontal_spacer = QWidget()
        self.horizontal_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        #self.top_toolbar.addWidget(self.horizontal_spacer)

        ###prompt dropdown
        self.load_prompts()
        self.gpt_prompt_dropdown = QComboBox()
        self.top_toolbar.addWidget(self.gpt_prompt_dropdown)
        self.top_toolbar.addWidget(self.horizontal_spacer)
        self.gpt_prompt_dropdown.addItems(self.preset_prompts.keys())

        self.raw_transcript_label = QLabel('Raw Transcript')
        self.top_toolbar.addWidget(self.raw_transcript_label)
        self.mode_switch = ToggleSwitch()
        self.mode_switch.setValue(0)
        self.top_toolbar.addWidget(self.mode_switch)
        self.gpt_processed_label = QLabel('Processed W/ GPT')
        self.top_toolbar.addWidget(self.gpt_processed_label)

        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon('icons/settings.svg'))
        self.settings_button.setIconSize(QSize(25, 25))
        self.settings_button.setFixedSize(30, 30)
        self.transcript_text = TextEditor()
        self.top_toolbar.addWidget(self.horizontal_spacer)
        self.top_toolbar.addWidget(self.settings_button)
        self.layout.addLayout(self.top_toolbar)
        self.layout.addWidget(self.transcript_text)

        self.play_button.clicked.connect(self.toggle_transcription)
        self.save_button.clicked.connect(self.save_transcription)
        self.settings_button.clicked.connect(self.request_settings)
        self.transcript_text.transcription_requested.connect(self.start_transcription)
        self.transcript_text.gpt4_processing_requested.connect(self.start_gpt4_processing)
        self.mode_switch.valueChanged.connect(self.toggle_transcription_view)

        self.file_path = None
        self.is_transcribing = False
        self.is_processing_gpt4 = False


    def toggle_transcription(self):
        if self.play_button.text() == 'Play':
            self.play_button.setIcon(QIcon('icons/stop.svg'))
            self.transcriptionStarted.emit()
            self.play_button.setText('Stop')
        else:
            self.play_button.setIcon(QIcon('icons/play.svg'))
            self.transcriptionStopped.emit()
            self.play_button.setText('Play')
    def set_file_path(self, file_path):
        self.file_path = file_path
    def save_transcription(self):
        content = self.transcript_text.editor.toPlainText()
        self.transcriptionSaved.emit(content)

    def request_settings(self):
        dialog = SettingsDialog(self)
        dialog.settings_changed.connect(self.load_config)
        dialog.prompts_updated.connect(self.load_prompts)
        dialog.exec()

    def start_transcription(self):
        if self.file_path is None:
            QMessageBox.warning(self, 'No File Selected', 'Please select a file to transcribe.')
            return

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        self.transcription_thread = TranscriptionThread(
            file_path=self.file_path,
            transcription_quality=config.get('transcription_quality', 'medium'),
            speaker_detection_enabled=config.get('speaker_detection_enabled', False),
            hf_auth_key=config.get('hf_auth_key', '')
        )
        self.transcription_thread.completed.connect(self.on_transcription_completed)
        self.transcription_thread.update_progress.connect(self.on_transcription_progress)
        self.transcription_thread.error.connect(self.on_transcription_error)
        self.transcription_thread.start()
        self.is_transcribing = True
        self.update_ui_state()

    def on_transcription_completed(self, transcript):
        self.transcript_text.editor.setPlainText(transcript)
        if self.current_selected_item:
            recording_item = self.current_selected_item
            self.mode_switch.setValue(0)
            recording_item.set_raw_transcript(transcript)
            self.transcript_text.editor.setPlainText(transcript)
        self.is_transcribing = False
        try:
            self.update_ui_state()
        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()


    def on_transcription_progress(self, progress_message):
        self.update_progress.emit(progress_message)

    def on_transcription_error(self, error_message):
        QMessageBox.critical(self, 'Transcription Error', error_message)
        self.is_transcribing = False
        self.update_ui_state()

    def start_gpt4_processing(self):
        recording_item = self.current_selected_item
        raw_transcript = recording_item.get_raw_transcript()

        selected_prompt_key = self.gpt_prompt_dropdown.currentText()
        prompt_instructions = self.preset_prompts.get(selected_prompt_key, '')

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        #self.hf_auth_key = keyring.get_password("transcription_application", "HF_AUTH_TOKEN")
        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")

        self.gpt4_processing_thread = GPT4ProcessingThread(
            transcript=raw_transcript,
            prompt_instructions=prompt_instructions,
            gpt_model=config.get('gpt_model', 'gpt-4-1106-preview'),
            max_tokens=config.get('max_tokens', 4096),
            temperature=config.get('temperature', 0.7),
            openai_api_key=openai_api_key
        )
        self.gpt4_processing_thread.completed.connect(self.on_gpt4_processing_completed)
        self.gpt4_processing_thread.update_progress.connect(self.on_gpt4_processing_progress)
        self.gpt4_processing_thread.error.connect(self.on_gpt4_processing_error)
        self.gpt4_processing_thread.start()
        self.is_processing_gpt4 = True
        self.update_ui_state()

    def on_gpt4_processing_completed(self, processed_text):
        if self.current_selected_item:
            recording_item = self.current_selected_item
            recording_item.set_processed_text(processed_text)
            self.transcript_text.editor.setPlainText(processed_text)
            self.mode_switch.setValue(1)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def on_gpt4_processing_progress(self, progress_message):
        self.update_progress.emit(progress_message)

    def on_gpt4_processing_error(self, error_message):
        QMessageBox.critical(self, 'GPT-4 Processing Error', error_message)
        self.is_processing_gpt4 = False
        self.update_ui_state()

    def toggle_transcription_view(self):
        if self.current_selected_item is not None:
            recording_item = self.current_selected_item
            if self.mode_switch.value() == 0:  #  0 s for raw transcript
                self.transcript_text.editor.setPlainText(recording_item.get_raw_transcript())
            else:  # 1 is for processed text
                self.transcript_text.editor.setPlainText(recording_item.get_processed_text())

    def set_file_path(self, file_path):
        self.file_path = file_path

    def update_ui_state(self):
        # Enable or disable buttons based on the current state
        self.transcript_text._toolbar_actions['start_transcription'].setEnabled(not self.is_transcribing)
        self.transcript_text._toolbar_actions['process_with_gpt4'].setEnabled(
            not self.is_transcribing and not self.is_processing_gpt4 and self.raw_transcript_available()
        )

    def raw_transcript_available(self):
        # Check if there is a raw transcript available for processing
        if self.current_selected_item is not None:
            if self.current_selected_item:
                recording_item = self.current_selected_item
            return bool(recording_item.get_raw_transcript())
        return False

    def load_config(self):
        pass

    def load_prompts(self):
        try:
            with open('preset_prompts.json', 'r') as file:
                self.preset_prompts = json.load(file)
                try:
                    self.gpt_prompt_dropdown.clear()
                    self.gpt_prompt_dropdown.addItems(self.preset_prompts.keys())
                except AttributeError:
                    pass
        except FileNotFoundError:
            print('No existing prompts file found. Using Defaults.')
            self.preset_prompts = {
                "Journal Entry Formatting": "Format this raw audio transcript into a clean, coherent journal entry, maintaining a first-person narrative style.",
                "Meeting Minutes": "Convert this transcript into a structured format of meeting minutes, highlighting key points, decisions made, and action items.",
                "Interview Summary": "Summarize this interview transcript, emphasizing the main questions, responses, and any significant insights or conclusions.",
                "Lecture Notes": "Condense this lecture transcript into concise notes, outlining the main topics, subtopics, and key points discussed.",
                "Podcast Highlights": "Extract key highlights and interesting moments from this podcast transcript, presenting them in a bullet-point format.",
                "Dialogue Cleanup": "Edit this dialogue transcript to remove filler words, repeated phrases, and non-verbal cues, making it more readable.",
                "Speech to Article": "Transform this speech transcript into a well-structured article, maintaining the speaker's key messages.",
                "Q&A Format": "Organize this transcript into a clear question-and-answer format, ensuring each question and its corresponding answer are clearly presented.",
                "Debate Summary": "Summarize this debate transcript, outlining the main points and arguments presented by each participant.",
                "Technical Explanation": "Rewrite this technical discussion transcript into a simpler, more understandable format for a general audience.",
                "Legal Testimony Review": "Condense this legal testimony transcript, focusing on the key statements and evidence presented.",
                "Conference Session Summary": "Provide a concise summary of this conference session transcript, highlighting the main themes, discussions, and conclusions.",
                "Educational Course Summary": "Summarize this educational course transcript into a study guide format, including headings, key concepts, and important explanations.",
                "Youtube to Article": "Transform this raw transcript of a youtube video into a well-structured article, maintaining as much detail as possible."
            }

    def on_recording_item_selected(self, recording_item):
        try:
            self.current_selected_item = recording_item
            if self.mode_switch.value() == 0:
                self.transcript_text.editor.setPlainText(recording_item.get_raw_transcript())
            elif self.mode_switch.value() == 1:
                self.transcript_text.editor.setPlainText(recording_item.get_processed_text())
        except Exception as e:
            print(f"An error occurred: {e}")
            traceback.print_exc()