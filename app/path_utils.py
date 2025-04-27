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
        base_path: str = sys._MEIPASS  # Type annotation to ensure correct type
        logger.debug(f"Using PyInstaller _MEIPASS path: {base_path}")
        return base_path
        
    # Check if running as a py2app bundle
    elif getattr(sys, 'frozen', False) and 'MacOS' in sys.executable:
        bundle_dir = os.path.normpath(os.path.join(
            os.path.dirname(sys.executable), 
            os.pardir, 'Resources'
        ))
        base_path: str = bundle_dir  # Type annotation to ensure correct type
        logger.debug(f"Using py2app bundle path: {base_path}")
        return base_path
        
    # Default: Not running as a bundled app, use project root directory
    # Go up two levels from this file's directory (app/path_utils.py → project root)
    base_path: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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

