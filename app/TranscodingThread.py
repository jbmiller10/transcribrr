from PyQt6.QtCore import QThread, pyqtSignal
from pydub import AudioSegment
import os
import traceback

class TranscodingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path=None, target_format='mp3', *args, **kwargs):
        super().__init__(*args, **kwargs)  # Changed to PyQt6 super() call
        self.file_path = file_path
        self.target_format = target_format

    def run(self):
        try:
            self.update_progress.emit('Starting conversion...')
            target_file_path = self.generate_unique_target_path(self.file_path, self.target_format)

            # Transcode the audio
            self.reencode_audio(self.file_path, target_file_path)

            # Delete the original file after successful conversion
            if os.path.exists(target_file_path):
                os.remove(self.file_path)

            self.completed.emit(target_file_path)
            self.update_progress.emit('Conversion completed.')
        except Exception as e:
            error_message = f'Error during conversion: {e}'
            self.handle_error(error_message)

    def generate_unique_target_path(self, file_path, target_format):
        base_dir = os.path.dirname(file_path)
        base_name = os.path.basename(file_path)
        name, _ = os.path.splitext(base_name)
        counter = 1

        target_file_path = os.path.join(base_dir, f"{name}.{target_format}")
        while os.path.exists(target_file_path):
            target_file_path = os.path.join(base_dir, f"{name}_{counter}.{target_format}")
            counter += 1

        return target_file_path

    def reencode_audio(self, source_path, target_path):
        print(f'rencoding {source_path} to {target_path}')
        # Load the source audio file
        source_audio = AudioSegment.from_file(source_path)

        # Export the audio in the target format
        source_audio.export(target_path, format=self.target_format)

    def handle_error(self, error_message):
        traceback.print_exc()
        self.error.emit(error_message)