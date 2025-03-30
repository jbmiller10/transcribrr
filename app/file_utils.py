"""
File utility functions for handling files and file paths.
"""

import os
import shutil
import tempfile
from datetime import datetime
import logging
from typing import Optional, Tuple, List, Union
from moviepy.editor import VideoFileClip, AudioFileClip
import wave
from pydub import AudioSegment
import datetime

from app.constants import (
    AUDIO_EXTENSIONS, VIDEO_EXTENSIONS, DOCUMENT_EXTENSIONS,
    FileType, FILE_TYPES, RECORDINGS_DIR, MAX_FILE_SIZE_MB
)

# Configure logging
logger = logging.getLogger('transcribrr')

def get_file_type(file_path: str) -> FileType:
    """
    Determine the type of file based on its extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        FileType enum value
    """
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
    """
    Check if a file is a valid media file that can be transcribed.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file is a valid media file
    """
    if not os.path.exists(file_path):
        return False
        
    file_type = get_file_type(file_path)
    return file_type in (FileType.AUDIO, FileType.VIDEO)

def check_file_size(file_path: str, max_size_mb: int = MAX_FILE_SIZE_MB) -> Tuple[bool, float]:
    """
    Check if a file exceeds the maximum allowed size.
    
    Args:
        file_path: Path to the file
        max_size_mb: Maximum allowed size in MB
        
    Returns:
        Tuple of (is_valid, size_in_mb)
    """
    if not os.path.exists(file_path):
        return False, 0
        
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    return file_size_mb <= max_size_mb, file_size_mb

def ensure_recordings_dir() -> str:
    """
    Ensure the recordings directory exists.
    
    Returns:
        Path to the recordings directory
    """
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    return RECORDINGS_DIR

def generate_new_filename(base_name: str, directory: str) -> str:
    """
    Generate a unique filename in the target directory.
    
    Args:
        base_name: Base filename (without directory)
        directory: Target directory
        
    Returns:
        Unique file path in the target directory
    """
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
    """
    Safely copy a file to the target directory, handling errors.
    
    Args:
        source_path: Path to the source file
        target_dir: Target directory (defaults to recordings dir)
        
    Returns:
        Path to the copied file or None if failed
    """
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
    """
    Get a timestamp string for filenames.
    
    Returns:
        Formatted timestamp string
    """
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

def calculate_duration(file_path: str) -> str:
    """
    Calculate the duration of an audio or video file.
    
    Args:
        file_path: Path to the media file
        
    Returns:
        Duration as a formatted string (HH:MM:SS)
    """
    try:
        file_type = get_file_type(file_path)
        
        if file_type == FileType.AUDIO:
            clip = AudioFileClip(file_path)
        elif file_type == FileType.VIDEO:
            clip = VideoFileClip(file_path)
        else:
            logger.error(f"Unsupported file type for duration calculation: {file_path}")
            return "00:00:00"
        
        # Calculate the duration
        duration_in_seconds = clip.duration
        clip.close()  # Close the clip to release the file
        
        # Format the duration as HH:MM:SS
        duration_str = str(datetime.timedelta(seconds=int(duration_in_seconds)))
        return duration_str
        
    except Exception as e:
        logger.error(f"Error calculating duration for {file_path}: {e}")
        return "00:00:00"

def save_temp_recording(frames: List[bytes], channels: int, sample_width: int, rate: int) -> Optional[str]:
    """
    Save audio frames to a temporary file.
    
    Args:
        frames: List of audio frames bytes
        channels: Number of audio channels
        sample_width: Sample width in bytes
        rate: Sample rate in Hz
        
    Returns:
        Path to the saved file or None if failed
    """
    if not frames:
        logger.error("No audio frames to save")
        return None
        
    try:
        # Write to a temporary WAV file first
        temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False).name
        
        with wave.open(temp_wav, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(b''.join(frames))
        
        # Generate a filename with timestamp in the Recordings directory
        timestamp = get_timestamp_string()
        mp3_filename = os.path.join(ensure_recordings_dir(), f"Recording-{timestamp}.mp3")
        
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