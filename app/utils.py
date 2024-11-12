import os
import re
import sys

def is_video_file(file_path):
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm']
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in video_extensions


def is_audio_file(file_path):
    audio_extensions = ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a']
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in audio_extensions

def validate_url(url):
    # Use regex to validate the URL
    regex = r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    return re.match(regex, url) is not None


def resource_path(relative_path, root=False):
    try:
        base_path = sys._MEIPASS
    except Exception:
        if root:
            base_path = os.path.abspath("")
        else:
            base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

