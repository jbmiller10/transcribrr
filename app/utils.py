import os
import re
import sys
import logging
import platform
import subprocess
import torch
import shutil
import json
from typing import Dict, Any, Optional, List, Union, Tuple
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.getcwd(), 'transcribrr.log'))
    ]
)

logger = logging.getLogger('transcribrr')


def is_video_file(file_path):
    """Check if a file is a video file based on its extension."""
    video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv']
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in video_extensions


def is_audio_file(file_path):
    """Check if a file is an audio file based on its extension."""
    audio_extensions = ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.aiff', '.wma']
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in audio_extensions


def validate_url(url):
    """Validate if a URL is a valid YouTube URL."""
    # Modified regex pattern to handle more YouTube URL formats
    youtube_regex = r'(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|embed\/|v\/|shorts\/)?([^\s&?\/\#]+)'
    match = re.match(youtube_regex, url)
    return bool(match)


def resource_path(relative_path, root=False):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
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
        "Amharic": "am",
        "Arabic": "ar",
        "Armenian": "hy",
        "Azerbaijani": "az",
        "Basque": "eu",
        "Belarusian": "be",
        "Bengali": "bn",
        "Bosnian": "bs",
        "Bulgarian": "bg",
        "Catalan": "ca",
        "Cebuano": "ceb",
        "Chinese": "zh",
        "Corsican": "co",
        "Croatian": "hr",
        "Czech": "cs",
        "Danish": "da",
        "Dutch": "nl",
        "English": "en",
        "Esperanto": "eo",
        "Estonian": "et",
        "Finnish": "fi",
        "French": "fr",
        "Frisian": "fy",
        "Galician": "gl",
        "Georgian": "ka",
        "German": "de",
        "Greek": "el",
        "Gujarati": "gu",
        "Haitian Creole": "ht",
        "Hausa": "ha",
        "Hawaiian": "haw",
        "Hebrew": "he",
        "Hindi": "hi",
        "Hmong": "hmn",
        "Hungarian": "hu",
        "Icelandic": "is",
        "Igbo": "ig",
        "Indonesian": "id",
        "Irish": "ga",
        "Italian": "it",
        "Japanese": "ja",
        "Javanese": "jv",
        "Kannada": "kn",
        "Kazakh": "kk",
        "Khmer": "km",
        "Korean": "ko",
        "Kurdish": "ku",
        "Kyrgyz": "ky",
        "Lao": "lo",
        "Latin": "la",
        "Latvian": "lv",
        "Lithuanian": "lt",
        "Luxembourgish": "lb",
        "Macedonian": "mk",
        "Malagasy": "mg",
        "Malay": "ms",
        "Malayalam": "ml",
        "Maltese": "mt",
        "Maori": "mi",
        "Marathi": "mr",
        "Mongolian": "mn",
        "Myanmar": "my",
        "Nepali": "ne",
        "Norwegian": "no",
        "Nyanja": "ny",
        "Pashto": "ps",
        "Persian": "fa",
        "Polish": "pl",
        "Portuguese": "pt",
        "Punjabi": "pa",
        "Romanian": "ro",
        "Russian": "ru",
        "Samoan": "sm",
        "Scots Gaelic": "gd",
        "Serbian": "sr",
        "Sesotho": "st",
        "Shona": "sn",
        "Sindhi": "sd",
        "Sinhala": "si",
        "Slovak": "sk",
        "Slovenian": "sl",
        "Somali": "so",
        "Spanish": "es",
        "Sundanese": "su",
        "Swahili": "sw",
        "Swedish": "sv",
        "Tagalog": "tl",
        "Tajik": "tg",
        "Tamil": "ta",
        "Telugu": "te",
        "Thai": "th",
        "Turkish": "tr",
        "Ukrainian": "uk",
        "Urdu": "ur",
        "Uzbek": "uz",
        "Vietnamese": "vi",
        "Welsh": "cy",
        "Xhosa": "xh",
        "Yiddish": "yi",
        "Yoruba": "yo",
        "Zulu": "zu"
    }

    # Normalize input by capitalizing the first letter and lowercase the rest
    normalized_name = language_name.strip().title()

    return language_map.get(normalized_name, "en")  # Default to English if not found


