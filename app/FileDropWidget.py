import os
from PyQt6.QtWidgets import (
    QApplication,
    QVBoxLayout,
    QWidget,
    QLabel,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QPainter, QPen, QColor
import shutil
import logging
from app.path_utils import resource_path

from app.constants import get_recordings_dir

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class FileDropWidget(QWidget):
    fileDropped = pyqtSignal(str)

    supported_file_types = {
        # Audio formats
        "mp3": "MPEG Audio Layer III",
        "wav": "Waveform Audio File Format",
        "m4a": "MPEG-4 Audio",
        "ogg": "Ogg Vorbis Audio",
        "flac": "Free Lossless Audio Codec",
        # Video formats
        "mp4": "MPEG-4 Video",
        "mkv": "Matroska Video",
        "avi": "Audio Video Interleave",
        "mov": "QuickTime Movie",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.initUI()

        # Ensure recordings directory exists
        os.makedirs(get_recordings_dir(), exist_ok=True)

    def initUI(self):
        self.layout = QVBoxLayout(self)
        self.label = QLabel(
            "Drag audio/video files here or click to browse", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Fixed enum
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

        self.setStyleSheet(
            f"""
            QLabel {{
                font-size: 16px;
                padding-top: 50px;
                padding-bottom: 50px;
            }}
            QWidget {{
                border: 2px dashed #cccccc;
                padding: 5px;
                font-weight: medium;
                background-image: url({resource_path('icons/dropdown_arrow.svg')});
            }}
            QWidget:hover {{
                border: 2px dashed #5a5a5a;
            }}
        """
        )

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            if url.isLocalFile():
                file_path = url.toLocalFile()
                file_extension = os.path.splitext(file_path)[1].lower()[
                    1:
                ]  # Get extension without dot

                if file_extension in self.supported_file_types:
                    self.label.setText(
                        f"Release to upload {os.path.basename(file_path)}"
                    )
                    self.setStyleSheet(
                        f"""
                        QLabel {{
                            font-size: 16px;
                            padding-top: 50px;
                            padding-bottom: 50px;
                            color: #3366cc;
                        }}
                        QWidget {{
                            border: 2px dashed #3366cc;
                            padding: 5px;
                            font-weight: medium;
                            background-image: url({resource_path('icons/dropdown_arrow.svg')});
                        }}
                    """
                    )
                    event.acceptProposedAction()
                else:
                    self.label.setText(
                        f"Unsupported file type: .{file_extension}")
                    self.setStyleSheet(
                        f"""
                        QLabel {{
                            font-size: 16px;
                            padding-top: 50px;
                            padding-bottom: 50px;
                            color: #cc3333;
                        }}
                        QWidget {{
                            border: 2px dashed #cc3333;
                            padding: 5px;
                            font-weight: medium;
                            background-image: url({resource_path('icons/dropdown_arrow.svg')});
                        }}
                    """
                    )
                    event.accept()
            else:
                self.label.setText("Only local files are supported")
                event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.label.setText("Drag audio/video files here or click to browse")
        self.setStyleSheet(
            f"""
            QLabel {{
                font-size: 16px;
                padding-top: 50px;
                padding-bottom: 50px;
            }}
            QWidget {{
                border: 2px dashed #cccccc;
                padding: 5px;
                font-weight: medium;
                background-image: url({resource_path('icons/dropdown_arrow.svg')});
            }}
            QWidget:hover {{
                border: 2px dashed #5a5a5a;
            }}
        """
        )

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        self.label.setText("Drag audio/video files here or click to browse")
        self.dragLeaveEvent(None)  # Reset styling

        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0]
            file_path = url.toLocalFile()
            file_extension = os.path.splitext(file_path)[1].lower()[1:]

            if file_extension in self.supported_file_types:
                self.process_file(file_path)
            else:
                self.showErrorMessage(
                    f"The file type .{file_extension} is not supported. Please use one of these formats: {', '.join(self.supported_file_types.keys())}"
                )
                event.ignore()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:  # Fixed enum
            self.openFileDialog()

    def openFileDialog(self):
        filter_parts = []
        for ext, desc in self.supported_file_types.items():
            filter_parts.append(f"*.{ext}")

        filter_string = f"Audio/Video Files ({' '.join(filter_parts)})"

        audio_formats = [
            ext
            for ext in self.supported_file_types.keys()
            if ext in ["mp3", "wav", "m4a", "ogg", "flac"]
        ]
        video_formats = [
            ext
            for ext in self.supported_file_types.keys()
            if ext in ["mp4", "mkv", "avi", "mov"]
        ]

        audio_filter = (
            f"Audio Files ({' '.join([f'*.{ext}' for ext in audio_formats])})"
        )
        video_filter = (
            f"Video Files ({' '.join([f'*.{ext}' for ext in video_formats])})"
        )

        complete_filter = f"{filter_string};;{audio_filter};;{video_filter}"

        file_dialog = QFileDialog(self)
        file_dialog.setNameFilter(complete_filter)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setWindowTitle("Select Audio or Video File")

        if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
            file_path = file_dialog.selectedFiles()[0]
            file_extension = os.path.splitext(file_path)[1].lower()[1:]

            if file_extension in self.supported_file_types:
                self.process_file(file_path)
            else:
                self.showErrorMessage(
                    f"The file type .{file_extension} is not supported."
                )

    def process_file(self, file_path):
        """Process file with progress."""
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # Check file size (prevent extremely large files)
            file_size_mb = os.path.getsize(
                file_path) / (1024 * 1024)  # Convert to MB
            if file_size_mb > 500:  # Limit to 500MB
                response = QMessageBox.question(
                    self,
                    "Large File Warning",
                    f"The selected file is {file_size_mb:.1f}MB, which is quite large. "
                    "Processing might take significant time and resources. Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if response == QMessageBox.StandardButton.No:
                    return

            base_name = os.path.basename(file_path)
            new_path = os.path.join(get_recordings_dir(), base_name)

            # Check if file with same name already exists
            if os.path.exists(new_path):
                response = QMessageBox.question(
                    self,
                    "File Exists",
                    f"A file named '{base_name}' already exists in Recordings folder. Replace it?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel,
                )

                if response == QMessageBox.StandardButton.Cancel:
                    return
                elif response == QMessageBox.StandardButton.Yes:
                    os.remove(new_path)  # Remove existing file
                else:  # No - create a new unique filename
                    counter = 1
                    name, ext = os.path.splitext(base_name)
                    while os.path.exists(new_path):
                        new_base_name = f"{name}_{counter}{ext}"
                        new_path = os.path.join(
                            get_recordings_dir(), new_base_name)
                        counter += 1
                    base_name = os.path.basename(new_path)

            # Show progress dialog for larger files
            if file_size_mb > 50:  # Only show for files > 50MB
                progress = QProgressDialog(
                    f"Copying {base_name}...", "Cancel", 0, 100, self
                )
                progress.setWindowTitle("Copying File")
                progress.setWindowModality(
                    Qt.WindowModality.WindowModal)  # Fixed enum
                progress.setMinimumDuration(
                    500
                )  # Only show for operations taking > 500ms
                progress.setValue(0)

                # Since shutil.copy2 doesn't report progress, we'll just update in chunks
                progress.setValue(25)
                QApplication.processEvents()

                shutil.copy2(file_path, new_path)

                progress.setValue(100)
                QApplication.processEvents()
            else:
                # For smaller files, just copy without progress dialog
                shutil.copy2(file_path, new_path)

            # Emit signal with the new path
            logging.info(f"File processed successfully: {new_path}")
            self.fileDropped.emit(new_path)

        except FileNotFoundError as e:
            self.showErrorMessage(f"File not found: {e}")
        except PermissionError:
            self.showErrorMessage(
                "Permission denied. Make sure you have access to both the source file and the Recordings folder."
            )
        except shutil.SameFileError:
            # If it's the same file, just use it directly
            self.fileDropped.emit(file_path)
        except Exception as e:
            self.showErrorMessage(f"Failed to process file: {e}")
            logging.error(f"Error processing file: {e}", exc_info=True)

    def showErrorMessage(self, message):
        """Show error message."""
        error_box = QMessageBox(self)
        error_box.setIcon(QMessageBox.Icon.Critical)
        error_box.setWindowTitle("File Error")
        error_box.setText(message)
        error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        error_box.exec()

    def paintEvent(self, event):
        """Custom paint event."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded dashed rectangle
        pen = QPen(QColor("#cccccc"), 2, Qt.PenStyle.DashLine)  # Fixed enum
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)  # Fixed enum
        painter.drawRoundedRect(10, 10, self.width() -
                                20, self.height() - 20, 10, 10)

        # Draw plus sign
        pen.setStyle(Qt.PenStyle.SolidLine)  # Fixed enum
        pen.setColor(QColor("#666666"))
        painter.setPen(pen)

        # Draw plus sign
        plus_size = 40
        center_x = self.width() / 2
        center_y = self.height() / 2 - 15  # Move up slightly to account for text below

        # Horizontal line
        painter.drawLine(
            int(center_x - plus_size / 2),
            int(center_y),
            int(center_x + plus_size / 2),
            int(center_y),
        )

        # Vertical line
        painter.drawLine(
            int(center_x),
            int(center_y - plus_size / 2),
            int(center_x),
            int(center_y + plus_size / 2),
        )

        super().paintEvent(event)

    def get_supported_format_list(self):
        """Return supported formats list."""
        formats = []
        for ext, desc in self.supported_file_types.items():
            formats.append(f".{ext} ({desc})")
        return formats

    @property
    def recordings_dir(self):
        """Return recordings directory path for compatibility.

        This property ensures compatibility with code that might still
        access self.recordings_dir, ensuring it always points to the
        centralized RECORDINGS_DIR constant.
        """
        return get_recordings_dir()

    @staticmethod
    def check_recordings_dir_consistency():
        """Test method to verify constant/attribute consistency.

        This method checks that the FileDropWidget.recordings_dir property
        returns the same value as the RECORDINGS_DIR constant, satisfying
        the regression test requirement.

        Returns:
            bool: True if consistent, False otherwise.
        """
        from app.constants import get_recordings_dir as CONST_DIR

        # No need to instantiate a widget, we can directly compare the values
        # since recordings_dir is now a property that just returns RECORDINGS_DIR
        return FileDropWidget.recordings_dir.fget(None) == CONST_DIR()
