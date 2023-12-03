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

class TranscodingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    temp_file_created = pyqtSignal(str)

    def __init__(self, file_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path

    def run(self):
        try:
            self.update_progress.emit('Starting conversion...')
            if self.is_video_file(self.file_path):
                self.update_progress.emit('Converting video to audio...')
                audio_file_path = self.extract_audio_from_video(self.file_path)
            elif self.is_audio_file(self.file_path):
                if not self.is_wav_file(self.file_path):
                    self.update_progress.emit('Converting audio to mono wav format...')
                    audio_file_path = self.convert_audio_to_mono_wav(self.file_path)
                else:
                    self.update_progress.emit('Audio file is already in wav format.')
                    audio_file_path = self.file_path
            else:
                raise ValueError("Unsupported file type.")

            if audio_file_path:
                self.completed.emit(audio_file_path)  # Emit the path of the processed audio file
                self.update_progress.emit('Conversion completed.')
            else:
                raise FileNotFoundError("No audio file path was set.")

        except ValueError as e:
            error_message = f'Unsupported file type error: {e}'
            self.handle_error(error_message)
        except FileNotFoundError as e:
            error_message = f'File not found error: {e}'
            self.handle_error(error_message)
        except Exception as e:
            error_message = f'General error during conversion: {e}'
            self.handle_error(error_message)

    def handle_error(self, error_message):
        print(error_message)
        traceback.print_exc()
        self.error.emit(error_message)

    @staticmethod
    def is_video_file(file_path):
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov','webp']
        file_extension = os.path.splitext(file_path)[1].lower()
        return file_extension in video_extensions

    @staticmethod
    def is_audio_file(file_path):
        audio_extensions = ['.mp3', '.wav', '.aac', '.flac', '.ogg']
        file_extension = os.path.splitext(file_path)[1].lower()
        return file_extension in audio_extensions

    @staticmethod
    def is_wav_file(file_path):
        return file_path.lower().endswith('.wav')

    def extract_audio_from_video(self, video_file_path):
        try:
            print(f'TranscodingThread: Attempting to extract audio from: {video_file_path}')
            clip = VideoFileClip(video_file_path)
            audio_file_path = video_file_path.rsplit('.', 1)[0] + '.wav'
            print('TranscodingThread: Before write_audiofile')
            clip.audio.write_audiofile(audio_file_path, codec='pcm_s16le')
            print(f'TranscodingThread: Audio extracted to: {audio_file_path}')
            clip.close()
            return audio_file_path
        except Exception as e:
            print(f'TranscodingThread: Error while extracting audio: {e}')
            traceback.print_exc()
            raise e  # Re-raise the exception to ensure it's caught by the error handling in run()

    def convert_audio_to_mono_wav(self, audio_file_path):
        audio = AudioSegment.from_file(audio_file_path)
        audio = audio.set_channels(1)  # Convert to mono
        wav_file_path = audio_file_path.rsplit('.', 1)[0] + '_mono.wav'
        audio.export(wav_file_path, format='wav')
        self.temp_file_created.emit(audio_file_path)  # Track the temporary file
        return wav_file_path