def create_backup(file_path, backup_dir=None):
    """
    Create a backup of a file.

    Args:
        file_path (str): Path to the file to backup
        backup_dir (str, optional): Directory to store backups. Defaults to 'backups'.

    Returns:
        str: Path to the backup file, or None if backup failed
    """
    if not os.path.exists(file_path):
        logger.warning(f"Cannot backup non-existent file: {file_path}")
        return None

    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(file_path), 'backups')

    try:
        # Create backup directory if it doesn't exist
        os.makedirs(backup_dir, exist_ok=True)

        # Create backup filename with timestamp
        file_name = os.path.basename(file_path)
        backup_name = f"{os.path.splitext(file_name)[0]}_{get_timestamp()}{os.path.splitext(file_name)[1]}"
        backup_path = os.path.join(backup_dir, backup_name)

        # Copy the file
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")

        return backup_path
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None


def get_timestamp():
    """Get a timestamp string for filenames."""
    import datetime
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def check_ffmpeg():
    """Check if FFmpeg is installed and accessible."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_system_requirements():
    """
    Check system requirements for running the application.

    Returns:
        dict: System requirements check results
    """
    results = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": platform.python_version(),
        "ffmpeg_installed": check_ffmpeg(),
        "cuda_available": torch.cuda.is_available(),
        "gpu_info": None,
        "mps_available": hasattr(torch.backends, 'mps') and torch.backends.mps.is_available(),
        "issues": []
    }

    # Check Python version
    if sys.version_info < (3, 10):
        results["issues"].append("Python 3.10+ is recommended for optimal performance")

    # Check GPU info if CUDA is available
    if results["cuda_available"]:
        try:
            gpu_count = torch.cuda.device_count()
            gpu_info = []
            for i in range(gpu_count):
                name = torch.cuda.get_device_name(i)
                memory = torch.cuda.get_device_properties(i).total_memory / (1024 ** 3)  # Convert to GB
                gpu_info.append({"index": i, "name": name, "memory": f"{memory:.2f} GB"})
            results["gpu_info"] = gpu_info
        except Exception as e:
            logger.error(f"Error getting GPU info: {e}")
            results["issues"].append(f"Error accessing GPU information: {e}")
    else:
        results["issues"].append("CUDA not available - some features may be slower")

    # Check FFmpeg
    if not results["ffmpeg_installed"]:
        results["issues"].append("FFmpeg not found - required for audio/video processing")

    return results


def format_time_duration(seconds):
    """
    Format seconds into a human-readable time duration.

    Args:
        seconds (float): Time in seconds

    Returns:
        str: Formatted time duration (HH:MM:SS)
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def show_system_info(parent=None):
    """
    Display system information in a message box.

    Args:
        parent: Parent widget for QMessageBox
    """
    info = check_system_requirements()

    # Format the message
    message = "System Information:\n\n"
    message += f"Operating System: {info['os']} {info['os_version']}\n"
    message += f"Python Version: {info['python_version']}\n"
    message += f"FFmpeg Installed: {'Yes' if info['ffmpeg_installed'] else 'No'}\n"
    message += f"CUDA Available: {'Yes' if info['cuda_available'] else 'No'}\n"
    message += f"MPS Available: {'Yes' if info['mps_available'] else 'No'}\n\n"

    if info['gpu_info']:
        message += "GPU Information:\n"
        for gpu in info['gpu_info']:
            message += f"  • {gpu['name']} ({gpu['memory']})\n"
    else:
        message += "No GPU information available\n"

    if info['issues']:
        message += "\nPotential Issues:\n"
        for issue in info['issues']:
            message += f"  • {issue}\n"

    # Show the message box
    if parent:
        QMessageBox.information(parent, "System Information", message)
    else:
        print(message)

    return message


def cleanup_temp_files(directory=None, file_pattern=None, max_age_days=7):
    """
    Clean up temporary files based on pattern and age.

    Args:
        directory (str, optional): Directory to clean. Defaults to temp directory.
        file_pattern (str, optional): File pattern to match. Defaults to all files.
        max_age_days (int, optional): Maximum age in days. Defaults to 7.

    Returns:
        int: Number of files deleted
    """
    import tempfile
    import glob
    import time

    if directory is None:
        directory = tempfile.gettempdir()

    if file_pattern is None:
        file_pattern = "*"

    pattern = os.path.join(directory, file_pattern)
    files = glob.glob(pattern)

    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60

    deleted_count = 0

    for file_path in files:
        try:
            if os.path.isfile(file_path):
                file_age = current_time - os.path.getmtime(file_path)
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.debug(f"Deleted temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Error deleting temp file {file_path}: {e}")

    logger.info(f"Cleaned up {deleted_count} temporary files")
    return deleted_count


