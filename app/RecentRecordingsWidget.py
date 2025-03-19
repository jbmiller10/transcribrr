import traceback
import datetime
import os
import logging
from PyQt6.QtCore import (
    pyqtSignal, QSize, Qt, QPropertyAnimation, QEasingCurve, QSortFilterProxyModel, QTimer,
    QThread, QUrl
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QWidget, QLabel, QListWidget, QMenu, QListWidgetItem,
    QHBoxLayout, QPushButton, QLineEdit, QComboBox, QInputDialog, QApplication, QSplitter,
    QFrame, QProgressDialog, QFileDialog, QToolButton, QToolBar, QStatusBar, QSizePolicy
)
from PyQt6.QtGui import QIcon, QFont, QColor, QDesktopServices, QAction
from app.RecordingListItem import RecordingListItem
from app.utils import resource_path, create_backup, format_time_duration
from app.database import (
    create_connection, get_all_recordings, create_db, create_recording,
    update_recording, delete_recording
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SearchWidget(QWidget):
    """Widget for searching and filtering recordings."""
    searchTextChanged = pyqtSignal(str)
    filterCriteriaChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Search field
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search recordings...")
        self.search_field.textChanged.connect(self.searchTextChanged.emit)
        self.search_field.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)

        # Filter dropdown
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Has Transcript", "No Transcript", "Recent (24h)", "This Week"])
        self.filter_combo.currentTextChanged.connect(self.filterCriteriaChanged.emit)

        # Layout
        layout.addWidget(self.search_field, 3)
        layout.addWidget(self.filter_combo, 1)

    def clear_search(self):
        """Clear the search field."""
        self.search_field.clear()

    def get_search_text(self):
        """Get current search text."""
        return self.search_field.text()

    def get_filter_criteria(self):
        """Get current filter criteria."""
        return self.filter_combo.currentText()


