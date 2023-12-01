import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal,Qt
import traceback

class YouTub2eDownloadThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    temp_file_created = pyqtSignal(str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.youtube_url = None  # Initialize youtube_url to None

    def run(self):
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'outtmpl': 'downloaded_audio.%(ext)s',
                'quiet': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.youtube_url])
            self.update_progress.emit('YouTube Download Complete.')
            self.completed.emit('downloaded_audio.wav')
            self.temp_file_created.emit('downloaded_audio.wav')
        except Exception as e:
            error_message = str(e)
            self.error.emit(error_message)
            print('Error occurred:', error_message)
            print(traceback.format_exc())
    def set_youtube_url(self, url):
        self.youtube_url = url