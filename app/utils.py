from .path_utils import resource_path
from logging.handlers import RotatingFileHandler
import os
import re
import sys
import logging
import platform
import subprocess
# Torch may not be available or may lack certain submodules in CPU-only builds.
# Provide a resilient shim to keep tests import-safe and patchable.
try:  # pragma: no cover - behavior validated by higher-level tests
    import torch as _torch  # type: ignore
except Exception:  # torch not installed
    import types as _types  # lazy import for shim

    class _CudaShim:
        def is_available(self):
            return False

        def device_count(self):
            return 0

        def get_device_name(self, idx):  # noqa: ARG002
            return f"GPU{idx}"

        def get_device_properties(self, idx):  # noqa: ARG002
            return _types.SimpleNamespace(total_memory=0)

    _torch = _types.SimpleNamespace(  # type: ignore
        cuda=_CudaShim(),
        backends=_types.SimpleNamespace(
            mps=_types.SimpleNamespace(is_available=lambda: False)
        ),
    )
else:
    # Ensure 'cuda' and 'backends.mps' exist for patching/tests
    import types as _types

    if not hasattr(_torch, "cuda"):
        class _CudaShim:
            def is_available(self):
                return False

            def device_count(self):
                return 0

            def get_device_name(self, idx):  # noqa: ARG002
                return f"GPU{idx}"

            def get_device_properties(self, idx):  # noqa: ARG002
                return _types.SimpleNamespace(total_memory=0)

        _torch.cuda = _CudaShim()  # type: ignore

    # backends may exist without mps; add if missing
    if not hasattr(_torch, "backends"):
        _torch.backends = _types.SimpleNamespace()  # type: ignore
    if not hasattr(_torch.backends, "mps"):
        _torch.backends.mps = _types.SimpleNamespace(is_available=lambda: False)  # type: ignore

# Expose as 'torch' for module consumers
torch = _torch  # type: ignore
import shutil
import json
from typing import Dict, Any, Optional, Union, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
import datetime

# Assuming constants.py is in the same directory or accessible via path
from .constants import (
    APP_NAME,
    DEFAULT_CONFIG,
    DEFAULT_PROMPTS,
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    get_config_path,
    get_prompts_path,
    get_log_dir,
    get_log_file,
)

# Configure logging
# Ensure log directory exists
os.makedirs(get_log_dir(), exist_ok=True)
# Configure logging once, using a rotating file handler to avoid unbounded
# growth of the log file.  If another module (e.g. main.py) re‑configures
# logging later this block will silently be ignored thanks to the `force`
# parameter defaulting to *False* in older Python versions.


if not logging.getLogger().handlers:
    max_bytes = 5 * 1024 * 1024  # 5 MB per log file
    backup_count = 3  # keep up to 15 MB total

    rotating_handler = RotatingFileHandler(
        get_log_file(),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        handlers=[logging.StreamHandler(), rotating_handler],
    )

# Use app name for logger consistently
logger = logging.getLogger(APP_NAME)


