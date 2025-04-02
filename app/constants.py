"""
Central location for application constants to avoid duplication and ensure consistency.
"""

import os
import sys
import appdirs
from typing import Dict, List, Set
from enum import Enum, auto

# Application information
APP_NAME = "Transcribrr"
APP_VERSION = "1.0.0"
APP_AUTHOR = "John Miller"

# Determine base paths: differentiate between resource path and user data path
def get_resource_path():
    """Get the path for read-only resources bundled with the app"""
    try:
        # Check if running as PyInstaller bundle
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        
        # Check if running as a py2app bundle
        elif getattr(sys, 'frozen', False) and 'MacOS' in sys.executable:
            bundle_dir = os.path.normpath(os.path.join(
                os.path.dirname(sys.executable), 
                os.pardir, 'Resources'
            ))
            return bundle_dir
        
    except AttributeError:
        pass
    
    # Not running as bundled app, use current working directory
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_user_data_path():
    """Get the path for user data files that need to be read/write"""
    # When packaged, we need to use the user's data directory
    if hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False):
        # Use appdirs to get standard user data directory
        user_data_dir = appdirs.user_data_dir(APP_NAME, APP_AUTHOR)
        # Create the directory if it doesn't exist
        os.makedirs(user_data_dir, exist_ok=True)
        return user_data_dir
    else:
        # In development mode, use the project directory
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Base directories
RESOURCE_DIR = get_resource_path()  # Read-only bundled resources
USER_DATA_DIR = get_user_data_path()  # Read-write user data

# File paths for read-only resources
ICONS_DIR = os.path.join(RESOURCE_DIR, "icons")

# File paths for user data (read-write)
RECORDINGS_DIR = os.path.join(USER_DATA_DIR, "Recordings")
DATABASE_DIR = os.path.join(USER_DATA_DIR, "database")
DATABASE_PATH = os.path.join(DATABASE_DIR, "database.sqlite")
CONFIG_PATH = os.path.join(USER_DATA_DIR, "config.json")
PROMPTS_PATH = os.path.join(USER_DATA_DIR, "preset_prompts.json")
LOG_DIR = os.path.join(USER_DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "transcribrr.log")

# Ensure user data directories exist
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Database table names and fields
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

# File types
class FileType(Enum):
    """Enum for file types supported by the application."""
    AUDIO = auto()
    VIDEO = auto()
    DOCUMENT = auto()
    UNKNOWN = auto()
    
# Supported file extensions
AUDIO_EXTENSIONS: Set[str] = {
    '.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.aiff', '.wma'
}

VIDEO_EXTENSIONS: Set[str] = {
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv'
}

DOCUMENT_EXTENSIONS: Set[str] = {
    '.txt', '.md', '.doc', '.docx', '.pdf', '.odt'
}

# Maps file extensions to their display names and types
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

# Default configuration values
DEFAULT_CONFIG = {
    "transcription_quality": "openai/whisper-large-v3",
    "transcription_method": "local",
    "gpt_model": "gpt-4o",
    "max_tokens": 16000,
    "temperature": 1.0,
    "speaker_detection_enabled": False,
    "transcription_language": "english",
    "theme": "light",
    "chunk_enabled": True,
    "chunk_duration": 5,
    "hardware_acceleration_enabled": True
}

# Default prompt templates
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

# Transcription settings
WHISPER_CHUNK_LENGTH = 30  # seconds
MIN_AUDIO_LENGTH = 0.5  # seconds
MAX_FILE_SIZE_MB = 300  # MB

# UI constants
DEFAULT_FONT_FAMILY = "Arial"
DEFAULT_FONT_SIZE = 12
TEXT_EDITOR_MIN_HEIGHT = 200

# Error messages
ERROR_DATABASE_CONNECTION = "Could not connect to the database."
ERROR_INVALID_FILE = "The selected file format is not supported."
ERROR_FILE_TOO_LARGE = "The selected file is too large to process."
ERROR_API_CONNECTION = "Could not connect to API. Please check your internet connection."
ERROR_API_KEY_MISSING = "API key is missing. Please add your API key in settings."

# Success messages
SUCCESS_TRANSCRIPTION = "Audio transcription completed successfully."
SUCCESS_GPT_PROCESSING = "GPT processing completed successfully."
SUCCESS_SAVE = "File saved successfully."

# Log format
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'