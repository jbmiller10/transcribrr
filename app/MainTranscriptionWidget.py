import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QMessageBox, QComboBox, QHBoxLayout, QLabel, QSizePolicy
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import pyqtSignal, QSize
from app.TextEditor import TextEditor
from app.threads.TranscriptionThread import TranscriptionThread
from app.threads.GPT4ProcessingThread import GPT4ProcessingThread
from app.SettingsDialog import SettingsDialog
from app.ToggleSwitch import ToggleSwitch
import traceback
import keyring

from app.database import *


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

        self.transcript_text.save_requested.connect(self.save_editor_state)

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
        if self.filepath is None:
            QMessageBox.warning(self, 'No File Selected', 'Please select a file to transcribe.')
            return

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        self.transcription_thread = TranscriptionThread(
            file_path=self.filepath,
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

        recording_id = self.current_selected_item.get_id()
        self.mode_switch.setValue(0)
        self.transcript_text.editor.setPlainText(transcript)

        # Save the raw transcript to the database
        conn = create_connection("./database/database.sqlite")
        update_recording(conn, recording_id,raw_transcript=transcript)

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
        prompt_instructions = self.preset_prompts.get(selected_prompt_key, '')

        with open('config.json', 'r') as config_file:
            config = json.load(config_file)

        openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")

        # Start the GPT-4 processing thread
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
            self.mode_switch.setValue(1)
            self.transcript_text.editor.setPlainText(processed_text)
            recording_id = self.current_selected_item.get_id()
            conn = create_connection("./database/database.sqlite")
            update_recording(conn, recording_id, processed_text=processed_text)

            self.is_transcribing = False
            try:
                self.update_ui_state()
            except Exception as e:
                print(f"An error occurred: {e}")
                traceback.print_exc()
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
            recording_id = self.current_selected_item.get_id()
            conn = create_connection("./database/database.sqlite")

            if conn is None:
                print("Error! Cannot connect to the database.")
                return

            recording = get_recording_by_id(conn, recording_id)

            if recording is None:
                print(f"No recording found with ID: {recording_id}")
                return

            # Deserialize formatted text if available; otherwise, fall back to raw text
            if self.mode_switch.value() == 0:  # 0 is for raw transcript
                raw_formatted = recording[7] if recording[7] else recording[5].encode('utf-8')
                self.transcript_text.deserialize_text_document(raw_formatted)
            else:  # 1 is for processed text
                processed_formatted = recording[8] if recording[8] else recording[6].encode('utf-8')
                self.transcript_text.deserialize_text_document(processed_formatted)

            # Close the database connection
            conn.close()

    def set_file_path(self, file_path):
        self.file_path = file_path

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
            return bool(recording and recording[5])  # Index 5 corresponds to the raw_transcript column
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
                "Youtube to Article": "Transform this raw transcript of a youtube video into a well-structured article, maintaining as much detail as possible. Do your best to replicate the speaker's voice and tone in your entry. Do not embelish by adding details not mentioned."
            }
    def load_recording(self, recording_id):
        conn = create_connection("./database/database.sqlite")
        recording = get_recording_by_id(conn, recording_id)
        self.textEditor.deserialize_text_document(recording['raw_transcript_formatted'], self.textEditor.editor.document())
        self.textEditor.deserialize_text_document(recording['processed_text_formatted'], self.textEditor.editor.document())

    def on_recording_item_selected(self, recording_item):
        try:
            self.current_selected_item = recording_item
            conn = create_connection("./database/database.sqlite")
            recording_id = self.current_selected_item.get_id()
            recording = get_recording_by_id(conn, recording_id)

            if recording:
                self.id = recording[0]
                self.filename = recording[1]
                self.filepath = recording[2]
                self.date_created = recording[3]
                self.duration = recording[4]

                # Check if formatted text is available and deserialize it; otherwise, fall back to raw text
                if self.mode_switch.value() == 0:  # 0 is for raw transcript
                    # Use formatted text if available, otherwise fall back to raw text, or clear if none
                    raw_formatted = recording[7] if recording[7] else recording[5]
                    self.transcript_text.deserialize_text_document(raw_formatted)
                else:  # 1 is for processed text
                    # Use formatted text if available, otherwise fall back to processed text, or clear if none
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
    def save_editor_state(self):
        if self.mode_switch.value() == 0:  # Raw transcript mode
            formatted_data = self.transcript_text.serialize_text_document()
            field_to_update = 'raw_transcript_formatted'
        else:  # Processed text mode
            formatted_data = self.transcript_text.serialize_text_document()
            field_to_update = 'processed_text_formatted'

        # Save the binary data to the database
        conn = create_connection("./database/database.sqlite")
        update_recording(conn, self.current_selected_item.get_id(), **{field_to_update: formatted_data})
        QMessageBox.information(self, "Success", "saved successfully.")

