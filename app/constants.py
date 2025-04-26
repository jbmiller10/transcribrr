"""Application constants."""

import os
from typing import Dict, List, Set
from enum import Enum, auto
from .path_utils import resource_path

APP_NAME = "Transcribrr"
APP_VERSION = "1.0.0"
APP_AUTHOR = "John Miller"

# Use the consolidated resource_path function
RESOURCE_DIR = resource_path()  # Read-only bundled resources
# USER_DATA_DIR is determined at runtime via get_user_data_dir()

ICONS_DIR = os.path.join(RESOURCE_DIR, "icons")

# Path constants are now provided via runtime functions

# --- Path Retrieval Functions ---

_USER_DATA_DIR_CACHE = None

def get_user_data_dir() -> str:
    """Gets the user-specific data directory, caching the result."""
    global _USER_DATA_DIR_CACHE
    if _USER_DATA_DIR_CACHE is None:
        import sys
        import os

        APP_NAME_CONST = "Transcribrr"
        APP_AUTHOR_CONST = "John Miller"

        if "TRANSCRIBRR_USER_DATA_DIR" in os.environ:
            _USER_DATA_DIR_CACHE = os.environ["TRANSCRIBRR_USER_DATA_DIR"]
        elif hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
            import appdirs
            _USER_DATA_DIR_CACHE = appdirs.user_data_dir(APP_NAME_CONST, APP_AUTHOR_CONST)
        else:
            _USER_DATA_DIR_CACHE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return _USER_DATA_DIR_CACHE

def get_recordings_dir() -> str:
    return os.path.join(get_user_data_dir(), "Recordings")

def get_database_dir() -> str:
    return os.path.join(get_user_data_dir(), "database")

def get_database_path() -> str:
    return os.path.join(get_database_dir(), "database.sqlite")

def get_config_path() -> str:
    return os.path.join(get_user_data_dir(), "config.json")

def get_prompts_path() -> str:
    return os.path.join(get_user_data_dir(), "preset_prompts.json")

def get_log_dir() -> str:
    return os.path.join(get_user_data_dir(), "logs")

def get_log_file() -> str:
    return os.path.join(get_log_dir(), "transcribrr.log")

# Directories are now created explicitly during app startup in __main__.py
# os.makedirs(RECORDINGS_DIR, exist_ok=True)
# os.makedirs(DATABASE_DIR, exist_ok=True)
# os.makedirs(LOG_DIR, exist_ok=True)

TABLE_RECORDINGS = "recordings"
FIELD_ID = "id"
FIELD_FILENAME = "filename"
FIELD_FILE_PATH = "file_path"
FIELD_DATE_CREATED = "date_created"
FIELD_DURATION = "duration"
FIELD_RAW_TRANSCRIPT = "raw_transcript"
FIELD_PROCESSED_TEXT = "processed_text"
FIELD_RAW_TRANSCRIPT_FORMATTED = "raw_transcript_formatted"
FIELD_PROCESSED_TEXT_FORMATTED = "processed_text_formatted"

class FileType(Enum):
    """Supported file type enum."""
    AUDIO = auto()
    VIDEO = auto()
    DOCUMENT = auto()
    UNKNOWN = auto()
    
AUDIO_EXTENSIONS: Set[str] = {
    '.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.aiff', '.wma'
}

VIDEO_EXTENSIONS: Set[str] = {
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv'
}

DOCUMENT_EXTENSIONS: Set[str] = {
    '.txt', '.md', '.doc', '.docx', '.pdf', '.odt'
}

