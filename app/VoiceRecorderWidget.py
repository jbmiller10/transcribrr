import sys
import os
import pyaudio
from pydub import AudioSegment
import wave
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import datetime
from collections import deque
from PyQt5.QtSvg import QSvgRenderer
from app.SVGToggleButton import *

import numpy as np


class VoiceRecorderWidget(QWidget):
    recordingCompleted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.initAudio()
        self.recording_thread = None
        self.is_recording = False
        self.is_paused = False
        self.elapsed_time = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateTimer)



    def initUI(self):
        self.layout = QVBoxLayout(self)
        self.layout.addStretch(1)

        # Record button
        #self.recordButton = QPushButton()
        #self.recordButton.setIcon(QIcon('icons/record.svg'))  # Record icon
        #self.recordButton.setFixedSize(80, 80)
        #self.recordButton.clicked.connect(self.toggleRecording)
        #self.layout.addWidget(self.recordButton, 0, Qt.AlignCenter)

        record_button_svg_files = {
            'record': 'icons/record.svg',
            'pause': 'icons/pause.svg',
        }
        # Record button - now using SvgButton
        self.recordButton = SVGToggleButton(record_button_svg_files)
        self.recordButton.setFixedSize(80, 80)
        self.recordButton.clicked.connect(self.toggleRecording)
        self.layout.addWidget(self.recordButton, 0, Qt.AlignCenter)

        # Timer display
        self.timerLabel = QLabel("00:00:00")
        self.layout.addWidget(self.timerLabel, 0, Qt.AlignCenter)

        # Save and Delete buttons in a horizontal layout
        buttonLayout = QHBoxLayout()
        self.saveButton = QPushButton("Save")
        self.saveButton.clicked.connect(self.saveRecording)
        self.saveButton.setEnabled(False)
        buttonLayout.addWidget(self.saveButton)

        self.deleteButton = QPushButton("Delete")
        self.deleteButton.clicked.connect(self.deleteRecording)
        self.deleteButton.setEnabled(False)
        buttonLayout.addWidget(self.deleteButton)
        self.statusLabel = QLabel("Ready to record")
        self.layout.addWidget(self.statusLabel, 0, Qt.AlignCenter)
        self.layout.addLayout(buttonLayout)
        self.layout.addStretch(1)


    def initAudio(self):
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100
        self.frames_per_buffer = 4096
        self.audio = pyaudio.PyAudio()

    def toggleRecording(self):
        if not self.is_recording:
            self.recordButton.set_svg('pause')  # Change to pause SVG
            self.startRecording()
        elif self.is_paused:
            self.recordButton.set_svg('record')  # Change to record SVG
            self.resumeRecording()
        else:
            self.recordButton.set_svg('record')  # Change to record SVG

            self.pauseRecording()


    def startRecording(self):
        self.is_recording = True
        self.is_paused = False
        #self.recordButton.setIcon(QIcon('icons/pause.svg'))  # Change to pause icon
        self.statusLabel.setText("Recording...")
        self.saveButton.setEnabled(True)  # Enable the save button when recording starts
        self.deleteButton.setEnabled(True)
        self.recording_thread = RecordingThread(self.audio, self.format, self.channels, self.rate, self.frames_per_buffer)
        self.recording_thread.startRecording()
        self.timer.start(1000)
    def pauseRecording(self):
        if self.recording_thread:
            self.is_paused = True
            #self.recordButton.setIcon(QIcon('icons/play.svg'))  # Change to play icon
            self.recordButton.set_svg('record')  # Change to record SVG
            #self.recordButton.svg_renderer.load('icons/record.svg')  # Change to pause SVG
            self.statusLabel.setText("Recording paused")
            self.recording_thread.pauseRecording()
            self.timer.stop()

    def resumeRecording(self):
        if self.recording_thread:
            self.is_paused = False
            #self.recordButton.setIcon(QIcon('icons/pause.svg'))  # Change back to pause icon
            #self.recordButton.svg_renderer.load('icons/pause.svg')  # Change to pause SVG
            self.statusLabel.setText("Recording...")
            self.recordButton.set_svg('pause')  # Change to record SVG
            self.recording_thread.resumeRecording()
            self.timer.start(1000)

    def saveRecording(self):
        if self.recording_thread:
            #self.recordButton.setIcon(QIcon('icons/record.svg'))  # Change back to record icon

            #self.recordButton.svg_renderer.load('icons/record.svg')  # Change back to record SVG
            self.is_recording = False
            self.is_paused = False
            self.recordButton.set_svg('record')  # Change to record SVG
            self.recording_thread.stopRecording()
            self.recording_thread.wait()
            file_name = self.recording_thread.saveRecording()
            self.statusLabel.setText("Ready to record")
            self.saveButton.setEnabled(False)  # Disable the save button after saving
            self.deleteButton.setEnabled(False)
            self.recordingCompleted.emit(file_name)
            self.resetTimer()
    def deleteRecording(self):
        if self.recording_thread:
            #self.recordButton.setIcon(QIcon('icons/record.svg'))  # Change back to record icon
            #self.recordButton.svg_renderer.load('icons/record.svg')  # Change back to record SVG
            self.statusLabel.setText("Ready to record")
            self.recordButton.set_svg('record')  # Change to record SVG
            self.is_recording = False
            self.is_paused = False
            self.recording_thread.stopRecording()
            self.recording_thread.wait()
            self.recording_thread.frames.clear()  # Clear the recorded frames
            self.deleteButton.setEnabled(False)  # Disable delete button after deletion
            self.saveButton.setEnabled(False)  # Disable save button after deletion
            self.resetTimer()
    def updateTimer(self):
        self.elapsed_time += 1
        time_str = str(datetime.timedelta(seconds=self.elapsed_time))
        self.timerLabel.setText(time_str)

    def resetTimer(self):
        self.timer.stop()
        self.elapsed_time = 0
        self.timerLabel.setText("00:00:00")

