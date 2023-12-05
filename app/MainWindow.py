import re
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import os
import traceback
#from PyQt5.QtWidgets import  QLabel, QLineEdit
import keyring
import json
from app.YouTubeDownloadThread import YouTubeDownloadThread
from app.SettingsDialog import SettingsDialog
from app.TranscodingThread import TranscodingThread
from app.TranscriptionThread import TranscriptionThread
from app.GPT4ProcessingThread import GPT4ProcessingThread

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Transcribrr')
        self.setGeometry(100, 100, 1350, 768)
        self.is_process_running = False
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.layout = QGridLayout(self.central_widget)
        self.status_bar = QStatusBar()

        # Initialize instance variables for all settings with default values
        self.transcription_quality = None
        self.speaker_detection_enabled = None
        self.gpt_model = None
        self.max_tokens = None
        self.temperature = None
        self.hf_auth_key = None
        self.openai_api_key = None
        self.preset_prompts = {}
        # Load the configuration settings from the file
        self.load_config()
        self.load_prompts()
        self.init_ui()
        self.temp_files = []
        self.create_spinner()

        # Initialize threads without starting them
        self.youtube_thread = YouTubeDownloadThread()
        self.transcoding_thread = TranscodingThread()
        #self.transcription_thread = TranscriptionThread()
        #self.gpt4_processing_thread = GPT4ProcessingThread()

        # Connect signals to slots
        self.transcoding_thread.temp_file_created.connect(self.track_temp_file)
        self.youtube_thread.temp_file_created.connect(self.track_temp_file)

        # Initialize the list to track temporary files

        self.file_path = None

    def init_ui(self):
        # Main layout is horizontal
        main_layout = QHBoxLayout()
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.central_widget.setLayout(main_layout)

        # Splitter to contain the two main vertical layouts
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Left layout for recent recordings list and the '+' button
        left_layout = QVBoxLayout()
        self.recordings_list = QListWidget()
        self.add_recording_button = QPushButton('+')
        self.add_recording_button.setFixedSize(24, 24)  # Set the size of the '+' button
        left_layout.addWidget(self.recordings_list)
        left_layout.addWidget(self.add_recording_button, 0, Qt.AlignLeft)

        # Left widget to encapsulate the left layout
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        # Right layout for transcription controls and text displays
        right_layout = QVBoxLayout()

        # Upper controls layout for transcript type selection and action buttons
        upper_controls_layout = QHBoxLayout()
        self.transcription_type_combo = QComboBox()
        self.transcription_type_combo.addItems(
            ['Journal Entry', 'Meeting Minutes', 'Interview Summary'])  # Populate with your options

        # Icons for the action buttons
        save_icon = QIcon(QPixmap('icons/save.svg'))
        settings_icon = QIcon(QPixmap('icons/settings.svg'))
        # ... Add more icons as needed

        self.save_button = QPushButton(save_icon, '')  # Save button with icon
        self.settings_button = QPushButton(settings_icon, '')  # Settings button with icon
        # ... Instantiate more action buttons as needed

        upper_controls_layout.addWidget(self.transcription_type_combo)
        upper_controls_layout.addStretch()  # This will push the buttons to the right
        upper_controls_layout.addWidget(self.save_button)
        upper_controls_layout.addWidget(self.settings_button)
        # ... Add more buttons to the layout as needed

        # Text display for the transcript
        self.transcript_text = QTextEdit()

        # Status bar at the bottom
        self.status_bar = QStatusBar()
        self.status_message_label = QLabel('GPT-4 processing complete')  # Example status message
        self.status_bar.addWidget(self.status_message_label, 1)  # Add the label to the status bar

        # Adding upper controls and transcript text display to the right layout
        right_layout.addLayout(upper_controls_layout)
        right_layout.addWidget(self.transcript_text)
        right_layout.addWidget(self.status_bar)

        # Right widget to encapsulate the right layout
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        # Set the splitter sizes to match the design
        splitter.setSizes([400, 950])

        # Load configuration and prompts
        self.load_config()
        self.load_prompts()

        # The start transcription button (play button)
        self.start_transcription_button = QPushButton()
        self.start_transcription_button.setIcon(
            QIcon('icons/play.svg'))  # Assuming 'play.svg' is the icon for the play button
        self.start_transcription_button.clicked.connect(self.toggle_transcription_process)

        # Add the start transcription button to the layout
        upper_controls_layout.addWidget(self.start_transcription_button)

        # ... [other unchanged code] ...
        # Update button states
        self.update_button_state()

    def toggle_transcription_process(self):
        if self.is_process_running:
            self.cancel_transcription()
        else:
            self.start_transcription()

    def open_settings_dialog(self):
        try:
            dialog = SettingsDialog(self)
            dialog.settings_changed.connect(self.load_config)
            dialog.prompts_updated.connect(self.load_prompts)
            dialog.exec_()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, 'Exception', f'An exception occurred: {str(e)}')

    def open_file_dialog(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, 'Open Audio or Video File', '',
                                                   'Audio Files/Video Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov)', options=options)
        if file_name:
            self.file_path = file_name
            self.youtube_url_entry.clear()  # Clear the YouTube URL field
            self.youtube_url_entry.setDisabled(True)  # Disable the YouTube URL field
            self.status_bar.showMessage(f'Selected file: {file_name}')
            self.start_transcription_button.setEnabled(True)  # Enable transcription button

    def start_transcription(self):
        # Disable the transcription button to prevent starting another transcription process
        self.is_process_running = True
        self.show_spinner(True)
        self.update_button_state()
       #self.start_transcription_button.setDisabled(True)

        # Check the mode and start the appropriate process
        if self.mode_selector_dropdown.currentText() == 'YouTube URL':
            youtube_url = self.youtube_url_entry.text()
            if self.validate_youtube_url(youtube_url):
                self.start_youtube_download(youtube_url)
            else:
                QMessageBox.warning(self, 'Invalid URL', 'Please enter a valid YouTube URL.')
                self.start_transcription_button.setEnabled(True)  # Re-enable the button in case of an invalid URL
        elif self.file_path:
            self.start_transcription_thread(self.file_path)
        else:
            QMessageBox.warning(self, 'Input Required', 'Please select a file or enter a YouTube URL to transcribe.')
            self.start_transcription_button.setEnabled(True)  # Re-enable the button in case of missing input
        # Set the process running state to True
        self.is_process_running = True
        self.update_button_state()

    def cancel_transcription(self):
        # Implement the logic to cancel the ongoing process
        # For example, if you're using QThread, you can implement a method to terminate it
        if self.youtube_thread and self.youtube_thread.isRunning():
            self.youtube_thread.terminate()
        if self.transcription_thread and self.transcription_thread.isRunning():
            self.transcription_thread.terminate()
        if self.transcoding_thread and self.transcoding_thread.isRunning():
            self.transcoding_thread.terminate()

        # After canceling, set the process running state to False
        self.is_process_running = False
        self.update_button_state()
        self.cleanup_temp_files()
        self.show_spinner(False)
        self.status_bar.showMessage('Transcription cancelled.')

    def start_youtube_download(self, youtube_url):
        print('start_ytd')
        self.youtube_thread = YouTubeDownloadThread()
        self.youtube_thread.set_youtube_url(youtube_url)  # Set the URL before starting the thread
        self.youtube_thread.update_progress.connect(self.status_bar.showMessage)
        self.youtube_thread.completed.connect(self.on_youtube_download_complete)
        self.youtube_thread.error.connect(lambda e: self.show_error(e, traceback.format_exc()))
        self.youtube_thread.start()
        self.status_bar.showMessage('Downloading YouTube video...')

    def update_button_state(self):
        if self.is_process_running:
            self.start_transcription_button.setText('Cancel')
        else:
            self.start_transcription_button.setText('Start Transcription')

    def is_video_file(self, file_path):
        # Check if the file is a video file based on its extension (case-insensitive)
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov']
        file_extension = os.path.splitext(file_path)[1].lower()
        return file_extension in (ext.lower() for ext in video_extensions)

    def on_youtube_download_complete(self, file_path):
        # The YouTube video has been downloaded, now start the transcoding process
        self.status_bar.showMessage('YouTube video downloaded. Extracting audio...')
        self.transcode_file(file_path)

    def transcode_file(self, file_path):
        print('start transcode')
        # Start the transcoding process
        self.transcoding_thread = TranscodingThread(file_path)
        self.transcoding_thread.update_progress.connect(self.status_bar.showMessage)
        self.transcoding_thread.completed.connect(self.on_transcoding_complete)
        self.transcoding_thread.error.connect(self.show_error)
        self.transcoding_thread.start()

    def on_transcoding_complete(self, audio_file_path):
        self.transcription_thread = TranscriptionThread(audio_file_path, self.transcription_quality, self.speaker_detection_enabled, self.hf_auth_key)
        self.transcription_thread.update_progress.connect(self.status_bar.showMessage)
        self.transcription_thread.completed.connect(self.show_transcription_result)
        self.transcription_thread.error.connect(self.show_error)
        self.transcription_thread.finished.connect(self.clean_up_thread)
        self.transcription_thread.start()

    def start_transcription_thread(self, file_path):
        self.transcription_thread = TranscriptionThread(file_path, self.transcription_quality, self.speaker_detection_enabled, self.hf_auth_key)
        self.transcription_thread.update_progress.connect(self.status_bar.showMessage)
        self.transcription_thread.completed.connect(self.show_transcription_result)
        self.transcription_thread.error.connect(self.show_error)
        self.transcription_thread.start()

    def clean_up_thread(self):
        # Clean up the transcription thread and reset UI controls if necessary
        self.transcription_thread.deleteLater()
        self.transcription_thread = None
        self.start_transcription_button.setEnabled(True)  # Re-enable the transcription button

    def show_transcription_result(self, result):
        print("Updating raw transcript text with the result.")  # Debug print
        self.raw_transcript_text.setPlainText(result)  # Set the transcription result in the QTextEdit
        self.process_gpt_button.setEnabled(True)
        self.start_transcription_button.setEnabled(True)
        self.status_bar.showMessage('Transcription completed.')
        self.cleanup_temp_files()
        self.is_process_running = False
        self.update_button_state()
        self.show_spinner(False)

    def process_with_gpt(self):
        transcript = self.raw_transcript_text.toPlainText()
        self.show_spinner(True)
        prompt_instructions = self.gpt_prompt_text.toPlainText()
        if not transcript:
            QMessageBox.warning(self, 'Input Required', 'Please provide a transcription to process.')
            return
        self.gpt4_processing_thread = GPT4ProcessingThread(transcript, prompt_instructions,self.gpt_model, self.max_tokens, self.temperature, self.openai_api_key,)
        self.gpt4_processing_thread.update_progress.connect(self.status_bar.showMessage)
        self.gpt4_processing_thread.completed.connect(self.show_gpt_processed_result)
        self.gpt4_processing_thread.error.connect(self.show_error)
        self.gpt4_processing_thread.start()

    def show_gpt_processed_result(self, result):
        self.gpt_processed_text.setPlainText(result)
        self.show_spinner(False)
        self.status_bar.showMessage('GPT-4 processing completed.')

    def show_error(self, message, traceback_info=None):
        error_message = f'An error occurred: {message}'
        if traceback_info:
            error_message += f"\n{traceback_info}"
        QMessageBox.critical(self, 'Error', error_message)
        self.status_bar.showMessage('An error occurred: ' + message)
        self.is_process_running = False
        self.show_spinner(False)
        self.update_button_state()

    def validate_youtube_url(self, url):
        regex = r"(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})"
        return re.match(regex, url) is not None

    def validate_youtube_url_input(self):
        youtube_url = self.youtube_url_entry.text()
        is_valid = self.validate_youtube_url(youtube_url)
        # Enable the button if the URL is valid or if a local file is selected
        self.start_transcription_button.setEnabled(is_valid or bool(self.file_path))

    def cleanup_temp_files(self):
        for temp_file in self.temp_files:
            try:
                os.remove(temp_file)
                print(f"Removed temporary file: {temp_file}")
            except OSError as e:
                print(f"Error removing temporary file {temp_file}: {e.strerror}")
        self.temp_files.clear()  # Clear the list after cleanup

    def load_config(self):
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
                # Set instance variables from the configuration or use default values
        except FileNotFoundError:
            default_config = {
                'transcription_quality': self.transcription_quality_dropdown.currentText(),
                'gpt_model': self.gpt_model_dropdown.currentText(),
                'max_tokens': self.max_tokens_spinbox.value(),
                'temperature': self.temperature_spinbox.value(),
                'speaker_detection_enabled': self.speaker_detection_checkbox.isChecked(),
            }
            with open('config.json', 'w') as config_file:
                json.dump(config, config_file)
        finally:
            self.transcription_quality = config.get('transcription_quality', self.transcription_quality)
            self.speaker_detection_enabled = config.get('speaker_detection_enabled', self.speaker_detection_enabled)
            self.gpt_model = config.get('gpt_model', self.gpt_model)
            self.max_tokens = config.get('max_tokens', self.max_tokens)
            self.temperature = config.get('temperature', self.temperature)

        # load api keys
        self.hf_auth_key = keyring.get_password("transcription_application", "HF_AUTH_TOKEN")
        self.openai_api_key = keyring.get_password("transcription_application", "OPENAI_API_KEY")

        if not self.openai_api_key:
            self.status_bar.showMessage('Please set OpenAI API key in Settings')

        if not self.hf_auth_key:
            self.speaker_detection_enabled = False

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
                "Educational Course Summary": "Summarize this educational course transcript into a study guide format, including headings, key concepts, and important explanations."
            }

    def save_text_content(self, text_edit, dialog_title):
        file_name, _ = QFileDialog.getSaveFileName(self, dialog_title, '', 'Text Files (*.txt);;All Files (*)')
        if file_name:
            with open(file_name, 'w', encoding='utf-8') as file:
                file.write(text_edit.toPlainText())
            self.status_bar.showMessage(f'Content saved to {file_name}')

    def create_spinner(self):
        self.spinner_label = QLabel(self)
        self.spinner_movie = QMovie('icons/spinner.gif')
        self.spinner_label.setMovie(self.spinner_movie)
        spinner_size = QSize(26, 26)
        #self.spinner_label.setFixedSize(spinner_size)
        self.spinner_movie.setScaledSize(spinner_size)
        # Add the spinner to the status bar
        self.status_bar.addPermanentWidget(self.spinner_label, 0)
        self.spinner_label.hide()  # Hide it by default
    def show_spinner(self, show):
        if show:
            self.spinner_label.show()
            self.spinner_movie.start()  # Start the animation
        else:
            self.spinner_movie.stop()  # Stop the animation
            self.spinner_label.hide()

    def populate_recordings_list(self):
        self.recordings_list.clear()  # Clear the list before populating
        recordings_directory = '/recordings'  # Replace with the actual path
        for recording in os.listdir(recordings_directory):
            if recording.endswith('.wav'):
                # Create a QListWidgetItem for each recording
                item = QListWidgetItem(recording)
                self.recordings_list.addItem(item)