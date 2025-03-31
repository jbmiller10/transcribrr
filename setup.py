"""
setup.py file for creating a macOS application bundle using py2app
"""

from setuptools import setup
import os
import glob

APP = ['main.py']
APP_NAME = "Transcribrr"

# Include all Python files in app directory
APP_FILES = glob.glob('app/**/*.py', recursive=True)

# Include entire directories
DATA_FILES = [
    ('icons', glob.glob('icons/**/*', recursive=True)),
    ('Recordings', glob.glob('Recordings/**/*', recursive=True)),
    ('database', glob.glob('database/**/*', recursive=True)),
    ('logs', glob.glob('logs/**/*', recursive=True)),
    ('', ['config.json', 'preset_prompts.json']),
]

OPTIONS = {
    'argv_emulation': True,
    'includes': [
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.QtSvg', 
        'PyQt6.QtPrintSupport', 'PyQt6.QtSvgWidgets', 'PyQt6.uic', 'PyQt6.sip',
        'appdirs', 'numpy', 'pyaudio', 'pydub', 'moviepy', 'moviepy.editor',
        'yt_dlp', 'openai', 'keyring', 'requests', 'PyPDF2'
    ],
    'packages': [
        'app', 'app.services', 'app.threads', 'numpy', 
    ],
    'iconfile': 'icons/app/app_icon.icns',
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleVersion': '1.0.0',
        'CFBundleIdentifier': f'com.{APP_NAME.lower()}.app',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'NSMicrophoneUsageDescription': f'{APP_NAME} needs access to the microphone for voice recording.',
    },
}

setup(
    name=APP_NAME,
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)