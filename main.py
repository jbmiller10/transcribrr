#!/usr/bin/env python3
"""
Transcribrr - Development launcher for the application

This is a simple launcher script used during development to start the application.
For packaged builds, use the entry point in app/__main__.py instead.
"""

import sys
import os

# Ensure the app directory is in the import path
app_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app')
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)

# Import the main execution function from the new location
from app.__main__ import run_application

if __name__ == "__main__":
    # This allows running `python main.py` during development
    sys.exit(run_application())