class ConfigManager(QObject):
    """Centralized configuration management for the application."""
    
    config_updated = pyqtSignal(dict)
    
    _instance = None
    
    @classmethod
    def instance(cls) -> 'ConfigManager':
        """Get the singleton instance of ConfigManager."""
        if cls._instance is None:
            cls._instance = ConfigManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the configuration manager."""
        super().__init__()
        self._config: Dict[str, Any] = {}
        self._config_path = resource_path('config.json')
        self._load_config()
        
    def _load_config(self) -> None:
        """Load configuration from config.json file."""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r') as config_file:
                    self._config = json.load(config_file)
                logger.info("Configuration loaded successfully")
            else:
                logger.warning("Config file not found, creating default")
                self._create_default_config()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._create_default_config()
            
    def _create_default_config(self) -> None:
        """Create default configuration file."""
        self._config = {
            "transcription_quality": "openai/whisper-large-v3",
            "transcription_method": "local",
            "gpt_model": "gpt-4o",
            "max_tokens": 16000,
            "temperature": 1.0,
            "speaker_detection_enabled": False,
            "transcription_language": "english",
            "theme": "light",
            "chunk_enabled": True,
            "chunk_duration": 5
        }
        self._save_config()
        
    def _save_config(self) -> None:
        """Save configuration to config.json file."""
        try:
            with open(self._config_path, 'w') as config_file:
                json.dump(self._config, config_file, indent=4)
            logger.info("Configuration saved successfully")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key: The configuration key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            The configuration value or default
        """
        return self._config.get(key, default)
        
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            key: The configuration key to set
            value: The value to set
        """
        if key in self._config and self._config[key] == value:
            return  # No change, don't emit signal
            
        self._config[key] = value
        self._save_config()
        self.config_updated.emit(self._config)
        
    def update(self, config_dict: Dict[str, Any]) -> None:
        """
        Update multiple configuration values at once.
        
        Args:
            config_dict: Dictionary of configuration key-value pairs to update
        """
        changed = False
        for key, value in config_dict.items():
            if key not in self._config or self._config[key] != value:
                self._config[key] = value
                changed = True
                
        if changed:
            self._save_config()
            self.config_updated.emit(self._config)
            
    def get_all(self) -> Dict[str, Any]:
        """
        Get the entire configuration dictionary.
        
        Returns:
            A copy of the configuration dictionary
        """
        return self._config.copy()
    
    def create_backup(self) -> Optional[str]:
        """
        Create a backup of the current configuration.
        
        Returns:
            Path to the backup file or None if failed
        """
        return create_backup(self._config_path)


def estimate_transcription_time(file_path: str, model_name: str, is_gpu: bool = False) -> Optional[int]:
    """
    Estimate transcription time based on file size and model.

    Args:
        file_path: Path to audio file
        model_name: Name of the model
        is_gpu: Whether GPU acceleration is available

    Returns:
        Estimated time in seconds
    """
    if not os.path.exists(file_path):
        return None

    # Get file size in MB
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)

    # Base processing speed in MB per second for different models
    # These are rough estimates and can be adjusted
    model_speeds = {
        "tiny": 1.5,
        "base": 1.0,
        "small": 0.8,
        "medium": 0.5,
        "large": 0.3,
        "distil-small": 1.2,
        "distil-medium": 0.7,
        "distil-large": 0.4
    }

    # Extract model size from name
    model_size = None
    for size in model_speeds.keys():
        if size in model_name.lower():
            model_size = size
            break

    if model_size is None:
        model_size = "medium"  # Default to medium if not recognized

    # Get base speed
    base_speed = model_speeds[model_size]

    # Adjust for GPU acceleration
    if is_gpu:
        base_speed *= 3  # GPU is roughly 3x faster

    # Calculate estimated time in seconds
    estimated_time = file_size_mb / base_speed

    # Add overhead time (loading model, etc.)
    overhead = 10  # seconds
    estimated_time += overhead

    return max(int(estimated_time), 1)  # Ensure at least 1 second