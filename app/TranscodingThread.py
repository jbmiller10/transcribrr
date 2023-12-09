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
            target_file_path = self.reencode_audio(self.file_path, self.target_format)

            # Delete the original file after successful conversion
            if os.path.exists(target_file_path):
                os.remove(self.file_path)

            self.completed.emit(target_file_path)
            self.update_progress.emit('Conversion completed.')
        except Exception as e:
            error_message = f'Error during conversion: {e}'
            self.handle_error(error_message)

    def reencode_audio(self, file_path, target_format):
        print(f'rencoding {file_path} to {target_format}')
        # Determine the target file path based on the desired format
        target_file_path = os.path.splitext(file_path)[0] + f'.{target_format}'

        # Load the source audio file
        source_audio = AudioSegment.from_file(file_path)

        # Export the audio in the target format
        source_audio.export(target_file_path, format=target_format)
        return target_file_path

    def handle_error(self, error_message):
        traceback.print_exc()
        self.error.emit(error_message)