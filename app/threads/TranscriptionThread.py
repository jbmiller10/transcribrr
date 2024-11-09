import subprocess
import json
import os
import whisper
from PyQt6.QtCore import QThread, pyqtSignal


class TranscriptionThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path, transcription_quality, speaker_detection_enabled ,hf_auth_key,  language='en', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.transcription_quality = transcription_quality
        self.hf_token = hf_auth_key
        self.language = language
        self.speaker_detection = True #speaker_detection_enabled

    def run(self):
        try:
            self.update_progress.emit('Transcription started...')
            transcript_path = os.path.splitext(self.file_path)[0] + "_transcript.json"

            command = [
                'insanely-fast-whisper',
                '--file-name', self.file_path,
                '--transcript-path', transcript_path,
                '--language', self.language,
                '--hf_token', self.hf_token,
                #'--model-name', 'distil-whisper/large-v3',
                '--device-id', "mps",
            ]

            if self.speaker_detection:
                command.extend(['--diarization_model', 'pyannote/speaker-diarization'])

            # Execute the command
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise Exception(f"Error in transcription: {stderr}")

            self.update_progress.emit('Transcription completed. Parsing results...')

            # Load and parse the transcription output
            with open(transcript_path, 'r') as file:
                transcript_data = json.load(file)
                print(transcript_data)
                transcript_text = self.parse_transcript(transcript_data)

            self.completed.emit(transcript_text)
            self.update_progress.emit('All operations finished successfully.')
        except Exception as error:
            self.error.emit(str(error))

    def parse_transcript(self, data):
        # Custom parsing logic depending on the output format of insanely-fast-whisper
        # Generally, you would iterate through the entries to format them as needed
        transcript = ""
        for entry in data:
            transcript += f"Speaker {entry['speaker']}: {entry['text']}\n" if self.speaker_detection else f"{entry['text']}\n"
        return transcript.strip()