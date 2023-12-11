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

from app.TextEditor import TextEditor


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
        self.upper_transcription_toolbar = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(QIcon('icons/play.svg'))  # path to 'play' icon
        self.play_button.setFixedSize(50, 50)  # Adjust size as needed
        self.upper_transcription_toolbar.addWidget(self.play_button)
        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon('icons/save.svg'))  # path to 'save' icon
        self.save_button.setFixedSize(50, 50)  # Adjust size as needed
        self.upper_transcription_toolbar.addWidget(self.save_button)

        self.horizontal_spacer = QWidget()
        self.top_toolbar = QHBoxLayout()
        self.horizontal_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.settings_button = QPushButton()
        self.settings_button.setIcon(QIcon('icons/settings.svg'))  # path to 'settings' icon
        self.settings_button.setIconSize(QSize(25,25))
        self.settings_button.setFixedSize(30, 30)  # Adjust size as needed
        self.upper_transcription_toolbar.addWidget(self.settings_button)
        self.transcript_text = TextEditor()
        self.top_toolbar.addWidget(self.horizontal_spacer)
        self.top_toolbar.addWidget(self.settings_button)
        self.layout.addLayout(self.top_toolbar)
        self.upper_transcription_toolbar.addWidget(self.transcription_type_combo)
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