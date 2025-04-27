"""Standardized error handling utilities for user-facing error messages.

This module provides standardized functions for handling and displaying errors
to users in a consistent manner across the application.
"""

import logging
import traceback
from typing import Optional, Dict, Any, Type, Callable, List
from PyQt6.QtWidgets import QWidget

from app.secure import redact
from app.ui_utils_legacy import show_error_message, safe_error

# Configure logging
logger = logging.getLogger('transcribrr')

# Map of exception types to user-friendly error messages
ERROR_MESSAGE_MAP: Dict[Type[Exception], str] = {
    # File-related errors
    FileNotFoundError: "The specified file could not be found.",
    PermissionError: "You don't have permission to access this file or directory.",
    IOError: "There was a problem reading or writing to a file.",

    # Network-related errors
    ConnectionError: "Could not connect to the server. Please check your internet connection.",
    TimeoutError: "The connection timed out. The server might be busy or unavailable.",

    # Database errors - add specific SQLite errors if needed

    # API-specific errors can be added as needed
    ValueError: "Invalid input provided.",
    RuntimeError: "An unexpected error occurred during operation."
}

# Map of error sources to user-friendly context
ERROR_CONTEXT_MAP: Dict[str, str] = {
    "transcription": "Audio transcription",
    "gpt": "GPT text processing",
    "youtube": "YouTube download",
    "voice_recording": "Voice recording",
    "database": "Database operation",
    "file_import": "File import",
    "export": "File export"
}


def handle_error(
    error: Exception,
    parent: Optional[QWidget] = None,
    source: str = "application",
    show_dialog: bool = True,
    title_override: Optional[str] = None,
    callback: Optional[Callable[[str], None]] = None
) -> str:
    """Handle an error in a standardized way.

    Args:
        error: The exception to handle
        parent: Parent widget for any dialogs
        source: Source of the error (e.g., "transcription", "youtube")
        show_dialog: Whether to show an error dialog
        title_override: Optional override for the dialog title
        callback: Optional callback to call with the error message

    Returns:
        The user-facing error message that was generated
    """
    # Extract exception details for logging
    error_type = type(error)
    error_message = str(error)
    error_traceback = traceback.format_exc()

    # Create a redacted version of the error for UI display
    safe_error_message = redact(error_message)

    # Get user-friendly message from map or use generic message
    user_friendly_message = ERROR_MESSAGE_MAP.get(error_type, safe_error_message)

    # Get context if source is recognized
    context = ERROR_CONTEXT_MAP.get(source, "Application")

    # Create dialog title
    title = title_override or f"{context} Error"

    # Log the error with appropriate level
    if error_type in [FileNotFoundError, ValueError, PermissionError]:
        # Less severe errors
        logger.warning(f"{context} error ({error_type.__name__}): {safe_error_message}")
    else:
        # More severe errors - log with full traceback
        logger.error(f"{context} error ({error_type.__name__}): {error_message}\n{error_traceback}")

    # Show error dialog if requested
    if show_dialog and parent:
        safe_error(parent, title, user_friendly_message)

    # Call callback if provided
    if callback:
        callback(user_friendly_message)

    return user_friendly_message


def handle_external_library_error(
    error: Exception,
    library_name: str,
    parent: Optional[QWidget] = None,
    show_dialog: bool = True
) -> str:
    """Handle errors from external libraries with specific error messages.

    Args:
        error: The exception to handle
        library_name: Name of the external library (e.g., "openai", "yt-dlp")
        parent: Parent widget for any dialogs
        show_dialog: Whether to show an error dialog

    Returns:
        The user-facing error message that was generated
    """
    # Common error patterns for various libraries
    error_str = str(error).lower()
    error_type = type(error).__name__

    # Create a safe version of the error
    safe_error_message = redact(str(error))

    # Default message if no specific pattern is matched
    user_message = f"{library_name} library error: {safe_error_message}"
    title = f"{library_name.capitalize()} Error"

    # Library-specific error patterns
    if library_name.lower() == "openai":
        if "api key" in error_str:
            user_message = "Invalid or missing API key. Please check your OpenAI API key in Settings."
        elif "rate limit" in error_str:
            user_message = "Rate limit exceeded. Please wait a moment and try again."
        elif "context length" in error_str or "token limit" in error_str:
            user_message = "The text is too long for the current model. Try a different model or shorten the text."
        elif "timeout" in error_str:
            user_message = "The request timed out. The OpenAI service might be busy."
        elif "connection" in error_str:
            user_message = "Connection error. Please check your internet connection."

    elif library_name.lower() == "yt-dlp":
        if "age" in error_str and "confirm" in error_str:
            user_message = "Age-restricted video. Login required (not supported)."
        elif "unavailable" in error_str:
            user_message = "This video is unavailable or has been removed."
        elif "private" in error_str:
            user_message = "This is a private video that cannot be accessed."
        elif "copyright" in error_str:
            user_message = "This video is unavailable due to copyright restrictions."
        elif "sign in" in error_str or "log in" in error_str:
            user_message = "This video requires a YouTube account to access."

    elif library_name.lower() == "ffmpeg":
        if "not found" in error_str:
            user_message = "FFmpeg executable not found. Please ensure FFmpeg is installed."
        elif "format" in error_str:
            user_message = "Unsupported file format or corrupted file."

    elif library_name.lower() == "pyaudio":
        if "device" in error_str:
            user_message = "Audio device error. The microphone might be disconnected or in use."
        elif "stream" in error_str:
            user_message = "Error with audio stream. Try restarting the application."

    # Log the error appropriately
    logger.error(f"{library_name} error ({error_type}): {safe_error_message}")

    # Show dialog if requested
    if show_dialog and parent:
        safe_error(parent, title, user_message)

    return user_message


def get_common_error_messages() -> Dict[str, List[Dict[str, str]]]:
    """Get a dictionary of common error messages organized by category.

    Returns:
        Dictionary mapping error categories to lists of error details
    """
    return {
        "network": [
            {"error": "Connection refused",
                "message": "Could not connect to the server. Please check your internet connection."},
            {"error": "Timeout", "message": "The connection timed out. The server might be busy or unavailable."},
            {"error": "DNS resolution",
                "message": "Could not resolve the server's address. Check your internet connection."}
        ],
        "file_system": [
            {"error": "Permission denied",
                "message": "You don't have permission to access this file or directory."},
            {"error": "File not found", "message": "The specified file could not be found."},
            {"error": "Disk full", "message": "Not enough disk space to complete this operation."}
        ],
        "api": [
            {"error": "Invalid API key",
                "message": "The API key is invalid or has expired. Please update it in Settings."},
            {"error": "Rate limit", "message": "You have reached the rate limit for this API. Please try again later."},
            {"error": "Service unavailable",
                "message": "The service is currently unavailable. Please try again later."}
        ]
    }
