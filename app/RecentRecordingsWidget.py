import datetime
import os
import logging
from PyQt6.QtCore import pyqtSignal, QSize, Qt, QTimer, QThread
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QWidget,
    QLabel,
    QHBoxLayout,
    QLineEdit,
    QComboBox,
    QProgressDialog,
    QFileDialog,
    QToolBar,
    QStatusBar,
)
from PyQt6.QtGui import QIcon, QFont, QAction
from app.RecordingListItem import RecordingListItem
from app.path_utils import resource_path

# Use ui_utils for messages
from app.ui_utils import show_error_message, show_info_message, show_confirmation_dialog
from app.DatabaseManager import DatabaseManager
from app.ResponsiveUI import ResponsiveWidget, ResponsiveSizePolicy
from app.UnifiedFolderTreeView import UnifiedFolderTreeView

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Configured in main
logger = logging.getLogger("transcribrr")


class SearchWidget(QWidget):
    """Search/filter recordings."""

    # (Content mostly unchanged)
    searchTextChanged = pyqtSignal(str)
    filterCriteriaChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search recordings & transcripts...")
        self.search_field.textChanged.connect(self.searchTextChanged.emit)
        self.search_field.setStyleSheet(
            "QLineEdit { border: 1px solid #ccc; border-radius: 4px; padding: 4px 8px; }"
        )
        self.search_field.setToolTip("Search in filenames and transcript content")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(
            ["All", "Has Transcript", "No Transcript", "Recent (24h)", "This Week"]
        )
        self.filter_combo.currentTextChanged.connect(self.filterCriteriaChanged.emit)
        layout.addWidget(self.search_field, 3)
        layout.addWidget(self.filter_combo, 1)

    def clear_search(self):
        self.search_field.clear()

    def get_search_text(self):
        return self.search_field.text()

    def get_filter_criteria(self):
        return self.filter_combo.currentText()


class BatchProcessWorker(QThread):
    """Thread for batch processing recordings."""

    # TODO: Implement actual batch processing logic by integrating
    #       with TranscriptionThread and GPT4ProcessingThread.
    #       This currently only simulates progress.
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self, recordings_data, process_type, parent=None
    ):  # Pass data, not widgets
        super().__init__(parent)
        self.recordings_data = recordings_data  # List of dicts or tuples
        self.process_type = process_type
        self._is_canceled = False

    def run(self):
        try:
            total = len(self.recordings_data)
            logger.info(f"Starting batch '{self.process_type}' for {total} recordings.")

            for i, rec_data in enumerate(self.recordings_data):
                if self._is_canceled:
                    self.finished.emit(False, "Operation canceled")
                    return

                rec_id = rec_data["id"]
                rec_name = rec_data["filename"]
                progress_val = int(((i + 1) / total) * 100)
                status_msg = f"Processing {rec_name} ({i+1}/{total})"
                self.progress.emit(progress_val, status_msg)
                logger.debug(status_msg)

                # --- Placeholder for Actual Processing ---
                if self.process_type == "transcribe":
                    # Example: Start TranscriptionThread for rec_data['file_path']
                    # Need to handle thread management, config, keys etc.
                    # Wait for completion or manage multiple threads.
                    self.msleep(300)  # Simulate work
                    pass
                elif self.process_type == "process":
                    # Example: Start GPT4ProcessingThread for rec_data['raw_transcript']
                    # Need to handle thread management, config, keys, prompts etc.
                    self.msleep(500)  # Simulate work
                    pass
                # -----------------------------------------

            if not self._is_canceled:
                self.finished.emit(
                    True,
                    f"Batch '{self.process_type}' complete for {total} recordings.",
                )
                logger.info(f"Batch '{self.process_type}' complete.")

        except Exception as e:
            error_msg = f"Error during batch {self.process_type}: {e}"
            logger.error(error_msg, exc_info=True)
            if not self._is_canceled:
                self.finished.emit(False, error_msg)

    def cancel(self):
        logger.info(f"Cancellation requested for batch '{self.process_type}'.")
        self._is_canceled = True


