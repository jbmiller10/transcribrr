"""Path utilities for resource and file path management."""

import os
import sys
import logging
from typing import Optional, Callable

# Configure module-level logger
logger = logging.getLogger("transcribrr")


def get_execution_environment() -> str:
    """Return execution environment: 'pyinstaller', 'py2app', or 'development'."""
    try:
        # PyInstaller explicitly exposes _MEIPASS
        if hasattr(sys, "_MEIPASS"):
            return "pyinstaller"

        # Detect macOS app bundle layouts (Briefcase/py2app) by path pattern
        exe = getattr(sys, "executable", "") or ""
        if "/Contents/MacOS/" in exe:
            return "py2app"

        # Secondary heuristic on macOS: presence of sibling Resources directory
        if sys.platform == "darwin":
            macos_dir = os.path.dirname(exe)
            resources_dir = os.path.normpath(os.path.join(macos_dir, os.pardir, "Resources"))
            if os.path.isdir(resources_dir):
                return "py2app"
    except Exception:
        # Fall back to development on any detection failure
        pass

    # Default to development in all other cases (including frozen on non-macOS)
    return "development"


def _get_base_resource_path(env_detector: Optional[Callable[[], str]] = None) -> str:
    """
    Get the base resource directory path based on the execution environment.

    This is a helper function to make testing easier.
    """
    if env_detector is None:
        env_detector = get_execution_environment
    env = env_detector()

    # Check if running as PyInstaller bundle
    if env == "pyinstaller":
        pyinstaller_path: str = sys._MEIPASS  # Type annotation to ensure correct type
        logger.debug(f"Using PyInstaller _MEIPASS path: {pyinstaller_path}")
        return pyinstaller_path

    # Check if running as a macOS app bundle (Briefcase/py2app)
    elif env == "py2app":
        bundle_dir = os.path.normpath(
            os.path.join(os.path.dirname(sys.executable),
                         os.pardir, "Resources")
        )
        py2app_path: str = bundle_dir  # Type annotation to ensure correct type
        logger.debug(f"Using py2app bundle path: {py2app_path}")
        return py2app_path

    # Default: Not running as a bundled app, use project root directory
    # Go up two levels from this file's directory (app/path_utils.py → project root)
    dev_path: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger.debug(f"Using development path: {dev_path}")
    return dev_path


def resource_path(relative_path: Optional[str] = None, *, env_detector: Optional[Callable[[], str]] = None) -> str:
    """
    Return absolute path to resources, works for dev and for PyInstaller/py2app.

    This function determines the resource directory path based on the application's
    execution environment:

    1. When running as a PyInstaller bundle: Uses sys._MEIPASS
    2. When running as a py2app bundle: Uses path relative to the executable
    3. When running in development mode: Uses the project root directory

    Args:
        relative_path: Optional path relative to the resource directory.
                      If None, returns the resource directory itself.

    Returns:
        Absolute path to the resource or the resource directory.
    """
    base_path = _get_base_resource_path(env_detector)

    # If no relative path provided, return the base resource directory
    if relative_path is None:
        return base_path

    # If an absolute path is provided, honor it verbatim
    if os.path.isabs(relative_path):
        logger.debug(f"Absolute resource path requested: {relative_path}")
        return relative_path

    # Primary join: Resources/<relative_path>
    full_path = os.path.join(base_path, relative_path)
    if os.path.exists(full_path):
        logger.debug(f"Resource path for '{relative_path}': {full_path}")
        return full_path

    # In some Briefcase/py2app layouts, app code is at Resources/app and
    # additional resources may also be nested under that folder. Fall back to a
    # couple of common alternatives if the primary join isn't present.
    try:
        env = env_detector() if env_detector else get_execution_environment()
    except Exception:
        env = "development"

    if env == "py2app":
        fallbacks = [
            os.path.join(base_path, "app", relative_path),
            os.path.join(base_path, "transcribrr", relative_path),
            os.path.join(base_path, "app", "transcribrr", relative_path),
        ]
        for alt in fallbacks:
            if os.path.exists(alt):
                logger.debug(
                    f"Resource fallback for '{relative_path}': {alt}")
                return alt

    # Last resort: return the primary joined path (may not exist) for callers
    # that want to probe existence or handle their own fallback.
    logger.debug(
        f"Resource path (not found, returning best-effort) for '{relative_path}': {full_path}")
    return full_path
