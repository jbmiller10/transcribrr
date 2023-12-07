import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal,Qt
import traceback
from datetime import datetime
import os

class YouTubeDownloadThread(QThread):
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, youtube_url, *args, **kwargs):
        super(YouTubeDownloadThread, self).__init__(*args, **kwargs)
        self.youtube_url = youtube_url

    def run(self):
        try:
            # Define the output template for the downloaded audio file
            output_template = os.path.join(
                'recordings',  # Ensure this directory exists or is created before downloading
                f'downloaded_audio_{datetime.now().strftime("%Y%m%d_%H%M%S")}.%(ext)s'
            )

            # Setup yt_dlp options
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav',
                    'preferredquality': '192',
                }],
                'outtmpl': output_template,
                'quiet': True
            }

            # Perform the download
            # Perform the download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.youtube_url, download=True)
                audio_file_path = ydl.prepare_filename(info)
                # Assuming the postprocessor renames the file to '.wav'
                audio_file_path = audio_file_path.rsplit('.', 1)[0] + '.wav'
                self.completed.emit(audio_file_path)  # Emit the path of the saved audio file
        except Exception as e:
            self.error.emit(str(e))

    def set_youtube_url(self, url):
        self.youtube_url = url