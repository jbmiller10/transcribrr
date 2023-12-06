import sys
import os
import pyaudio
import wave
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import datetime
from collections import deque
import numpy as np

class VoiceRecorderWidget(QWidget):
    recordingCompleted = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()
        self.initAudio()
        self.recording_thread = None
        self.is_recording = False

    def initUI(self):
        self.layout = QVBoxLayout(self)

        self.recordButton = QPushButton()
        self.recordButton.setIcon(QIcon('icons/record.svg'))  # path to 'record' icon
        self.recordButton.setFixedSize(80, 80)  # Big red circular button
        self.recordButton.clicked.connect(self.toggleRecording)

        self.recordButton.setStyleSheet("""
            QPushButton {
                border-radius: 40px; /* Half of the button size for a circular look */
                background-color: #FF0000; /* Red color */
            }
        """)

        self.layout.addWidget(self.recordButton)

    def initAudio(self):
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 44100
        self.frames_per_buffer = 4096
        self.audio = pyaudio.PyAudio()

    def toggleRecording(self):
        if not self.is_recording:
            self.startRecording()
        else:
            self.stopRecording()

    def startRecording(self):
        self.recordButton.setIcon(QIcon('icons/stop.svg'))  # path to 'stop' icon
        self.stream = self.audio.open(format=self.format, channels=self.channels,
                                      rate=self.rate, input=True,
                                      frames_per_buffer=self.frames_per_buffer)
        self.is_recording = True
        self.recording_thread = RecordingThread(self.audio)
        self.recording_thread.startRecording()

    def stopRecording(self):
        if self.recording_thread:
            self.recording_thread.stopRecording()
            file_name = self.recording_thread.saveRecording()
            QMessageBox.information(self, "Recording", f"Recording saved as: {file_name}")
            self.recordButton.setIcon(QIcon('icons/record.svg'))  # path to 'record' icon
            self.is_recording = False
            self.recordingCompleted.emit(file_name)



class RecordingThread(QThread):
    def __init__(self, audio_instance, parent=None):
        super().__init__(parent)
        self.audio = audio_instance
        self.frames = deque()
        self.is_recording = False

    def run(self):
        while self.is_recording:
            data = self.stream.read(4096)
            self.frames.append(data)

    def startRecording(self):
        self.stream = self.audio.open(format=pyaudio.paInt16, channels=1,
                                      rate=44100, input=True, frames_per_buffer=4096)
        self.is_recording = True
        self.start()

    def stopRecording(self):
        self.is_recording = False
        self.stream.stop_stream()
        self.stream.close()
        self.wait()

    def saveRecording(self):
        recordings_dir = "Recordings"
        os.makedirs(recordings_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        file_name = os.path.join(recordings_dir, f"Recording-{timestamp}.wav")

        # Assuming the audio is mono and the sample rate is 44100 Hz
        wf = wave.open(file_name, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(44100)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        self.frames.clear()
        return file_name

# Test the VoiceRecorderWidget
if __name__ == "__main__":
    app = QApplication(sys.argv)
    recorder = VoiceRecorderWidget()
    recorder.show()
    sys.exit(app.exec_())