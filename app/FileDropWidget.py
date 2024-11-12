import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QPen, QFont
import os
import shutil
from app.utils import resource_path

class FileDropWidget(QWidget):
    fileDropped = pyqtSignal(str)
    supported_file_types = (
        'mp3', 'wav', 'm4a', 'ogg', 'mp4', 'mkv', 'avi', 'mov', 'flac'
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        #self.setMinimumSize(50, 100)
        self.initUI()

    def initUI(self):
        self.layout = QVBoxLayout(self)
        self.label = QLabel("Drag audio/video files here or click to browse", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
        # Custom styling
        self.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
            }}
            QWidget {{
                border: 2px dashed #cccccc;
                padding-top: 50px;
                padding-bottom: 50px;
                padding-left: 3px;
                padding-right: 3px;
                font-weight: medium;
                background-image: url({resource_path('icons/dropdown_arrow.svg')});
            }}
            QPushButton:hover {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 gray, stop:1 darkgray
                );
            }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        event.accept()
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile() and url.toLocalFile().endswith(self.supported_file_types):
                event.acceptProposedAction()
            else:
                self.label.setText("Unsupported filetype.")
                event.accept()
    def dragLeaveEvent(self, event):

        self.label.setText("Drag audio/video files here or click to browse")

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        self.label.setText("Drag audio/video files here or click to browse")

        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            if file_path.endswith(self.supported_file_types):
                # Determine the app's directory and ensure the /Recordings directory exists
                app_directory = os.getcwd()
                recordings_path = os.path.join(app_directory, 'Recordings')
                os.makedirs(recordings_path, exist_ok=True)

                # Copy the file to the /Recordings directory
                try:
                    base_name = os.path.basename(file_path)
                    new_path = os.path.join(recordings_path, base_name)
                    shutil.copy2(file_path, new_path)
                    self.fileDropped.emit(new_path)  # Emit the new path
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to copy file: {e}")
                    event.ignore()
            else:
                event.ignore()


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.openFileDialog()

    def openFileDialog(self):
        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter("Audio/Video Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov *.flac)")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            file_path = file_dialog.selectedFiles()[0]
            if file_path.endswith(self.supported_file_types):
                # Determine the app's directory and ensure the /Recordings directory exists
                app_directory = os.getcwd()
                recordings_path = os.path.join(app_directory, 'Recordings')
                os.makedirs(recordings_path, exist_ok=True)

                # Copy the file to the /Recordings directory
                try:
                    base_name = os.path.basename(file_path)
                    new_path = os.path.join(recordings_path, base_name)
                    shutil.copy2(file_path, new_path)
                    self.fileDropped.emit(new_path)  # Emit the new path
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to copy file: {e}")
            else:
                self.showErrorMessage()
    def showErrorMessage(self):
        QMessageBox.critical(self, "Unsupported File Type",
                             "The file you dragged is not a supported audio/video file.")

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(Qt.GlobalColor.gray, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(10, 10, self.width()-20, self.height()-20)

        # Draw plus sign
        font = QFont()
        font.setPixelSize(32)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "+")

        super().paintEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("File Drop Test")
        self.setGeometry(100, 100, 600, 200)

        self.file_drop_widget = FileDropWidget(self)
        self.setCentralWidget(self.file_drop_widget)

        self.file_drop_widget.fileDropped.connect(self.file_dropped)

    def file_dropped(self, file_path):
        print(f"File dropped: {file_path}")


def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
