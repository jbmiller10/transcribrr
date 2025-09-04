"""Path utilities for resource and file path management."""

import os
import sys
import logging
from typing import Optional, Callable

# Configure module-level logger
logger = logging.getLogger("transcribrr")


def get_execution_environment() -> str:
    """
    Return execution environment: 'pyinstaller', 'app_bundle', or 'development'.

    Notes:
    - Briefcase and py2app style macOS bundles may not set sys.frozen; detect by
      the executable path pattern (.../Contents/MacOS/...) or presence of a
      sibling Resources directory.
    """
    try:
        if hasattr(sys, "_MEIPASS"):
            return "pyinstaller"

        exe = getattr(sys, "executable", "") or ""
        # Heuristic for macOS app bundles (Briefcase/py2app)
        if sys.platform == "darwin":
            macos_dir = os.path.dirname(exe)
            resources_dir = os.path.normpath(os.path.join(macos_dir, os.pardir, "Resources"))
            if "/Contents/MacOS/" in exe or os.path.isdir(resources_dir):
                return "app_bundle"

        # Generic frozen fallback
        if getattr(sys, "frozen", False):
            return "app_bundle"
    except Exception:
        # If detection fails, assume development to avoid crashing
        pass

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
    elif env == "app_bundle":
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

    # Join with the relative path and return
    full_path = os.path.normpath(os.path.join(base_path, relative_path))
    logger.debug(f"Resource path for '{relative_path}': {full_path}")
    return full_path