class RecentRecordingsWidget(ResponsiveWidget):
    # recordingSelected = pyqtSignal(str) # Replaced by recordingItemSelected
    # recordButtonPressed = pyqtSignal() # Handled internally by controls now
    recordingItemSelected = pyqtSignal(RecordingListItem)  # Emit the item widget

    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(8)
        self.setSizePolicy(ResponsiveSizePolicy.preferred())  # Changed policy

        self.db_manager = db_manager or DatabaseManager(self)
        self.current_folder_id = -1  # Default to "All Recordings"

        # Create a timer for debouncing search
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(250)  # 250ms debounce delay
        self.filter_timer.timeout.connect(self._apply_filter)
        self.pending_search_text = ""
        self.pending_filter_criteria = "All"

        self.init_toolbar()  # Add toolbar

        # Header (Simplified - folder name updated by Unified view selection)
        self.header_label = QLabel("Recordings")  # Static header
        self.header_label.setObjectName("RecentRecordingHeader")
        self.header_label.setFont(
            QFont("Arial", 14, QFont.Weight.Bold)
        )  # Slightly larger
        self.layout.addWidget(self.header_label)

        # Search and filter
        self.search_widget = SearchWidget()
        self.search_widget.searchTextChanged.connect(self.filter_recordings)
        self.search_widget.filterCriteriaChanged.connect(self.filter_recordings)
        self.layout.addWidget(self.search_widget)

        # Unified folder and recordings view using model/view framework
        self.unified_view = UnifiedFolderTreeView(self.db_manager, self)
        self.unified_view.folderSelected.connect(self.on_folder_selected)
        self.unified_view.recordingSelected.connect(
            self.recordingItemSelected.emit
        )  # Pass signal through
        self.unified_view.recordingNameChanged.connect(
            self.handle_recording_rename
        )  # Connect rename handler
        self.layout.addWidget(self.unified_view, 1)  # Allow view to stretch

        # Status bar
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.layout.addWidget(self.status_bar)
        self.status_bar.hide()

        # Batch processing (Keep worker reference)
        self.batch_worker = None
        self.progress_dialog = None

        # Load initial data
        self.load_recordings()

        # Clear search on initialize
        self.search_widget.clear_search()

        # Initial filter application (without debounce)
        self._apply_filter()

    def init_toolbar(self):
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(18, 18))  # Slightly larger icons
        toolbar.setMovable(False)

        new_folder_action = QAction(
            QIcon(resource_path("icons/folder.svg")), "New Folder", self
        )
        new_folder_action.triggered.connect(self.create_new_folder)
        toolbar.addAction(new_folder_action)

        refresh_action = QAction(
            QIcon(resource_path("icons/refresh.svg")), "Refresh", self
        )
        refresh_action.triggered.connect(self.refresh_recordings)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        import_action = QAction(
            QIcon(resource_path("icons/import.svg")), "Import Files", self
        )
        import_action.triggered.connect(self.import_recordings)
        toolbar.addAction(import_action)

        # TODO: Add Batch Actions Dropdown, Sort Dropdown, Help Button similar to previous implementation if needed

        self.layout.addWidget(toolbar)

    # --- Actions ---
    def create_new_folder(self):
        """Trigger folder creation in the unified view."""
        # Let the unified view handle the dialog and DB interaction - use UnifiedFolderTreeView API
        # Pass the parent folder ID directly (root level is -1)
        self.unified_view.create_subfolder(-1)

    def refresh_recordings(self):
        """Refresh the recordings list."""
        self.show_status_message("Refreshing recordings...")
        # Get current selection to restore it after reload
        selected_item = self.unified_view.currentItem()
        selected_id = None
        selected_type = None
        if selected_item:
            data = selected_item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                selected_id = data.get("id")
                selected_type = data.get("type")

        self.unified_view.load_structure(selected_id, selected_type)
        self.show_status_message("Recordings refreshed", 2000)

    def import_recordings(self):
        file_dialog = QFileDialog(self)
        file_dialog.setWindowTitle("Import Audio/Video Files")
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter(
            "Media Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov *.flac *.aac *.aiff *.wma *.webm *.flv *.wmv)"
        )
        if file_dialog.exec() != QFileDialog.DialogCode.Accepted:
            return

        selected_files = file_dialog.selectedFiles()
        if not selected_files:
            return

        imported_count = 0
        error_count = 0
        # TODO: Add progress dialog for large imports
        self.show_status_message(f"Importing {len(selected_files)} files...")

        for file_path in selected_files:
            try:
                # Ensure the recordings directory exists
                recordings_dir = os.path.join(os.getcwd(), "Recordings")
                os.makedirs(recordings_dir, exist_ok=True)

                # Generate a unique destination path
                dest_filename = os.path.basename(file_path)
                name, ext = os.path.splitext(dest_filename)
                counter = 1
                dest_path = os.path.join(recordings_dir, dest_filename)
                while os.path.exists(dest_path):
                    dest_path = os.path.join(recordings_dir, f"{name}_{counter}{ext}")
                    counter += 1

                # Copy the file
                import shutil

                shutil.copy2(file_path, dest_path)
                logger.info(f"Copied imported file to {dest_path}")

                # Add the copied file to the database via the io_complete handler
                # This assumes MainTranscriptionWidget is listening and will add it.
                # A more direct way would be better.
                # self.parent().on_new_file(dest_path) # Assuming parent is MainWindow
                self.add_imported_file_to_db(dest_path)  # Add directly here

                imported_count += 1
            except Exception as e:
                logger.error(f"Error importing {file_path}: {e}", exc_info=True)
                error_count += 1
                show_error_message(
                    self,
                    "Import Error",
                    f"Failed to import {os.path.basename(file_path)}: {e}",
                )

        # Update status after import loop
        if error_count == 0:
            self.show_status_message(
                f"Import complete: {imported_count} files added.", 5000
            )
        else:
            self.show_status_message(
                f"Import complete: {imported_count} added, {error_count} failed.", 5000
            )

        self.refresh_recordings()  # Refresh list after import

    def add_imported_file_to_db(self, file_path):
        """Adds an imported file record to the database."""
        try:
            filename = os.path.basename(file_path)
            date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Calculate duration (potential performance hit for many files)
            from app.file_utils import calculate_duration

            duration = calculate_duration(file_path)  # Returns "HH:MM:SS" or "MM:SS"

            recording_data = (filename, file_path, date_created, duration, "", "")

            # Define callback (optional, can just refresh later)
            def on_import_added(recording_id):
                if recording_id:
                    logger.info(
                        f"Imported file '{filename}' added to DB with ID {recording_id}"
                    )
                else:
                    logger.error(f"Failed to add imported file '{filename}' to DB")

            self.db_manager.create_recording(recording_data, on_import_added)
        except Exception as e:
            logger.error(
                f"Error preparing imported file '{file_path}' for DB: {e}",
                exc_info=True,
            )
            show_error_message(
                self,
                "Import DB Error",
                f"Could not add '{os.path.basename(file_path)}' to database: {e}",
            )

    # --- Signal Handlers ---
    def on_folder_selected(self, folder_id, folder_name):
        self.current_folder_id = folder_id
        # The header might not be needed if the unified view makes the selection clear
        # self.header_label.setText(folder_name)
        self.show_status_message(f"Selected folder: {folder_name}")

        # Apply filtering immediately without debounce when folder is selected
        self.pending_search_text = self.search_widget.get_search_text().lower()
        self.pending_filter_criteria = self.search_widget.get_filter_criteria()
        self._apply_filter()

        # In the model/view architecture the UnifiedFolderTreeView handles data updates
        # internally via model signals. Filtering above is sufficient to reflect the
        # newly-selected folder, so we no longer attempt to manually reload the
        # folder's recordings here (the previous call attempted to use a
        # non-existent load_recordings_for_item API and triggered an
        # AttributeError).

    def update_recording_status(self, recording_id, status_updates):
        """Update the status of a recording item based on external processing events."""
        logger.info(f"Updating recording status for ID {recording_id}")

        # Find the recording widget in our map
        widget = self.unified_view.id_to_widget.get(recording_id)
        if not widget:
            logger.error(
                f"Cannot update status: RecordingListItem widget not found for ID {recording_id}"
            )
            return

        # Update the widget with new status
        widget.update_data(status_updates)

        # Refresh the visual appearance
        self.unified_view.viewport().update()

    def handle_recording_rename(self, recording_id: int, new_name_no_ext: str):
        """
        Handle the rename request from a RecordingListItem.
        Synchronizes both database and filesystem changes in an atomic manner.
        """
        logger.info(f"Handling rename for ID {recording_id} to '{new_name_no_ext}'")

        # Construct new full filename (keep original extension)
        widget = self.unified_view.id_to_widget.get(recording_id)
        if not widget:
            logger.error(
                f"Cannot rename: RecordingListItem widget not found for ID {recording_id}"
            )
            return

        _, ext = os.path.splitext(widget.get_filename())
        new_full_filename = new_name_no_ext + ext

        # Get current file path
        old_file_path = widget.file_path
        if not os.path.exists(old_file_path):
            logger.error(
                f"Cannot rename: Original file does not exist at {old_file_path}"
            )
            show_error_message(
                self, "Rename Failed", "The original file could not be found on disk."
            )
            return

        # Generate new file path (same directory, new name)
        directory = os.path.dirname(old_file_path)
        new_file_path = os.path.join(directory, new_full_filename)

        # Check if target path already exists
        if os.path.exists(new_file_path):
            logger.error(
                f"Cannot rename: Target path already exists at {new_file_path}"
            )
            show_error_message(
                self, "Rename Failed", "A file with this name already exists."
            )
            # Revert UI change
            widget.name_editable.setText(widget.filename_no_ext)
            return

        # --- Atomic Rename Implementation ---
        def on_db_update_success():
            logger.info(f"Successfully updated database for recording {recording_id}")
            # Update the widget's internal state and UI
            widget.update_data(
                {
                    "filename": new_name_no_ext,  # base name for UI
                    "file_path": new_file_path,  # update file path reference
                }
            )
            self.show_status_message(f"Renamed to '{new_name_no_ext}'")

        def on_rename_error(op_name, error_msg):
            logger.error(f"Failed to rename recording {recording_id}: {error_msg}")
            show_error_message(
                self, "Rename Failed", f"Could not rename recording: {error_msg}"
            )
            # Revert UI change
            widget.name_editable.setText(widget.filename_no_ext)

        try:
            # First attempt the filesystem rename - if this fails, no DB update needed
            os.rename(old_file_path, new_file_path)
            logger.info(
                f"Successfully renamed file on disk from {old_file_path} to {new_file_path}"
            )

            try:
                # Now update the database with both new filename and file path
                self.db_manager.update_recording(
                    recording_id,
                    on_db_update_success,
                    filename=new_full_filename,
                    file_path=new_file_path,
                )

                # Connect error handler for DB-related errors
                self.db_manager.error_occurred.connect(on_rename_error)

            except Exception as db_error:
                # If DB update fails, roll back the filesystem rename
                logger.error(
                    f"Database update failed, rolling back filesystem rename: {db_error}"
                )
                try:
                    os.rename(new_file_path, old_file_path)
                    logger.info(
                        f"Successfully rolled back file rename from {new_file_path} to {old_file_path}"
                    )
                except OSError as rollback_error:
                    # Critical situation - DB update failed AND filesystem rollback failed
                    logger.critical(
                        f"CRITICAL: Failed to roll back rename after DB error. DB and filesystem out of sync: {rollback_error}"
                    )
                    show_error_message(
                        self,
                        "Critical Rename Error",
                        "Database update failed and could not roll back filesystem change. Please restart the application.",
                    )

                # Show error and revert UI
                show_error_message(
                    self, "Rename Failed", f"Database error: {str(db_error)}"
                )
                widget.name_editable.setText(widget.filename_no_ext)

        except OSError as fs_error:
            # Filesystem rename failed - no need to update DB
            logger.error(f"Failed to rename file on disk: {fs_error}")
            show_error_message(
                self, "Rename Failed", f"Could not rename file on disk: {str(fs_error)}"
            )
            # Revert UI change
            widget.name_editable.setText(widget.filename_no_ext)

    def filter_recordings(self):
        """Debounced filter for recordings displayed in the unified view."""
        # Store values for later use when the timer fires
        self.pending_search_text = self.search_widget.get_search_text().lower()
        self.pending_filter_criteria = self.search_widget.get_filter_criteria()

        # Reset and start the debounce timer
        self.filter_timer.stop()
        self.filter_timer.start()

        # Quick feedback to the user that filtering is pending
        if self.pending_search_text:
            self.show_status_message(
                f"Filtering for: '{self.pending_search_text}'...", 250
            )

    def _apply_filter(self):
        """Apply the actual filtering logic after debounce."""
        search_text = self.pending_search_text
        filter_criteria = self.pending_filter_criteria
        folder_id = self.current_folder_id

        # Show status message based on filtering parameters
        if search_text:
            self.show_status_message(
                f"Searching for: '{search_text}' in names and transcripts"
            )
        elif filter_criteria != "All":
            self.show_status_message(f"Filtering: {filter_criteria}")
        else:
            self.show_status_message("Showing all recordings")

        logger.info(
            f"Filtering recordings - Search: '{search_text}', Criteria: {filter_criteria}"
        )

        # Use the unified_view's set_filter method to apply filtering through the proxy model
        self.unified_view.set_filter(search_text, filter_criteria)

        # The QSortFilterProxyModel handles all the showing/hiding of items automatically
        # We no longer need to manually check visibility, but we might want to
        # provide count feedback to users in the future when we have access to that data

    def _make_all_visible(self, item):
        """No longer needed with model-based filtering."""
        # This method is kept as a stub for compatibility
        # With QSortFilterProxyModel, visibility is handled automatically
        pass

    def _count_visible_items(self, parent_item):
        """No longer needed with model-based filtering."""
        # This method is kept as a stub for compatibility
        # With QSortFilterProxyModel, visibility is handled automatically
        return 0

    def _check_for_visible_items(self, parent_item):
        """No longer needed with model-based filtering."""
        # This method is kept as a stub for compatibility
        # With QSortFilterProxyModel, visibility is handled automatically
        return True

    def load_recordings(self):
        """Load initial recordings."""
        self.unified_view.load_structure()

    def add_recording_to_list(
        self,
        recording_id,
        filename,
        file_path,
        date_created,
        duration,
        raw_transcript,
        processed_text,
    ):
        """Add a new recording to the recordings list."""
        # Find the root "All Recordings" folder - fix item_map reference
        root_item = self.unified_view.source_model.get_item_by_id(-1, "folder")
        if not root_item:
            logger.error("Root 'All Recordings' folder not found")
            return

        # Add recording to the folder directly
        recording_data = (
            recording_id,
            filename,
            file_path,
            date_created,
            duration,
            raw_transcript,
            processed_text,
        )
        try:
            # Add recording to the tree
            self.unified_view._add_recording_item(root_item, recording_data)

            # Make sure the recording is visible in the UI - handle both QTreeView and QTreeWidget APIs
            try:
                # Try QTreeView approach first (for UnifiedFolderTreeView)
                index = self.unified_view.proxy_model.mapFromSource(root_item.index())
                self.unified_view.setExpanded(index, True)
            except (AttributeError, Exception) as e:
                # Fall back to QTreeWidget approach
                try:
                    root_item.setExpanded(True)
                except Exception:
                    logger.warning(f"Could not expand root item: {e}")

            # Refresh the filter
            try:
                self.filter_recordings()
            except Exception as e:
                logger.warning(f"Error refreshing filter: {e}")

            logger.info(f"Added recording to the list: {filename}")
        except Exception as e:
            logger.error(f"Error adding recording to list: {e}", exc_info=True)

    def show_status_message(self, message, timeout=3000):
        self.status_bar.showMessage(message, timeout)
        if not self.status_bar.isVisible():
            self.status_bar.show()
            QTimer.singleShot(
                timeout + 100,
                lambda: (
                    self.status_bar.hide()
                    if self.status_bar.currentMessage() == message
                    else None
                ),
            )

    # --- Batch Processing Methods (Placeholders/Connections) ---
    def batch_process(self, process_type):
        selected_items = self.unified_view.selectedItems()
        selected_data = []
        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "recording":
                widget = data.get("widget")
                if widget:
                    # Collect necessary data for processing
                    selected_data.append(
                        {
                            "id": widget.get_id(),
                            "filename": widget.get_filename(),
                            "file_path": widget.get_filepath(),
                            "raw_transcript": widget.get_raw_transcript(),  # Needed for GPT processing
                        }
                    )

        if not selected_data:
            show_info_message(
                self, "No Selection", f"Please select recordings to {process_type}."
            )
            return

        action_text = (
            "Transcribe" if process_type == "transcribe" else "Process with GPT"
        )
        if not show_confirmation_dialog(
            self,
            f"Batch {action_text}",
            f"{action_text} {len(selected_data)} recording(s)?",
        ):
            return

        self.progress_dialog = QProgressDialog(
            f"Starting batch {process_type}...", "Cancel", 0, 100, self
        )
        self.progress_dialog.setWindowTitle(f"Batch {action_text}")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(False)
        self.progress_dialog.canceled.connect(self.cancel_batch_process)

        # TODO: Replace BatchProcessWorker with actual calls to Transcription/GPT threads
        # This requires more complex logic to manage multiple threads, API keys, config etc.
        self.batch_worker = BatchProcessWorker(selected_data, process_type)
        self.batch_worker.progress.connect(self.update_batch_progress)
        self.batch_worker.finished.connect(self.on_batch_process_finished)
        self.batch_worker.start()
        self.progress_dialog.show()

    def cancel_batch_process(self):
        if self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.cancel()
            if self.progress_dialog:
                self.progress_dialog.setLabelText("Cancelling...")

    def update_batch_progress(self, value, message):
        if self.progress_dialog:
            self.progress_dialog.setValue(value)
            self.progress_dialog.setLabelText(message)

    def on_batch_process_finished(self, success, message):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        if success:
            show_info_message(self, "Batch Complete", message)
        else:
            show_error_message(self, "Batch Error", message)

        self.refresh_recordings()  # Refresh list after batch operation
        self.batch_worker = None  # Clear worker

    def batch_export(self):
        selected_items = self.unified_view.selectedItems()
        files_to_export = []
        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "recording":
                widget = data.get("widget")
                if widget and widget.get_filepath():
                    files_to_export.append(
                        (widget.get_filepath(), widget.get_filename())
                    )

        if not files_to_export:
            show_info_message(
                self,
                "No Selection",
                "Select recordings with associated files to export.",
            )
            return

        export_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not export_dir:
            return

        exported_count = 0
        error_count = 0
        # TODO: Add progress dialog for export
        self.show_status_message(f"Exporting {len(files_to_export)} files...")

        for source_path, original_filename in files_to_export:
            try:
                # Generate unique target path
                target_path = os.path.join(export_dir, original_filename)
                counter = 1
                name, ext = os.path.splitext(original_filename)
                while os.path.exists(target_path):
                    target_path = os.path.join(export_dir, f"{name}_{counter}{ext}")
                    counter += 1
                # Copy
                import shutil

                shutil.copy2(source_path, target_path)
                exported_count += 1
            except Exception as e:
                logger.error(f"Error exporting {source_path} to {export_dir}: {e}")
                error_count += 1

        result_message = f"Exported {exported_count} files."
        if error_count > 0:
            result_message += f" Failed to export {error_count} files."
            show_error_message(self, "Export Complete with Errors", result_message)
        else:
            show_info_message(self, "Export Complete", result_message)
        self.show_status_message(result_message, 5000)

    def sort_recordings(self, sort_by, reverse=False):
        """Placeholder for sorting logic in UnifiedFolderListWidget."""
        show_info_message(
            self,
            "Not Implemented",
            "Sorting within the unified view is not yet implemented.",
        )
        # TODO: Implement sorting. This likely requires modifying how items are added
        # in `load_recordings_for_item` or using QTreeView with a sortable model.

    def show_help(self):
        # Content unchanged, using ui_utils
        help_text = """
         <h3>Managing Recordings</h3>
         <p><b>Folders:</b> Use the tree view to organize recordings. Drag recordings onto folders. Right-click for options like New Folder, Rename, Delete.</p>
         <p><b>Search/Filter:</b> Use the search box to find recordings by filename or transcript content. Use the dropdown to filter by status or date.</p>
         <p><b>Actions:</b> Right-click a recording for options like Rename, Show in Explorer, Export, Clear Transcript/Processed Text, Delete.</p>
         <p><b>Import:</b> Use the Import button in the toolbar to add existing media files.</p>
         <p><b>Batch Actions:</b> (Coming Soon) Select multiple recordings (Ctrl+Click or Shift+Click) and use toolbar actions.</p>
         """
        show_info_message(self, "Recordings Help", help_text)