def is_video_file(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in VIDEO_EXTENSIONS


def is_audio_file(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()
    return file_extension in AUDIO_EXTENSIONS


def ensure_ffmpeg_available():
    logger = logging.getLogger("transcribrr")

    # Check if we're running in a bundled app
    is_bundled = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

    # Potential locations for ffmpeg
    potential_locations = [
        # Check in PATH first
        shutil.which("ffmpeg"),
        # Check bundled binary (MacOS app)
        os.path.join(os.path.dirname(sys.executable), "bin", "ffmpeg"),
        # Check one directory up in case we're in MacOS/bin structure
        os.path.join(os.path.dirname(
            os.path.dirname(sys.executable)), "bin", "ffmpeg"),
        # Check Resources directory for bundled app
        resource_path("ffmpeg"),
        # Custom common locations
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]

    # Log the locations we're checking
    logger.info(f"Checking for ffmpeg in: {potential_locations}")

    # Check each potential location
    for location in potential_locations:
        if location and os.path.exists(location) and os.access(location, os.X_OK):
            logger.info(f"Found ffmpeg at: {location}")

            # Add the directory to PATH if it's not already there
            ffmpeg_dir = os.path.dirname(location)
            if ffmpeg_dir not in os.environ.get("PATH", ""):
                logger.info(f"Adding {ffmpeg_dir} to PATH")
                os.environ["PATH"] = (
                    f"{ffmpeg_dir}{os.pathsep}{os.environ.get('PATH', '')}"
                )

            # Try running ffmpeg to verify it works
            try:
                result = subprocess.run(
                    [location, "-version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=5,
                )
                if result.returncode == 0:
                    logger.info(
                        f"Successfully verified ffmpeg: {result.stdout.decode()[:100]}..."
                    )
                    return True, f"Found ffmpeg at {location}"
            except Exception as e:
                logger.warning(
                    f"Found ffmpeg at {location} but executing it failed: {e}"
                )

    logger.error("Could not find ffmpeg in any of the expected locations")
    return (
        False,
        "FFmpeg not found. Please install FFmpeg to enable audio/video processing.",
    )


def validate_url(url):
    """Return True if YouTube URL."""
    # Modified regex pattern to handle more YouTube URL formats
    # More specific video ID
    youtube_regex = r"(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=|embed\/|v\/|shorts\/)?([a-zA-Z0-9_-]{11})"
    # search() instead of match() so the pattern can appear anywhere in the URL
    return re.search(youtube_regex, url) is not None


# Moved to path_utils.py


def language_to_iso(language_name):
    """Convert language name to ISO code."""
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
        "Kinyarwanda": "rw",
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
        "Oriya": "or",
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
        "Tatar": "tt",
        "Telugu": "te",
        "Thai": "th",
        "Turkish": "tr",
        "Turkmen": "tk",
        "Ukrainian": "uk",
        "Urdu": "ur",
        "Uyghur": "ug",
        "Uzbek": "uz",
        "Vietnamese": "vi",
        "Welsh": "cy",
        "Xhosa": "xh",
        "Yiddish": "yi",
        "Yoruba": "yo",
        "Zulu": "zu",
    }
    normalized_name = language_name.strip().title()
    return language_map.get(normalized_name, "en")  # Default to English


def create_backup(file_path: str, backup_dir: Optional[str] = None) -> Optional[str]:
    """Create a timestamped backup of a file."""
    if not os.path.exists(file_path):
        logger.warning(f"Cannot backup non-existent file: {file_path}")
        return None

    if backup_dir is None:
        backup_dir = os.path.join(os.path.dirname(file_path), "backups")

    try:
        os.makedirs(backup_dir, exist_ok=True)
        file_name = os.path.basename(file_path)
        name, ext = os.path.splitext(file_name)
        backup_name = f"{name}_{get_timestamp()}{ext}"
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(file_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Backup failed for {file_path}: {e}", exc_info=True)
        return None


def get_timestamp():
    """Get a timestamp string formatted as YYYYMMDD_HHMMSS."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def check_ffmpeg():
    """Check if FFmpeg is installed and accessible."""
    try:
        # Use startupinfo for cleaner execution on Windows
        startupinfo = None
        if platform.system() == "Windows":
            # Windows-specific imports
            import ctypes
            # On Windows, subprocess has these attributes at runtime
            # For type checking, we'll ignore mypy errors here
            startupinfo = subprocess.STARTUPINFO()  # type: ignore
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore
            startupinfo.wShowWindow = 0  # SW_HIDE

        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=False,
            startupinfo=startupinfo,  # Pass startupinfo
        )
        if result.returncode == 0 and "ffmpeg version" in result.stdout.lower():
            logger.info("FFmpeg found and accessible.")
            return True
        else:
            logger.warning(
                f"FFmpeg check failed. Return code: {result.returncode}. Stdout: {result.stdout[:100]}..."
            )
            return False
    except FileNotFoundError:
        logger.error(
            "FFmpeg command not found. Please ensure FFmpeg is installed and in your system's PATH."
        )
        return False
    except Exception as e:
        logger.error(f"Error checking FFmpeg: {e}", exc_info=True)
        return False


def check_system_requirements():
    """Check system requirements for running the application."""
    results = {
        "os": platform.system(),
        "os_version": platform.version(),
        "python_version": platform.python_version(),
        "ffmpeg_installed": check_ffmpeg(),
        "cuda_available": torch.cuda.is_available(),
        "gpu_info": None,
        "mps_available": hasattr(torch.backends, "mps")
        and torch.backends.mps.is_available(),
        "issues": [],
    }

    if sys.version_info < (3, 11):
        results["issues"].append(
            "Python 3.11+ is recommended for optimal performance and compatibility."
        )

    if results["cuda_available"]:
        try:
            gpu_count = torch.cuda.device_count()
            gpu_info_list = []
            for i in range(gpu_count):
                name = torch.cuda.get_device_name(i)
                memory = torch.cuda.get_device_properties(
                    i).total_memory / (1024**3)
                gpu_info_list.append(
                    {"index": i, "name": name, "memory": f"{memory:.2f} GB"}
                )
            results["gpu_info"] = gpu_info_list
            logger.info(f"CUDA detected. GPU Info: {gpu_info_list}")
        except Exception as e:
            logger.error(f"Error getting GPU info: {e}", exc_info=True)
            results["issues"].append(f"Error accessing GPU information: {e}")
    elif results["mps_available"]:
        results["issues"].append("MPS acceleration available (Apple Silicon).")
        logger.info("MPS acceleration available.")
    else:
        results["issues"].append(
            "CUDA/MPS not detected. Using CPU (transcription may be slower)."
        )
        logger.info("No GPU acceleration (CUDA/MPS) detected. Using CPU.")

    if not results["ffmpeg_installed"]:
        results["issues"].append(
            "FFmpeg not found. Required for audio/video processing and conversion."
        )

    return results


def format_time_duration(seconds: Union[float, int, str]) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    try:
        secs = float(seconds)
        if secs < 0:
            secs = 0
    except (ValueError, TypeError):
        logger.warning(
            f"Invalid input for format_time_duration: {seconds}. Returning 00:00."
        )
        return "00:00"

    total_seconds = int(secs)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs_rem = total_seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs_rem:02d}"
    else:
        return f"{minutes:02d}:{secs_rem:02d}"


def show_system_info(parent=None):
    """Display system information in a message box."""
    from .ui_utils import show_info_message  # Local import to avoid circular dependency

    info = check_system_requirements()

    message = f"{APP_NAME} System Information:\n\n"
    message += f"- Operating System: {info['os']} {info['os_version']}\n"
    message += f"- Python Version: {info['python_version']}\n"
    message += f"- FFmpeg Installed: {'Yes' if info['ffmpeg_installed'] else 'No'}\n"
    message += f"- CUDA Available: {'Yes' if info['cuda_available'] else 'No'}\n"
    message += f"- MPS Available (Apple Silicon): {'Yes' if info['mps_available'] else 'No'}\n\n"

    if info["gpu_info"]:
        message += "Detected GPU(s):\n"
        for gpu in info["gpu_info"]:
            message += f"  • GPU {gpu['index']}: {gpu['name']} ({gpu['memory']})\n"
    elif info["cuda_available"]:
        message += "CUDA detected, but failed to get GPU details.\n"
    else:
        message += "No CUDA-enabled GPU detected.\n"

    if info["issues"]:
        message += "\nNotes & Potential Issues:\n"
        for issue in info["issues"]:
            message += f"  • {issue}\n"
    else:
        message += "\nSystem check passed with no major issues noted."

    show_info_message(parent, f"{APP_NAME} System Info", message)
    return message


def cleanup_temp_files(
    directory=None, file_pattern="transcribrr_temp_*", max_age_days=1
):
    """Clean up temporary files created by the application."""
    import tempfile
    import glob
    import time

    if directory is None:
        directory = tempfile.gettempdir()

    pattern = os.path.join(directory, file_pattern)
    files_to_check = glob.glob(pattern)
    current_time = time.time()
    # Reduce max age to 1 day for temp files
    max_age_seconds = max_age_days * 24 * 60 * 60
    deleted_count = 0

    logger.debug(
        f"Checking for old temp files in '{directory}' matching '{file_pattern}' older than {max_age_days} day(s)..."
    )

    for file_path in files_to_check:
        try:
            if os.path.isfile(file_path):
                file_mod_time = os.path.getmtime(file_path)
                file_age = current_time - file_mod_time
                if file_age > max_age_seconds:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.info(
                        f"Deleted old temp file: {file_path} (Age: {file_age/3600:.1f} hours)"
                    )
            elif os.path.isdir(file_path):
                # Optionally handle temporary directories later
                pass
        except Exception as e:
            logger.warning(
                f"Error during temp file cleanup for {file_path}: {e}")

    if deleted_count > 0:
        logger.info(f"Cleaned up {deleted_count} old temporary files.")
    else:
        logger.debug("No old temporary files found to clean up.")
    return deleted_count


class ConfigManager(QObject):
    """Singleton configuration manager."""

    config_updated = pyqtSignal(dict)  # Emits changes {key: new_value}
    _instance = None

    @classmethod
    def instance(cls) -> "ConfigManager":
        if cls._instance is None:
            # Ensure logs directory exists before initializing logger within instance
            os.makedirs(get_log_dir(), exist_ok=True)
            cls._instance = ConfigManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        # Prevent re-initialization
        if hasattr(self, "_config"):
            return
        self._config: Dict[str, Any] = {}
        self._config_path = get_config_path()
        self._load_config()

    def _load_config(self) -> None:
        """Load config, ensuring defaults are present."""
        loaded_config = {}
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r", encoding="utf-8") as config_file:
                    loaded_config = json.load(config_file)
                logger.info(f"Configuration loaded from {self._config_path}")
            else:
                logger.warning(
                    f"Config file not found at {self._config_path}, creating default."
                )
                # Proceed to ensure defaults, which will trigger save
        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding config file {self._config_path}: {e}. Using defaults.",
                exc_info=True,
            )
            # Proceed to ensure defaults
        except Exception as e:
            logger.error(
                f"Error loading config: {e}. Using defaults.", exc_info=True)
            # Proceed to ensure defaults

        # Ensure all default keys exist, merging loaded config over defaults
        self._config = DEFAULT_CONFIG.copy()
        # Overwrite defaults with loaded values
        self._config.update(loaded_config)

        # Save back if defaults were added or file was missing/corrupt
        if not os.path.exists(self._config_path) or len(self._config) > len(
            loaded_config
        ):
            self._save_config()

    def _save_config(self) -> None:
        """Save the current configuration state."""
        try:
            os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as config_file:
                json.dump(self._config, config_file, indent=4, sort_keys=True)
            logger.debug(f"Configuration saved to {self._config_path}")
        except Exception as e:
            logger.error(
                f"Error saving config to {self._config_path}: {e}", exc_info=True
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value, falling back to DEFAULT_CONFIG then provided default."""
        return self._config.get(key, DEFAULT_CONFIG.get(key, default))

    def set(self, key: str, value: Any) -> None:
        """Set a single config value and save."""
        if self.get(key) != value:  # Check against current effective value
            self._config[key] = value
            self._save_config()
            self.config_updated.emit({key: value})
            logger.info(f"Config set: {key} = {value}")

    def update(self, config_dict: Dict[str, Any]) -> None:
        """Update multiple config values and save once."""
        changes = {}
        for key, value in config_dict.items():
            if self.get(key) != value:
                self._config[key] = value
                changes[key] = value
        if changes:
            self._save_config()
            self.config_updated.emit(changes)
            logger.info(f"Config updated with {len(changes)} changes.")

    def get_all(self) -> Dict[str, Any]:
        """Get a copy of the entire configuration dictionary."""
        # Ensure defaults are present before returning copy
        full_config = DEFAULT_CONFIG.copy()
        full_config.update(self._config)
        return full_config

    def create_backup(self) -> Optional[str]:
        """Create a timestamped backup of the config file."""
        return create_backup(self._config_path)


class PromptManager(QObject):
    """Singleton prompt template manager."""

    prompts_changed = (
        pyqtSignal()
    )  # Emitted when prompts are added, updated, deleted, or imported
    _instance = None

    @classmethod
    def instance(cls) -> "PromptManager":
        if cls._instance is None:
            # Ensure logs directory exists before initializing logger within instance
            os.makedirs(get_log_dir(), exist_ok=True)
            cls._instance = PromptManager()
        return cls._instance

    def __init__(self):
        super().__init__()
        # Prevent re-initialization
        if hasattr(self, "_prompts"):
            return
        self._prompts: Dict[str, Dict[str, str]] = {}
        self._prompts_path = get_prompts_path()
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load prompts, ensuring defaults and correct format."""
        loaded_data = {}
        try:
            if os.path.exists(self._prompts_path):
                with open(self._prompts_path, "r", encoding="utf-8") as file:
                    loaded_data = json.load(file)
                logger.info(f"Prompts loaded from {self._prompts_path}")
            else:
                logger.warning(
                    f"Prompts file not found at {self._prompts_path}, creating default."
                )
                # Proceed to normalization which handles defaults
        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding prompts file {self._prompts_path}: {e}. Using defaults.",
                exc_info=True,
            )
            # Proceed to normalization
        except Exception as e:
            logger.error(
                f"Error loading prompts: {e}. Using defaults.", exc_info=True)
            # Proceed to normalization

        self._prompts = self._normalize_prompts(loaded_data)

        # Save back if defaults were added or file was missing/corrupt
        if not os.path.exists(self._prompts_path) or len(self._prompts) > len(
            loaded_data
        ):
            self._save_prompts()

    def _normalize_prompts(self, loaded_data: Dict) -> Dict[str, Dict[str, str]]:
        """Ensure all prompts have 'text' and 'category' keys, merge with defaults."""
        normalized = {}
        # Start with defaults
        for name, data in DEFAULT_PROMPTS.items():
            normalized[name] = data.copy()

        # Override/add from loaded data
        for name, data in loaded_data.items():
            if isinstance(data, str):  # Handle old format
                normalized[name] = {"text": data, "category": "General"}
            elif isinstance(data, dict) and "text" in data:
                normalized[name] = {
                    "text": data["text"],
                    "category": data.get(
                        "category", "General"
                    ),  # Default category if missing
                }
            else:
                logger.warning(
                    f"Skipping invalid prompt entry during load: '{name}'")
        return normalized

    def _save_prompts(self) -> None:
        """Save the current prompts state."""
        try:
            os.makedirs(os.path.dirname(self._prompts_path), exist_ok=True)
            with open(self._prompts_path, "w", encoding="utf-8") as file:
                json.dump(self._prompts, file, indent=4, sort_keys=True)
            logger.debug(f"Prompts saved to {self._prompts_path}")
        except Exception as e:
            logger.error(
                f"Error saving prompts to {self._prompts_path}: {e}", exc_info=True
            )

    def get_prompts(self) -> Dict[str, Dict[str, str]]:
        """Get a copy of all prompts."""
        return self._prompts.copy()

    def get_prompt_text(self, name: str) -> Optional[str]:
        """Get the text of a specific prompt by name."""
        return self._prompts.get(name, {}).get("text")

    def get_prompt_category(self, name: str) -> Optional[str]:
        """Get the category of a specific prompt by name."""
        return self._prompts.get(name, {}).get("category")

    def add_prompt(self, name: str, text: str, category: str = "Custom") -> bool:
        """Add a new prompt or overwrite an existing one."""
        name = name.strip()
        text = text.strip()
        category = category.strip() or "General"
        if not name or not text:
            logger.error("Prompt name and text cannot be empty.")
            return False
        self._prompts[name] = {"text": text, "category": category}
        self._save_prompts()
        self.prompts_changed.emit()
        logger.info(f"Added/Updated prompt: '{name}' in category '{category}'")
        return True

    def update_prompt(
        self, name: str, text: str, category: Optional[str] = None
    ) -> bool:
        """Update an existing prompt. Category is optional."""
        name = name.strip()
        text = text.strip()
        if name not in self._prompts:
            logger.error(f"Prompt '{name}' not found for updating.")
            return False
        if not text:
            logger.error("Prompt text cannot be empty.")
            return False

        self._prompts[name]["text"] = text
        if category is not None:
            self._prompts[name]["category"] = category.strip() or "General"
        self._save_prompts()
        self.prompts_changed.emit()
        logger.info(f"Updated prompt: '{name}'")
        return True

    def delete_prompt(self, name: str) -> bool:
        """Delete a prompt by name."""
        if name in self._prompts:
            # Prevent deleting default prompts? Optional check.
            # if name in DEFAULT_PROMPTS:
            #     logger.warning(f"Attempted to delete default prompt '{name}'. Deletion skipped.")
            #     return False
            del self._prompts[name]
            self._save_prompts()
            self.prompts_changed.emit()
            logger.info(f"Deleted prompt: '{name}'")
            return True
        logger.warning(f"Prompt '{name}' not found for deletion.")
        return False

    def import_prompts_from_file(
        self, file_path: str, merge: bool = True
    ) -> Tuple[bool, str]:
        """Import prompts from a JSON file."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                imported_data = json.load(file)

            new_prompts = self._normalize_prompts(
                imported_data
            )  # Normalize imported data
            count = len(new_prompts)

            if not merge:
                # Replace: Start with defaults, then add imported
                self._prompts = DEFAULT_PROMPTS.copy()
                self._prompts.update(new_prompts)
                action = "Replaced existing prompts with"
            else:
                # Merge: Add/overwrite imported into current
                self._prompts.update(new_prompts)
                action = "Merged/Updated with"

            self._save_prompts()
            self.prompts_changed.emit()
            logger.info(f"{action} {count} prompts from {file_path}")
            return True, f"Successfully {action.lower()} {count} prompts."
        except json.JSONDecodeError as e:
            logger.error(
                f"Error decoding JSON from {file_path}: {e}", exc_info=True)
            return False, f"Import failed: Invalid JSON file ({e})"
        except Exception as e:
            logger.error(
                f"Failed to import prompts from {file_path}: {e}", exc_info=True
            )
            return False, f"Import failed: {e}"

    def export_prompts_to_file(self, file_path: str) -> Tuple[bool, str]:
        """Export current prompts to a JSON file."""
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as file:
                # Exclude defaults maybe? Or export all? Export all for now.
                json.dump(self._prompts, file, indent=4, sort_keys=True)
            count = len(self._prompts)
            logger.info(f"Exported {count} prompts to {file_path}")
            return True, f"Successfully exported {count} prompts."
        except Exception as e:
            logger.error(
                f"Failed to export prompts to {file_path}: {e}", exc_info=True)
            return False, f"Export failed: {e}"


def estimate_transcription_time(
    file_path: str, model_name: str, is_gpu: bool = False
) -> Optional[int]:
    """Estimate transcription time (very rough estimate)."""
    if not os.path.exists(file_path):
        return None
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        # Simplified speed factor based on model size name
        speed_factor = 1.0  # Base (medium)
        if "tiny" in model_name:
            speed_factor = 3.0
        elif "base" in model_name:
            speed_factor = 2.0
        elif "small" in model_name:
            speed_factor = 1.5
        elif "large" in model_name:
            speed_factor = 0.5
        if "distil" in model_name:
            speed_factor *= 1.2  # Distilled models are faster

        if is_gpu:
            speed_factor *= 3  # Rough GPU boost

        # Time = Size / Speed (lower speed factor means slower -> more time)
        # Avoid division by zero
        if speed_factor <= 0:
            speed_factor = 0.1
        # Estimate seconds per MB
        secs_per_mb = (
            3 / speed_factor
        )  # Adjusted baseline (e.g., medium takes ~3s/MB on CPU)
        estimated_time = (file_size_mb * secs_per_mb) + \
            15  # Add fixed overhead

        logger.debug(
            f"Estimated time for {os.path.basename(file_path)} ({file_size_mb:.1f}MB, model='{model_name}', gpu={is_gpu}): {estimated_time:.1f}s"
        )
        return max(int(estimated_time), 5)  # Min 5 seconds estimate
    except Exception as e:
        logger.warning(
            f"Could not estimate transcription time for {file_path}: {e}")
        return None
