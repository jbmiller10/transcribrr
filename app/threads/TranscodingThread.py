from PyQt6.QtCore import QThread, pyqtSignal
from pydub import AudioSegment
import os
from moviepy.editor import VideoFileClip
import traceback
from app.utils import is_video_file, is_audio_file

class TranscodingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, file_path=None, target_format='mp3', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.target_format = target_format
        self.recordings_dir = 'Recordings'  # Directory for storing the output

    def run(self):
        try:
            if is_audio_file(self.file_path):
                self.update_progress.emit('Transcoding audio file...')
                self.transcode_audio(self.file_path, self.recordings_dir)
            elif is_video_file(self.file_path):
                self.update_progress.emit('Extracting audio from video file...')
                self.extract_audio_from_video(self.file_path, self.recordings_dir)
            else:
                raise ValueError("Unsupported file type")
        except Exception as e:
            error_message = f'Error: {e}'
            self.handle_error(error_message)

    def transcode_audio(self, source_path, target_dir):
        self.update_progress.emit('Transcoding audio file...')
        target_file_path = self.generate_unique_target_path(target_dir, self.target_format)
        self.reencode_audio(source_path, target_file_path)
        if os.path.exists(target_file_path):
            os.remove(source_path)
        self.completed.emit(target_file_path)


    def extract_audio_from_video(self, video_path, target_dir):
        self.update_progress.emit('Extracting audio from video file...')
        with VideoFileClip(video_path) as video:
            audio_path = self.generate_unique_target_path(target_dir, 'mp3', audio_only=True)
            video.audio.write_audiofile(audio_path)
        if os.path.exists(audio_path):
            os.remove(video_path)
        print(audio_path)
        self.completed.emit(audio_path)

    def generate_unique_target_path(self, target_dir, target_format, audio_only=False):
        base_name = os.path.basename(self.file_path)
        name, _ = os.path.splitext(base_name)
        if audio_only:
            name += "_extracted_audio"
        counter = 1
        target_file_path = os.path.join(target_dir, f"{name}.{target_format}")
        while os.path.exists(target_file_path):
            target_file_path = os.path.join(target_dir, f"{name}_{counter}.{target_format}")
            counter += 1
        return target_file_path

        return target_file_path

    def reencode_audio(self, source_path, target_path):
        self.update_progress.emit('Transcoding audio file...')
        source_audio = AudioSegment.from_file(source_path)
        source_audio.export(target_path, format=self.target_format)


    def handle_error(self, error_message):
        traceback.print_exc()
        self.error.emit(error_message)