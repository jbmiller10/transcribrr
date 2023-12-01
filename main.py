import sys
import re
import yt_dlp
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGridLayout, QWidget, QLabel,
                             QPushButton, QComboBox, QLineEdit, QFileDialog, QTextEdit,
                             QMessageBox, QStatusBar, QAction, QTableWidgetItem, QHBoxLayout, QDoubleSpinBox, QSpinBox,
                             QCheckBox, QTableWidget,QStyleFactory)
from PyQt5.QtCore import QThread, pyqtSignal,Qt
from moviepy.editor import VideoFileClip
import requests
import os
import traceback
import torch
from pydub import AudioSegment
import whisperx
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox
import keyring
import json

if __name__ == "__main__":
    app = QApplication(sys.argv)
    #app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt5', palette=qdarkstyle.LightPalette))
    app.setStyle(QStyleFactory.create("Fusion"))
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec_())