FILE_TYPES: Dict[str, Dict[str, str]] = {
    # Audio formats
    '.mp3': {'name': 'MPEG Audio Layer III', 'type': FileType.AUDIO},
    '.wav': {'name': 'Waveform Audio File Format', 'type': FileType.AUDIO},
    '.m4a': {'name': 'MPEG-4 Audio', 'type': FileType.AUDIO},
    '.ogg': {'name': 'Ogg Vorbis Audio', 'type': FileType.AUDIO},
    '.flac': {'name': 'Free Lossless Audio Codec', 'type': FileType.AUDIO},
    '.aac': {'name': 'Advanced Audio Coding', 'type': FileType.AUDIO},
    '.aiff': {'name': 'Audio Interchange File Format', 'type': FileType.AUDIO},
    '.wma': {'name': 'Windows Media Audio', 'type': FileType.AUDIO},
    
    # Video formats
    '.mp4': {'name': 'MPEG-4 Video', 'type': FileType.VIDEO},
    '.mkv': {'name': 'Matroska Video', 'type': FileType.VIDEO},
    '.avi': {'name': 'Audio Video Interleave', 'type': FileType.VIDEO},
    '.mov': {'name': 'QuickTime Movie', 'type': FileType.VIDEO},
    '.webm': {'name': 'WebM Video', 'type': FileType.VIDEO},
    '.flv': {'name': 'Flash Video', 'type': FileType.VIDEO},
    '.wmv': {'name': 'Windows Media Video', 'type': FileType.VIDEO},
    
    # Document formats
    '.txt': {'name': 'Plain Text', 'type': FileType.DOCUMENT},
    '.md': {'name': 'Markdown', 'type': FileType.DOCUMENT},
    '.doc': {'name': 'Microsoft Word Document', 'type': FileType.DOCUMENT},
    '.docx': {'name': 'Microsoft Word Document (XML)', 'type': FileType.DOCUMENT},
    '.pdf': {'name': 'Portable Document Format', 'type': FileType.DOCUMENT},
    '.odt': {'name': 'OpenDocument Text', 'type': FileType.DOCUMENT},
}

DEFAULT_CONFIG = {
    "transcription_quality": "openai/whisper-large-v3",
    "transcription_method": "local",
    "gpt_model": "gpt-4o",
    "max_tokens": 16000,
    "temperature": 1.0,
    "speaker_detection_enabled": False,
    "transcription_language": "english",
    "theme": "light",
    "hardware_acceleration_enabled": True
}

DEFAULT_PROMPTS = {
    "Youtube to article": {
        "text": "Transform this raw transcript of a youtube video into a well-structured article, maintaining as much detail as possible. Do not embellish by adding details not mentioned. It is extremely important you keep all details. Your output should come close to matching the number of words of the original transcript.",
        "category": "Formatting"
    },
    "Translate": {
        "text": "Translate this raw audio transcript into English. You may fix minor transcription errors based on context.",
        "category": "Translation"
    },
    "Journal Entry Formatting": {
        "text": "Format this raw audio transcript into a clean, coherent journal entry, maintaining a first-person narrative style.",
        "category": "Formatting"
    },
    "Meeting Minutes": {
        "text": "Convert this transcript into a structured format of meeting minutes, highlighting key points, decisions made, and action items.",
        "category": "Summarization"
    },
    "Stream of Consciousness": {
        "text": "Organize the ideas in this raw transcript of a stream of consciousness brainstorm in order to capture all key points in a comprehensive and thorough manner.",
        "category": "Organization"
    }
}

WHISPER_CHUNK_LENGTH = 30  # seconds
MIN_AUDIO_LENGTH = 0.5  # seconds
MAX_FILE_SIZE_MB = 300  # MB

DEFAULT_FONT_FAMILY = "Arial"
DEFAULT_FONT_SIZE = 12
TEXT_EDITOR_MIN_HEIGHT = 200

ERROR_DATABASE_CONNECTION = "Could not connect to the database."
ERROR_INVALID_FILE = "The selected file format is not supported."
ERROR_FILE_TOO_LARGE = "The selected file is too large to process."
ERROR_API_CONNECTION = "Could not connect to API. Please check your internet connection."
ERROR_API_KEY_MISSING = "API key is missing. Please add your API key in settings."

SUCCESS_TRANSCRIPTION = "Audio transcription completed successfully."
SUCCESS_GPT_PROCESSING = "GPT processing completed successfully."
SUCCESS_SAVE = "File saved successfully."

# Log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'