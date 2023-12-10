import re
import traceback
import datetime
import shutil
from PyQt6.QtCore import (
    pyqtSignal, QSize, Qt, QPropertyAnimation, QEasingCurve, QFile,
)
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QPushButton, QMessageBox,
    QWidget, QHBoxLayout, QLabel, QListWidget, QSizePolicy,
    QPushButton, QSpacerItem, QFileDialog, QMenu, QListWidgetItem, QMainWindow,QComboBox,QTextEdit, QSplitter,QStatusBar
)

from app.YouTubeDownloadThread import YouTubeDownloadThread
from app.TranscodingThread import TranscodingThread
from app.VoiceRecorderWidget import VoiceRecorderWidget  # Import specific classes
import os
from pydub import AudioSegment
from app.utils import validate_url, is_audio_file, is_video_file
from app.RecordingListItem import RecordingListItem


class MainTranscriptionWidget(QWidget):
    transcriptionStarted = pyqtSignal()
    transcriptionStopped = pyqtSignal()
    transcriptionSaved = pyqtSignal(str)
    settingsRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.transcription_type_combo = QComboBox()
        self.transcription_type_combo.addItems([
            'Journal Entry', 'Meeting Minutes', 'Interview Summary'
        ])

        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon('icons/play.svg'))  # path to 'play' icon
        self.play_button.setFixedSize(50, 50)  # Adjust size as needed

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon('icons/save.svg'))  # path to 'save' icon
        self.save_button.setFixedSize(50, 50)  # Adjust size as needed

        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon('icons/settings.svg'))  # path to 'settings' icon
        self.settings_button.setFixedSize(50, 50)  # Adjust size as needed

        self.transcript_text = QTextEdit()

        self.layout.addWidget(self.transcription_type_combo)
        self.layout.addWidget(self.play_button)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.settings_button)
        self.layout.addWidget(self.transcript_text)

        self.play_button.clicked.connect(self.toggle_transcription)
        self.save_button.clicked.connect(self.save_transcription)
        self.settings_button.clicked.connect(self.request_settings)

    def toggle_transcription(self):
        if self.play_button.text() == 'Play':
            self.play_button.setIcon(QIcon('icons/stop.svg'))  # path to 'stop' icon
            self.transcriptionStarted.emit()
            self.play_button.setText('Stop')
        else:
            self.play_button.setIcon(QIcon('icons/play.svg'))  # path to 'play' icon
            self.transcriptionStopped.emit()
            self.play_button.setText('Play')

    def save_transcription(self):
        content = self.transcript_text.toPlainText()
        self.transcriptionSaved.emit(content)

    def request_settings(self):
        self.settingsRequested.emit()

    def set_style(self):
        self.setStyleSheet("""
            QPushButton {
                border-radius: 25px; /* Half of the button size for a circular look */
                background-color: #444;
                color: white;
            }
            QTextEdit {
                background-color: #333;
                color: white;
            }
        """)