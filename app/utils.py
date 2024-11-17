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


def language_to_iso(language_name):
    """
    Convert a fully spelled-out language name to its ISO 639-1 code.

    Args:
        language_name (str): The full name of the language (e.g., "English").

    Returns:
        str: The ISO 639-1 code (e.g., "en") or None if the language is not recognized.
    """
    language_map = {
        "Afrikaans": "af",
        "Albanian": "sq",
        "Arabic": "ar",
        "Armenian": "hy",
        "Bengali": "bn",
        "Bosnian": "bs",
        "Bulgarian": "bg",
        "Catalan": "ca",
        "Chinese": "zh",
        "Croatian": "hr",
        "Czech": "cs",
        "Danish": "da",
        "Dutch": "nl",
        "English": "en",
        "Estonian": "et",
        "Finnish": "fi",
        "French": "fr",
        "Georgian": "ka",
        "German": "de",
        "Greek": "el",
        "Hebrew": "he",
        "Hindi": "hi",
        "Hungarian": "hu",
        "Icelandic": "is",
        "Indonesian": "id",
        "Italian": "it",
        "Japanese": "ja",
        "Kazakh": "kk",
        "Korean": "ko",
        "Latvian": "lv",
        "Lithuanian": "lt",
        "Macedonian": "mk",
        "Malay": "ms",
        "Mongolian": "mn",
        "Norwegian": "no",
        "Persian": "fa",
        "Polish": "pl",
        "Portuguese": "pt",
        "Romanian": "ro",
        "Russian": "ru",
        "Serbian": "sr",
        "Slovak": "sk",
        "Slovenian": "sl",
        "Spanish": "es",
        "Swahili": "sw",
        "Swedish": "sv",
        "Thai": "th",
        "Turkish": "tr",
        "Ukrainian": "uk",
        "Urdu": "ur",
        "Vietnamese": "vi",
        "Welsh": "cy",
    }

    return language_map.get(language_name.strip().title())