class RecordingThread(QThread):
    def __init__(self, audio_instance, format, channels, rate, frames_per_buffer, parent=None):
        super().__init__(parent)
        self.audio = audio_instance
        self.format = format
        self.channels = channels
        self.rate = rate
        self.frames_per_buffer = frames_per_buffer
        self.frames = deque()
        self.is_recording = False
        self.is_paused = False

    def run(self):
        self.stream = self.audio.open(format=self.format, channels=self.channels,
                                      rate=self.rate, input=True, frames_per_buffer=self.frames_per_buffer)
        while self.is_recording:
            if not self.is_paused:
                data = self.stream.read(self.frames_per_buffer, exception_on_overflow=False)
                self.frames.append(data)
        self.stream.stop_stream()
        self.stream.close()

    def pauseRecording(self):
        if self.is_recording:
            self.is_paused = True

    def resumeRecording(self):
        if self.is_recording:
            self.is_paused = False

    def startRecording(self):
        self.is_recording = True
        self.start()

    def stopRecording(self):
        self.is_recording = False
        self.wait()

    def saveRecording(self):
        recordings_dir = "Recordings"
        os.makedirs(recordings_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        wav_file_name = os.path.join(recordings_dir, f"Recording-{timestamp}.wav")
        final_file_name = os.path.join(recordings_dir, f"Recording-{timestamp}.mp3")  # or .ogg for OGG format

        # Save as WAV
        wf = wave.open(wav_file_name, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(44100)
        wf.writeframes(b''.join(self.frames))
        wf.close()

        # Convert to MP3
        audio = AudioSegment.from_wav(wav_file_name)
        audio.export(final_file_name, format="mp3")  # maybe change to format="ogg"

        os.remove(wav_file_name)  #Cleanup the WAV file
        self.frames.clear()
        return final_file_name

def main():
    app = QApplication(sys.argv)
    mainWindow = QMainWindow()
    recorderWidget = VoiceRecorderWidget()

    mainWindow.setCentralWidget(recorderWidget)
    mainWindow.setWindowTitle("Voice Recorder")
    mainWindow.resize(300, 200)
    mainWindow.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()