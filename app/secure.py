import os
import sys
import re
import logging
from typing import Dict, Optional

# Configure logger
logger = logging.getLogger("transcribrr")

# Patterns to detect sensitive API keys/tokens
OPENAI_KEY_PATTERN = r"sk-[A-Za-z0-9_-]{10,}"
HF_TOKEN_PATTERN = r"hf_[A-Za-z0-9]{10,}"

# Combined pattern for efficient scanning
API_KEY_PATTERN = f"({OPENAI_KEY_PATTERN}|{HF_TOKEN_PATTERN})"
API_KEY_REGEX = re.compile(API_KEY_PATTERN)

# Text replacement
REDACTED_TEXT = "***-REDACTED-***"


def redact(text: str) -> str:
    """
    Redact sensitive information like API keys from text.

    Args:
        text: Text that might contain sensitive information

    Returns:
        Text with sensitive information redacted
    """
    if not text:
        return ""

    # Replace any matching patterns with the redaction text
    return API_KEY_REGEX.sub(REDACTED_TEXT, text)


class SensitiveLogFilter(logging.Filter):
    """Filter to redact sensitive information from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records to redact sensitive information.

        Args:
            record: Log record to filter

        Returns:
            Always True (to keep the record), but modifies the record
        """
        # Redact the message
        if hasattr(record, "msg") and record.msg:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)

        # Redact args if they are strings
        if hasattr(record, "args") and record.args:
            args_list = list(record.args)
            for i, arg in enumerate(args_list):
                if isinstance(arg, str):
                    args_list[i] = redact(arg)
            record.args = tuple(args_list)

        return True


def migrate_api_keys() -> Dict[str, bool]:
    """
    Migrate API keys from old service ID to new version-based service ID.

    Returns:
        Dictionary with migration status for each key type
    """
    import keyring
    from .constants import APP_VERSION, APP_NAME

    old_service_id = "transcription_application"
    new_service_id = f"{APP_NAME.lower()}-v{APP_VERSION}"

    migration_status = {"openai": False, "hf": False}

    try:
        # Check for OPENAI_API_KEY in old location
        openai_key = keyring.get_password(old_service_id, "OPENAI_API_KEY")
        if openai_key:
            # Store in new location
            keyring.set_password(new_service_id, "OPENAI_API_KEY", openai_key)
            # Delete from old location
            keyring.delete_password(old_service_id, "OPENAI_API_KEY")
            migration_status["openai"] = True
            logger.info("Migrated OpenAI API key to new service ID")
    except Exception as e:
        logger.error(f"Error migrating OpenAI API key: {redact(str(e))}")

    try:
        # Check for HF_AUTH_TOKEN in old location
        hf_token = keyring.get_password(old_service_id, "HF_AUTH_TOKEN")
        if hf_token:
            # Store in new location
            keyring.set_password(new_service_id, "HF_AUTH_TOKEN", hf_token)
            # Delete from old location
            keyring.delete_password(old_service_id, "HF_AUTH_TOKEN")
            migration_status["hf"] = True
            logger.info("Migrated HuggingFace token to new service ID")
    except Exception as e:
        logger.error(f"Error migrating HuggingFace token: {redact(str(e))}")

    return migration_status


def get_service_id() -> str:
    """Get the current keyring service ID including app version."""
    from .constants import APP_VERSION, APP_NAME

    return f"{APP_NAME.lower()}-v{APP_VERSION}"


def _is_packaged() -> bool:
    """Return True if running as a packaged app (PyInstaller/py2app)."""
    return hasattr(sys, "_MEIPASS") or getattr(sys, "frozen", False)


def get_api_key(key_name: str) -> Optional[str]:
    """
    Get an API key securely from the keyring.

    Args:
        key_name: Name of the key to retrieve (e.g., "OPENAI_API_KEY", "HF_AUTH_TOKEN")

    Returns:
        The API key if found, None otherwise
    """
    # In development and test environments, allow returning fake keys by default
    # to keep unit tests import-safe and avoid keyring dependencies. Packaged
    # builds and explicit overrides disable this behavior.
    use_fake = os.environ.get("TRANSCRIBRR_FAKE_KEYS", "1") == "1" and not _is_packaged()
    if use_fake and key_name in ["OPENAI_API_KEY", "HF_API_KEY", "HF_AUTH_TOKEN"]:
        return "fake-api-key"

    import keyring
    return keyring.get_password(get_service_id(), key_name)


def set_api_key(key_name: str, value: str) -> bool:
    """
    Store an API key securely in the keyring.

    Args:
        key_name: Name of the key to store (e.g., "OPENAI_API_KEY", "HF_AUTH_TOKEN")
        value: The API key to store

    Returns:
        True if successful, False otherwise
    """
    import keyring

    try:
        if value:
            keyring.set_password(get_service_id(), key_name, value)
        else:
            # If empty value, delete the key
            try:
                keyring.delete_password(get_service_id(), key_name)
            except keyring.errors.PasswordDeleteError:
                # Ignore error if password doesn't exist
                pass
        return True
    except Exception as e:
        logger.error(f"Error storing API key: {redact(str(e))}")
        return False
