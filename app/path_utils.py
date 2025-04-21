"""Path utilities for resource and file path management."""

import os
import sys
import logging
from typing import Optional

# Configure module-level logger
logger = logging.getLogger('transcribrr')

def _get_base_resource_path() -> str:
    """
    Get the base resource directory path based on the execution environment.
    
    This is a helper function to make testing easier.
    """
    # Check if running as PyInstaller bundle
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
        logger.debug(f"Using PyInstaller _MEIPASS path: {base_path}")
        return base_path
        
    # Check if running as a py2app bundle
    elif getattr(sys, 'frozen', False) and 'MacOS' in sys.executable:
        bundle_dir = os.path.normpath(os.path.join(
            os.path.dirname(sys.executable), 
            os.pardir, 'Resources'
        ))
        base_path = bundle_dir
        logger.debug(f"Using py2app bundle path: {base_path}")
        return base_path
        
    # Default: Not running as a bundled app, use project root directory
    # Go up two levels from this file's directory (app/path_utils.py → project root)
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logger.debug(f"Using development path: {base_path}")
    return base_path

def resource_path(relative_path: Optional[str] = None) -> str:
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
    base_path = _get_base_resource_path()
    
    # If no relative path provided, return the base resource directory
    if relative_path is None:
        return base_path
        
    # Join with the relative path and return
    full_path = os.path.join(base_path, relative_path)
    logger.debug(f"Resource path for '{relative_path}': {full_path}")
    return full_path


def get_user_data_path() -> str:
    """
    Return path to user data directory.
    
    This function determines where user-specific data should be stored:
    1. If TRANSCRIBRR_USER_DATA_DIR environment variable is set, use that
    2. When packaged, use the user's standard data directory (via appdirs)
    3. In development mode, use the project directory
    
    Returns:
        Absolute path to the user data directory
    """
    # Delay import to avoid circular import with constants
    import appdirs
    
    # We can't directly import from constants since that would cause a circular import
    # So we define these constants here as well - they should match constants.py
    APP_NAME = "Transcribrr"
    APP_AUTHOR = "John Miller"
    
    # First, check if the app has provided a specific user data directory
    if "TRANSCRIBRR_USER_DATA_DIR" in os.environ:
        user_data_dir = os.environ["TRANSCRIBRR_USER_DATA_DIR"]
        os.makedirs(user_data_dir, exist_ok=True)
        return user_data_dir
    
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