class BatchProcessWorker(QThread):
    """Worker thread for batch processing recordings."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, recordings, process_type, parent=None):
        super().__init__(parent)
        self.recordings = recordings
        self.process_type = process_type
        self.is_canceled = False

    def run(self):
        try:
            total = len(self.recordings)
            completed = 0

            for recording in self.recordings:
                if self.is_canceled:
                    self.finished.emit(False, "Operation canceled")
                    return

                # Process recording based on type
                if self.process_type == "transcribe":
                    # Placeholder for actual transcription
                    # This would call the transcription code
                    self.progress.emit(int((completed / total) * 100), f"Transcribing {recording.filename}")

                elif self.process_type == "process":
                    # Placeholder for GPT processing
                    # This would call the GPT processing code
                    self.progress.emit(int((completed / total) * 100), f"Processing {recording.filename}")

                # Simulate processing time for demo
                self.msleep(500)

                completed += 1

            self.finished.emit(True, f"Completed {self.process_type} for {completed} recordings")

        except Exception as e:
            error_msg = f"Error in batch {self.process_type}: {str(e)}"
            logging.error(error_msg, exc_info=True)
            self.finished.emit(False, error_msg)

    def cancel(self):
        """Cancel the operation."""
        self.is_canceled = True


class RecentRecordingsWidget(QWidget):
    recordingSelected = pyqtSignal(str)
    recordButtonPressed = pyqtSignal()
    recordingItemSelected = pyqtSignal(RecordingListItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(5)

        # Toolbar
        self.init_toolbar()

        # Header with title and action buttons
        self.header_layout = QHBoxLayout()

        self.header_label = QLabel("Recent Recordings")
        self.header_label.setObjectName("RecentRecordingHeader")
        self.header_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.header_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))

        # Add refresh button
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(QIcon(resource_path('icons/refresh.svg')))
        self.refresh_button.setToolTip("Refresh Recordings")
        self.refresh_button.setFixedSize(30, 30)
        self.refresh_button.clicked.connect(self.refresh_recordings)

        self.header_layout.addWidget(self.header_label, 1)
        self.header_layout.addWidget(self.refresh_button, 0)

        self.layout.addLayout(self.header_layout)

        # Search and filter widget
        self.search_widget = SearchWidget()
        self.search_widget.searchTextChanged.connect(self.filter_recordings)
        self.search_widget.filterCriteriaChanged.connect(self.filter_recordings)
        self.layout.addWidget(self.search_widget)

        # Recordings list
        self.recordings_list = QListWidget()
        self.recordings_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.recordings_list.itemClicked.connect(self.recording_clicked)

        # Empty state message
        self.empty_label = QLabel("No recordings found. Upload or record audio to get started.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888; font-style: italic;")
        self.empty_label.setVisible(False)

        self.layout.addWidget(self.recordings_list)
        self.layout.addWidget(self.empty_label)

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.layout.addWidget(self.status_bar)
        self.status_bar.hide()  # Initially hidden

        # Set up right-click context menu for recordings
        self.recordings_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.recordings_list.customContextMenuRequested.connect(self.showRightClickMenu)

        # Batch processing worker
        self.batch_worker = None
        self.progress_dialog = None

        # Load recordings initially
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_recording_display)
        self.timer.start(60000)  # Update relative times every minute

        # Set up styling
        self.style_updated()

    def init_toolbar(self):
        """Initialize toolbar with action buttons."""
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setMovable(False)

        # New Folder action
        new_folder_action = QAction(QIcon(resource_path('icons/folder.svg')), "New Folder", self)
        new_folder_action.setToolTip("Create new folder for organizing recordings")
        new_folder_action.triggered.connect(self.create_new_folder)
        toolbar.addAction(new_folder_action)

        # Batch actions dropdown
        batch_button = QToolButton()
        batch_button.setText("Batch")
        batch_button.setIcon(QIcon(resource_path('icons/batch.svg')))
        batch_button.setToolTip("Batch operations")
        batch_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        batch_menu = QMenu()

        # Batch transcribe action
        batch_transcribe_action = QAction("Transcribe Selected", self)
        batch_transcribe_action.triggered.connect(lambda: self.batch_process("transcribe"))
        batch_menu.addAction(batch_transcribe_action)

        # Batch GPT process action
        batch_process_action = QAction("Process with GPT", self)
        batch_process_action.triggered.connect(lambda: self.batch_process("process"))
        batch_menu.addAction(batch_process_action)

        # Batch export action
        batch_export_action = QAction("Export Selected", self)
        batch_export_action.triggered.connect(self.batch_export)
        batch_menu.addAction(batch_export_action)

        batch_button.setMenu(batch_menu)
        toolbar.addWidget(batch_button)

        # Add separator
        toolbar.addSeparator()

        # Sort options
        sort_button = QToolButton()
        sort_button.setText("Sort")
        sort_button.setIcon(QIcon(resource_path('icons/sort.svg')))
        sort_button.setToolTip("Sort recordings")
        sort_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        sort_menu = QMenu()

        # Sort by date (newest)
        sort_date_new_action = QAction("Date (Newest First)", self)
        sort_date_new_action.triggered.connect(lambda: self.sort_recordings("date", False))
        sort_menu.addAction(sort_date_new_action)

        # Sort by date (oldest)
        sort_date_old_action = QAction("Date (Oldest First)", self)
        sort_date_old_action.triggered.connect(lambda: self.sort_recordings("date", True))
        sort_menu.addAction(sort_date_old_action)

        # Sort by name (A-Z)
        sort_name_az_action = QAction("Name (A-Z)", self)
        sort_name_az_action.triggered.connect(lambda: self.sort_recordings("name", False))
        sort_menu.addAction(sort_name_az_action)

        # Sort by name (Z-A)
        sort_name_za_action = QAction("Name (Z-A)", self)
        sort_name_za_action.triggered.connect(lambda: self.sort_recordings("name", True))
        sort_menu.addAction(sort_name_za_action)

        # Sort by duration
        sort_duration_action = QAction("Duration", self)
        sort_duration_action.triggered.connect(lambda: self.sort_recordings("duration", False))
        sort_menu.addAction(sort_duration_action)

        sort_button.setMenu(sort_menu)
        toolbar.addWidget(sort_button)

        # Import from file
        import_action = QAction(QIcon(resource_path('icons/import.svg')), "Import", self)
        import_action.setToolTip("Import recordings from file system")
        import_action.triggered.connect(self.import_recordings)
        toolbar.addAction(import_action)

        # Spacer to push help to right side
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)  # Fixed: QSizePolicy instead of QSize
        toolbar.addWidget(spacer)

        # Help action
        help_action = QAction(QIcon(resource_path('icons/help.svg')), "Help", self)
        help_action.setToolTip("Show help for recordings")
        help_action.triggered.connect(self.show_help)
        toolbar.addAction(help_action)

        self.layout.addWidget(toolbar)
    def style_updated(self):
        """Update widget styling."""
        self.recordings_list.setStyleSheet("""
            QListWidget {
                border: none;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #eee;
                padding: 4px;
            }
            QListWidget::item:selected {
                background-color: #f0f0f0;
                color: #000;
            }
            QListWidget::item:hover {
                background-color: #f8f8f8;
            }
        """)

    def create_new_folder(self):
        """Create a new folder for organizing recordings."""
        folder_name, ok = QInputDialog.getText(
            self, "Create Folder", "Enter folder name:", QLineEdit.EchoMode.Normal, "New Folder"
        )

        if ok and folder_name:
            # This implementation would need to be expanded to actually support folders in the UI
            # For now, just show a message indicating this is a placeholder
            QMessageBox.information(
                self, "Feature Coming Soon",
                f"Creating folder: {folder_name}\n\nThis feature will be implemented in a future update."
            )

    def batch_process(self, process_type):
        """Process multiple recordings in batch."""
        # Get selected recordings
        selected_items = self.recordings_list.selectedItems()

        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select recordings to process.")
            return

        # Get corresponding RecordingListItem widgets
        selected_recordings = []
        for item in selected_items:
            recording_widget = self.recordings_list.itemWidget(item)
            selected_recordings.append(recording_widget)

        # Confirm with user
        action_text = "transcribe" if process_type == "transcribe" else "process with GPT"
        confirm = QMessageBox.question(
            self,
            f"Batch {action_text.capitalize()}",
            f"Are you sure you want to {action_text} {len(selected_recordings)} recording(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        # Create and configure progress dialog
        self.progress_dialog = QProgressDialog(
            f"Starting batch {action_text}...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle(f"Batch {action_text.capitalize()}")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.canceled.connect(self.cancel_batch_process)

        # Create and start worker thread
        self.batch_worker = BatchProcessWorker(selected_recordings, process_type)
        self.batch_worker.progress.connect(self.update_batch_progress)
        self.batch_worker.finished.connect(self.on_batch_process_finished)
        self.batch_worker.start()

        # Show progress dialog
        self.progress_dialog.show()

    def cancel_batch_process(self):
        """Cancel the current batch process."""
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.cancel()

    def update_batch_progress(self, value, message):
        """Update batch process progress."""
        if self.progress_dialog:
            self.progress_dialog.setValue(value)
            self.progress_dialog.setLabelText(message)

    def on_batch_process_finished(self, success, message):
        """Handle batch process completion."""
        if self.progress_dialog:
            self.progress_dialog.setValue(100)
            self.progress_dialog.setLabelText(message)

            # Allow user to read the message
            QTimer.singleShot(2000, self.progress_dialog.close)

        if success:
            self.show_status_message(message, 5000)
        else:
            QMessageBox.warning(self, "Batch Process", message)

        # Refresh recordings
        self.refresh_recordings()

    def batch_export(self):
        """Export multiple recordings in batch."""
        # Get selected recordings
        selected_items = self.recordings_list.selectedItems()

        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select recordings to export.")
            return

        # Ask for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", os.getcwd(),
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks
        )

        if not export_dir:
            return

        # Process each selected recording
        exported_count = 0
        error_count = 0

        progress = QProgressDialog(
            "Preparing export...", "Cancel", 0, len(selected_items), self
        )
        progress.setWindowTitle("Batch Export")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        for i, item in enumerate(selected_items):
            if progress.wasCanceled():
                break

            recording_widget = self.recordings_list.itemWidget(item)
            file_path = recording_widget.file_path
            file_name = os.path.basename(file_path)

            progress.setValue(i)
            progress.setLabelText(f"Exporting {file_name}...")

            # Create export path
            export_path = os.path.join(export_dir, file_name)

            # Check if file exists
            if os.path.exists(export_path):
                # Append number to filename
                name, ext = os.path.splitext(file_name)
                counter = 1
                while os.path.exists(export_path):
                    export_path = os.path.join(export_dir, f"{name}_{counter}{ext}")
                    counter += 1

            try:
                # Copy file
                import shutil
                shutil.copy2(file_path, export_path)
                exported_count += 1
            except Exception as e:
                logging.error(f"Error exporting {file_path}: {e}")
                error_count += 1

        progress.setValue(len(selected_items))

        # Show results
        if error_count == 0:
            QMessageBox.information(
                self, "Export Complete",
                f"Successfully exported {exported_count} recording(s) to {export_dir}"
            )
        else:
            QMessageBox.warning(
                self, "Export Complete with Errors",
                f"Exported {exported_count} recording(s) to {export_dir}\n"
                f"Failed to export {error_count} recording(s). See log for details."
            )

    def sort_recordings(self, sort_by, reverse=False):
        """Sort recordings by various criteria."""
        items = []

        # Get all items from the list
        for i in range(self.recordings_list.count()):
            items.append(self.recordings_list.item(i))

        # Sort items based on criteria
        if sort_by == "date":
            items.sort(
                key=lambda item: datetime.datetime.strptime(
                    item.data(Qt.ItemDataRole.UserRole)['date_created'],
                    "%Y-%m-%d %H:%M:%S"
                ),
                reverse=reverse
            )
        elif sort_by == "name":
            items.sort(
                key=lambda item: item.data(Qt.ItemDataRole.UserRole)['filename'].lower(),
                reverse=reverse
            )
        elif sort_by == "duration":
            # Parse duration string (HH:MM:SS) to sort properly
            def parse_duration(duration_str):
                try:
                    parts = duration_str.split(':')
                    if len(parts) == 3:  # HH:MM:SS
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    elif len(parts) == 2:  # MM:SS
                        return int(parts[0]) * 60 + int(parts[1])
                    else:
                        return 0
                except:
                    return 0

            items.sort(
                key=lambda item: parse_duration(item.data(Qt.ItemDataRole.UserRole)['duration']),
                reverse=reverse
            )

        # Clear and re-add items in sorted order
        self.recordings_list.clear()
        for item in items:
            self.recordings_list.addItem(item)

            # Re-add the widget
            metadata = item.data(Qt.ItemDataRole.UserRole)
            recording_widget = RecordingListItem(
                metadata['id'], metadata['filename'], metadata['full_path'],
                metadata['date_created'], metadata['duration'], "", ""  # Raw/processed text will be loaded when needed
            )
            self.recordings_list.setItemWidget(item, recording_widget)

        # Update the UI
        self.update_empty_state()

        # Show status message
        sort_name = {
            "date": "date",
            "name": "name",
            "duration": "duration"
        }.get(sort_by, sort_by)

        direction = "descending" if reverse else "ascending"
        self.show_status_message(f"Sorted by {sort_name} ({direction})")

    def import_recordings(self):
        """Import recordings from external files."""
        # Open file dialog to select audio/video files
        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle("Import Audio/Video Files")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter(
            "Audio/Video Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov *.flac)"
        )

        if file_dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        # Get selected files
        selected_files = file_dialog.selectedFiles()

        if not selected_files:
            return

        # Process each file
        imported_count = 0
        error_count = 0

        progress = QProgressDialog(
            "Importing files...", "Cancel", 0, len(selected_files), self
        )
        progress.setWindowTitle("Import Recordings")
        progress.setWindowModality(Qt.WindowModality.WindowModal)

        for i, file_path in enumerate(selected_files):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            progress.setLabelText(f"Importing {os.path.basename(file_path)}...")

            try:
                # Copy file to Recordings directory
                recordings_dir = os.path.join(os.getcwd(), "Recordings")
                os.makedirs(recordings_dir, exist_ok=True)

                # Create destination path
                dest_file = os.path.join(recordings_dir, os.path.basename(file_path))

                # Check if file exists
                if os.path.exists(dest_file):
                    # Append number to filename
                    name, ext = os.path.splitext(os.path.basename(file_path))
                    counter = 1
                    while os.path.exists(dest_file):
                        dest_file = os.path.join(recordings_dir, f"{name}_{counter}{ext}")
                        counter += 1

                # Copy file
                import shutil
                shutil.copy2(file_path, dest_file)

                # Add to list
                self.on_io_complete(dest_file)

                imported_count += 1

            except Exception as e:
                logging.error(f"Error importing {file_path}: {e}")
                error_count += 1

        progress.setValue(len(selected_files))

        # Show results
        if error_count == 0:
            QMessageBox.information(
                self, "Import Complete",
                f"Successfully imported {imported_count} file(s)"
            )
        else:
            QMessageBox.warning(
                self, "Import Complete with Errors",
                f"Imported {imported_count} file(s)\n"
                f"Failed to import {error_count} file(s). See log for details."
            )

        # Refresh the list
        self.refresh_recordings()

    def show_help(self):
        """Show help information for recordings management."""
        help_text = """
        <h3>Managing Recordings</h3>
        <p><b>Search & Filter:</b> Use the search box to find recordings by name or content. Use the filter dropdown to show specific types of recordings.</p>
        <p><b>Sort:</b> Click the Sort button to organize recordings by date, name, or duration.</p>
        <p><b>Batch Operations:</b> Select multiple recordings by holding Ctrl while clicking, then use the Batch menu for bulk actions.</p>
        <p><b>Context Menu:</b> Right-click on any recording for more options, including rename, export, and delete.</p>
        <p><b>Import:</b> Use the Import button to add existing audio or video files to your recordings.</p>
        """

        QMessageBox.information(self, "Recordings Help", help_text)

    def refresh_recordings(self):
        """Refresh the recordings list from database."""
        # Store currently selected item
        current_item = self.recordings_list.currentItem()
        current_id = None
        if current_item:
            current_id = current_item.data(Qt.ItemDataRole.UserRole)['id']

        # Clear and reload recordings
        self.recordings_list.clear()
        self.load_recordings()

        # Restore selection if possible
        if current_id:
            for i in range(self.recordings_list.count()):
                item = self.recordings_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole)['id'] == current_id:
                    self.recordings_list.setCurrentItem(item)
                    break

        # Filter recordings based on current criteria
        self.filter_recordings()

        # Show confirmation
        self.show_status_message("Recordings refreshed")

    def filter_recordings(self):
        """Filter recordings based on search text and filter criteria."""
        search_text = self.search_widget.get_search_text().lower()
        filter_criteria = self.search_widget.get_filter_criteria()

        # Clear the search filter when both are empty
        if not search_text and filter_criteria == "All":
            for i in range(self.recordings_list.count()):
                self.recordings_list.item(i).setHidden(False)
            self.update_empty_state()
            return

        now = datetime.datetime.now()
        item_count = self.recordings_list.count()
        visible_count = 0

        for i in range(item_count):
            item = self.recordings_list.item(i)
            item_widget = self.recordings_list.itemWidget(item)
            metadata = item.data(Qt.ItemDataRole.UserRole)

            # Search by text
            text_match = (
                    not search_text or
                    search_text in metadata.get('filename', '').lower() or
                    search_text in item_widget.get_raw_transcript().lower()
            )

            # Filter by criteria
            criteria_match = True

            if filter_criteria == "Has Transcript":
                criteria_match = bool(item_widget.get_raw_transcript())
            elif filter_criteria == "No Transcript":
                criteria_match = not bool(item_widget.get_raw_transcript())
            elif filter_criteria == "Recent (24h)":
                try:
                    date_created = datetime.datetime.strptime(metadata.get('date_created', ''), "%Y-%m-%d %H:%M:%S")
                    time_diff = now - date_created
                    criteria_match = time_diff.total_seconds() < 86400  # 24 hours in seconds
                except (ValueError, TypeError):
                    criteria_match = False
            elif filter_criteria == "This Week":
                try:
                    date_created = datetime.datetime.strptime(metadata.get('date_created', ''), "%Y-%m-%d %H:%M:%S")
                    time_diff = now - date_created
                    criteria_match = time_diff.total_seconds() < 604800  # 7 days in seconds
                except (ValueError, TypeError):
                    criteria_match = False

            # Show/hide based on both conditions
            should_show = text_match and criteria_match
            item.setHidden(not should_show)

            if should_show:
                visible_count += 1

        # Show empty state message if no items visible
        self.empty_label.setVisible(visible_count == 0)
        if visible_count == 0:
            if search_text:
                self.empty_label.setText(f"No recordings found matching '{search_text}'")
            else:
                self.empty_label.setText(f"No recordings match the filter: {filter_criteria}")
        else:
            self.empty_label.setVisible(False)
            self.show_status_message(f"Showing {visible_count} of {item_count} recordings")

    def update_recording_display(self):
        """Update the relative time display in recording items."""
        for i in range(self.recordings_list.count()):
            item = self.recordings_list.item(i)
            item_widget = self.recordings_list.itemWidget(item)
            if hasattr(item_widget, 'update_relative_time'):
                item_widget.update_relative_time()

    def recording_clicked(self, item: QListWidgetItem):
        """Handle recording selection event."""
        recording_item_widget = self.recordings_list.itemWidget(item)
        self.recordingItemSelected.emit(recording_item_widget)

        # Update UI to show this item is selected
        for i in range(self.recordings_list.count()):
            curr_item = self.recordings_list.item(i)
            curr_widget = self.recordings_list.itemWidget(curr_item)
            if curr_widget == recording_item_widget:
                curr_widget.setStyleSheet("background-color: #e0e0e0; border-radius: 4px;")
            else:
                curr_widget.setStyleSheet("")

        # Show recording details in status bar
        recording_name = recording_item_widget.filename_no_ext
        date_created = datetime.datetime.strptime(
            recording_item_widget.date_created, "%Y-%m-%d %H:%M:%S"
        ).strftime("%b %d, %Y %H:%M")

        self.show_status_message(f"{recording_name} - {date_created} - {recording_item_widget.duration}")

    def showRightClickMenu(self, position):
        """Display context menu for recordings."""
        global_pos = self.recordings_list.viewport().mapToGlobal(position)
        item = self.recordings_list.itemAt(position)

        # Only show menu if there's an item
        if item:
            menu = QMenu()
            recording_widget = self.recordings_list.itemWidget(item)

            # Add actions based on recording state
            open_folder_action = menu.addAction("Show in Folder")
            open_folder_action.setIcon(QIcon(resource_path('icons/folder_open.svg')))

            rename_action = menu.addAction("Rename")
            rename_action.setIcon(QIcon(resource_path('icons/rename.svg')))
            menu.addSeparator()

            if recording_widget.has_transcript():
                clear_transcript_action = menu.addAction("Clear Transcript")
                clear_transcript_action.setIcon(QIcon(resource_path('icons/clear.svg')))
            else:
                clear_transcript_action = None

            if recording_widget.has_processed_text():
                clear_processed_action = menu.addAction("Clear Processed Text")
                clear_processed_action.setIcon(QIcon(resource_path('icons/clear.svg')))
            else:
                clear_processed_action = None

            menu.addSeparator()
            export_action = menu.addAction("Export Recording")
            export_action.setIcon(QIcon(resource_path('icons/export.svg')))
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
            delete_action.setIcon(QIcon(resource_path('icons/delete.svg')))

            # Show menu and handle action selection
            action = menu.exec(global_pos)

            if action == open_folder_action:
                self.open_containing_folder(item)
            elif action == rename_action:
                self.rename_recording(item)
            elif clear_transcript_action and action == clear_transcript_action:
                self.clear_transcript(item)
            elif clear_processed_action and action == clear_processed_action:
                self.clear_processed_text(item)
            elif action == export_action:
                self.export_recording(item)
            elif action == delete_action:
                self.delete_selected_recording(item)

    def open_containing_folder(self, item):
        """Open the folder containing the recording file."""
        recording_widget = self.recordings_list.itemWidget(item)
        file_path = recording_widget.file_path

        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", f"The file could not be found at: {file_path}")
            return

        # Open file explorer to the containing folder
        folder_path = os.path.dirname(file_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))

    def rename_recording(self, item):
        """Rename a recording."""
        recording_widget = self.recordings_list.itemWidget(item)
        current_name = recording_widget.filename_no_ext

        new_name, ok = QInputDialog.getText(
            self, 'Rename Recording', 'Enter new name:', QLineEdit.EchoMode.Normal, current_name
        )

        if ok and new_name and new_name != current_name:
            try:
                # Update database
                recording_id = recording_widget.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                if conn:
                    update_recording(conn, recording_id, filename=new_name)
                    conn.close()

                    # Update UI
                    recording_widget.filename = new_name
                    recording_widget.filename_no_ext = new_name
                    recording_widget.name_editable.setText(new_name)

                    # Update metadata
                    metadata = item.data(Qt.ItemDataRole.UserRole)
                    metadata['filename'] = new_name
                    item.setData(Qt.ItemDataRole.UserRole, metadata)

                    self.show_status_message(f"Recording renamed to {new_name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to rename recording: {e}")
                logging.error(f"Error renaming recording: {e}", exc_info=True)

    def clear_transcript(self, item):
        """Clear the transcript of a recording."""
        recording_widget = self.recordings_list.itemWidget(item)

        # Confirm with user
        confirm = QMessageBox.question(
            self, "Clear Transcript",
            "Are you sure you want to clear the transcript? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            try:
                # Update database
                recording_id = recording_widget.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                if conn:
                    update_recording(conn, recording_id, raw_transcript="", raw_transcript_formatted=None)
                    conn.close()

                    # Update recording widget
                    recording_widget.raw_transcript = ""
                    recording_widget.raw_transcript_formatted_data = None

                    # Update status indicator
                    recording_widget.status_indicator.set_status(False, recording_widget.has_processed_text())
                    recording_widget.update_status_label()

                    self.show_status_message("Transcript cleared successfully")

                    # Notify that recording was modified
                    self.recordingItemSelected.emit(recording_widget)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear transcript: {e}")
                logging.error(f"Error clearing transcript: {e}", exc_info=True)

    def clear_processed_text(self, item):
        """Clear the processed text of a recording."""
        recording_widget = self.recordings_list.itemWidget(item)

        # Confirm with user
        confirm = QMessageBox.question(
            self, "Clear Processed Text",
            "Are you sure you want to clear the processed text? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            try:
                # Update database
                recording_id = recording_widget.get_id()
                db_path = resource_path("./database/database.sqlite")
                conn = create_connection(db_path)
                if conn:
                    update_recording(conn, recording_id, processed_text="", processed_text_formatted=None)
                    conn.close()

                    # Update recording widget
                    recording_widget.processed_text = ""
                    recording_widget.processed_text_formatted_data = None

                    # Update status indicator
                    recording_widget.status_indicator.set_status(recording_widget.has_transcript(), False)
                    recording_widget.update_status_label()

                    self.show_status_message("Processed text cleared successfully")

                    # Notify that recording was modified
                    self.recordingItemSelected.emit(recording_widget)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to clear processed text: {e}")
                logging.error(f"Error clearing processed text: {e}", exc_info=True)

    def export_recording(self, item):
        """Export a recording file to another location."""
        recording_widget = self.recordings_list.itemWidget(item)
        file_path = recording_widget.file_path

        if not os.path.exists(file_path):
            QMessageBox.warning(self, "File Not Found", f"The audio file could not be found at: {file_path}")
            return

        # Ask for save location
        file_name = os.path.basename(file_path)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Export Recording", file_name, "Audio Files (*.mp3 *.wav *.m4a)"
        )

        if save_path:
            try:
                import shutil
                shutil.copy2(file_path, save_path)
                self.show_status_message(f"Exported to {os.path.basename(save_path)}")
                QMessageBox.information(self, "Success", f"Recording exported to: {save_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export recording: {e}")
                logging.error(f"Error exporting recording: {e}", exc_info=True)

    def delete_selected_recording(self, item=None):
        """Delete a recording from the list and database."""
        # If no item provided, use current selection
        if item is None:
            item = self.recordings_list.currentItem()

        if item is not None:
            # Confirm deletion
            response = QMessageBox.question(
                self, 'Delete Recording',
                'Are you sure you want to delete this recording? This cannot be undone.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if response == QMessageBox.StandardButton.Yes:
                recording_id = item.data(Qt.ItemDataRole.UserRole)['id']
                file_path = item.data(Qt.ItemDataRole.UserRole)['full_path']

                try:
                    # Delete from database
                    db_path = resource_path("./database/database.sqlite")
                    conn = create_connection(db_path)
                    delete_recording(conn, recording_id)
                    conn.close()

                    # Try to delete the actual file, but continue if it fails
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        logging.warning(f"Could not delete file {file_path}: {e}")

                    # Remove from list widget
                    row = self.recordings_list.row(item)
                    self.recordings_list.takeItem(row)

                    # Update empty state
                    self.update_empty_state()

                    self.show_status_message("Recording deleted")

                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to delete recording: {e}")
                    logging.error(f"Error deleting recording: {e}", exc_info=True)

    def update_empty_state(self):
        """Update empty state visibility."""
        has_visible_items = False
        for i in range(self.recordings_list.count()):
            if not self.recordings_list.item(i).isHidden():
                has_visible_items = True
                break

        self.empty_label.setVisible(not has_visible_items)
        if not has_visible_items:
            self.empty_label.setText("No recordings found. Upload or record audio to get started.")

    def load_recordings(self):
        """Load recordings from the database and populate the list."""
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)

        if not conn:
            QMessageBox.critical(self, "Database Error", "Could not connect to the database.")
            return

        try:
            recordings = get_all_recordings(conn)
            conn.close()

            if not recordings:
                self.empty_label.setText("No recordings found. Upload or record audio to get started.")
                self.empty_label.setVisible(True)
                return

            # Sort recordings by date, newest first
            sorted_recordings = sorted(
                recordings,
                key=lambda r: datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S"),
                reverse=True
            )

            for recording in sorted_recordings:
                id, filename, file_path, date_created, duration, raw_transcript, processed_text, raw_transcript_formatted, processed_text_formatted = recording
                self.add_recording_to_list(id, filename, file_path, date_created, duration, raw_transcript,
                                           processed_text, raw_transcript_formatted, processed_text_formatted)

            # Update empty state
            self.update_empty_state()

            # Show count in status bar
            self.show_status_message(f"Loaded {len(recordings)} recording(s)")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load recordings: {e}")
            logging.error(f"Error loading recordings: {e}", exc_info=True)
            if conn:
                conn.close()

    def add_recording_to_list(self, id, filename, file_path, date_created, duration, raw_transcript, processed_text,
                              raw_transcript_formatted=None, processed_text_formatted=None):
        """Add a recording to the list widget."""
        recording_item_widget = RecordingListItem(
            id, filename, file_path, date_created, duration,
            raw_transcript, processed_text, raw_transcript_formatted, processed_text_formatted
        )

        # Set metadata
        recording_item_widget.metadata = {
            'id': id,
            'filename': filename,
            'full_path': file_path,
            'date_created': date_created,
            'duration': duration
        }

        item = QListWidgetItem(self.recordings_list)
        item.setSizeHint(recording_item_widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, recording_item_widget.metadata)

        self.recordings_list.addItem(item)
        self.recordings_list.setItemWidget(item, recording_item_widget)

    def on_io_complete(self, file_path):
        """Handle new file addition."""
        try:
            # Extract metadata from the file
            filename = os.path.basename(file_path)
            date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Calculate duration
            from moviepy.editor import AudioFileClip
            audio = AudioFileClip(file_path)
            duration = format_time_duration(audio.duration)
            audio.close()

            # Add to database
            db_path = resource_path("./database/database.sqlite")
            conn = create_connection(db_path)
            recording_data = (filename, file_path, date_created, duration, "", "")
            recording_id = create_recording(conn, recording_data)
            conn.close()

            # Add to UI
            self.add_recording_to_list(recording_id, filename, file_path, date_created, duration, "", "")

            # Update empty state
            self.update_empty_state()

            self.show_status_message(f"Added {filename}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add recording: {e}")
            logging.error(f"Error adding recording: {e}", exc_info=True)

    def save_recordings(self):
        """Save all recordings from the list to the database."""
        db_path = resource_path("./database/database.sqlite")
        conn = create_connection(db_path)

        if not conn:
            QMessageBox.critical(self, "Database Error", "Could not connect to the database.")
            return

        try:
            for index in range(self.recordings_list.count()):
                item = self.recordings_list.item(index)
                recording_item_widget = self.recordings_list.itemWidget(item)

                # Get data from widget
                raw_transcript = recording_item_widget.get_raw_transcript()
                processed_text = recording_item_widget.get_processed_text()
                recording_id = recording_item_widget.get_id()

                # Update database
                update_recording(conn, recording_id, raw_transcript=raw_transcript, processed_text=processed_text)

            conn.close()
            logging.info("All recordings saved to database")
            self.show_status_message("All recordings saved")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save recordings: {e}")
            logging.error(f"Error saving recordings: {e}", exc_info=True)
            if conn:
                conn.close()

    def show_status_message(self, message, timeout=3000):
        """Show a message in the status bar."""
        self.status_bar.showMessage(message, timeout)
        if not self.status_bar.isVisible():
            self.status_bar.show()
            # Hide after timeout
            QTimer.singleShot(timeout, lambda: self.status_bar.hide() if not self.status_bar.currentMessage() else None)