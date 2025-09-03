"""File utilities."""

import os
import shutil
import tempfile
from datetime import datetime
import logging
from typing import Optional, Tuple, List
import wave
from pydub import AudioSegment
import datetime

from app.constants import (
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    FileType,
    MAX_FILE_SIZE_MB,
    get_recordings_dir,
)

# Configure logging
logger = logging.getLogger("transcribrr")


def get_file_type(file_path: str) -> FileType:
    """Return file type based on extension."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext in AUDIO_EXTENSIONS:
        return FileType.AUDIO
    elif ext in VIDEO_EXTENSIONS:
        return FileType.VIDEO
    elif ext in DOCUMENT_EXTENSIONS:
        return FileType.DOCUMENT
    else:
        return FileType.UNKNOWN


def is_valid_media_file(file_path: str) -> bool:
    """Return True if media file."""
    if not os.path.exists(file_path):
        return False

    file_type = get_file_type(file_path)
    return file_type in (FileType.AUDIO, FileType.VIDEO)


def check_file_size(
    file_path: str, max_size_mb: int = MAX_FILE_SIZE_MB
) -> Tuple[bool, float]:
    """Check file size against max MB."""
    if not os.path.exists(file_path):
        return False, 0

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    return file_size_mb <= max_size_mb, file_size_mb


def ensure_recordings_dir() -> str:
    """Ensure recordings dir exists."""
    recordings_dir = get_recordings_dir()
    os.makedirs(recordings_dir, exist_ok=True)
    return recordings_dir


def generate_new_filename(base_name: str, directory: str) -> str:
    """Generate unique filename in directory."""
    base_path = os.path.join(directory, base_name)

    # If file doesn't exist, use it directly
    if not os.path.exists(base_path):
        return base_path

    # Generate a unique name by adding a counter
    name, ext = os.path.splitext(base_name)
    counter = 1
    new_path = os.path.join(directory, f"{name}_{counter}{ext}")

    while os.path.exists(new_path):
        counter += 1
        new_path = os.path.join(directory, f"{name}_{counter}{ext}")

    return new_path


def safe_copy_file(source_path: str, target_dir: str = None) -> Optional[str]:
    """Copy file safely, return new path or None."""
    if not os.path.exists(source_path):
        logger.error(f"Source file does not exist: {source_path}")
        return None

    if target_dir is None:
        target_dir = ensure_recordings_dir()

    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)

    try:
        base_name = os.path.basename(source_path)
        target_path = generate_new_filename(base_name, target_dir)

        shutil.copy2(source_path, target_path)
        logger.info(f"File copied from {source_path} to {target_path}")
        return target_path

    except (shutil.Error, OSError, IOError) as e:
        logger.error(f"Error copying file {source_path}: {e}")
        return None


def get_timestamp_string() -> str:
    """Return timestamp string."""
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def calculate_duration(file_path: str) -> str:
    """Return media duration string."""
    try:
        file_type = get_file_type(file_path)

        if file_type == FileType.AUDIO:
            # Prefer pydub for audio duration (no heavy moviepy dependency)
            try:
                audio = AudioSegment.from_file(file_path)
                duration_in_seconds = len(audio) / 1000.0
                audio = None
            except Exception:
                # Fallback to moviepy if available
                try:
                    from moviepy.editor import AudioFileClip  # type: ignore

                    clip = AudioFileClip(file_path)
                    duration_in_seconds = clip.duration
                    clip.close()
                except Exception as mp_err:
                    logger.error(
                        f"Audio duration check failed (no moviepy?): {mp_err}"
                    )
                    return "00:00:00"
        elif file_type == FileType.VIDEO:
            # Use moviepy for video if available
            try:
                from moviepy.editor import VideoFileClip  # type: ignore

                clip = VideoFileClip(file_path)
                duration_in_seconds = clip.duration
                clip.close()
            except Exception as mp_err:
                logger.error(
                    f"Video duration check requires moviepy: {mp_err}"
                )
                return "00:00:00"
        else:
            logger.error(
                f"Unsupported file type for duration calculation: {file_path}")
            return "00:00:00"

        # Format the duration as HH:MM:SS
        duration_str = str(datetime.timedelta(
            seconds=int(duration_in_seconds)))
        return duration_str

    except Exception as e:
        logger.error(f"Error calculating duration for {file_path}: {e}")
        return "00:00:00"


def save_temp_recording(
    frames: List[bytes], channels: int, sample_width: int, rate: int
) -> Optional[str]:
    """Save audio frames to temp file."""
    if not frames:
        logger.error("No audio frames to save")
        return None

    try:
        # Write to a temporary WAV file first
        temp_wav = tempfile.NamedTemporaryFile(
            suffix=".wav", delete=False).name

        with wave.open(temp_wav, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(b"".join(frames))

        # Generate a filename with timestamp in the Recordings directory
        timestamp = get_timestamp_string()
        mp3_filename = os.path.join(
            ensure_recordings_dir(), f"Recording-{timestamp}.mp3"
        )

        # Convert to MP3
        audio = AudioSegment.from_wav(temp_wav)
        audio.export(mp3_filename, format="mp3", bitrate="192k")

        # Clean up temporary file
        os.remove(temp_wav)

        logger.info(f"Recording saved to {mp3_filename}")
        return mp3_filename

    except Exception as e:
        logger.error(f"Error saving recording: {e}")
        return None
