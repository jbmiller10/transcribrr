import datetime
import os
import sys
import logging
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout, QApplication, QWidget, QHBoxLayout,
    QSizePolicy, QMainWindow, QSplitter, QStatusBar,
    QMessageBox
)

from app.MainTranscriptionWidget import MainTranscriptionWidget
from app.ControlPanelWidget import ControlPanelWidget
from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager
from app.RecentRecordingsWidget import RecentRecordingsWidget
from app.path_utils import resource_path
from app.file_utils import calculate_duration
from app.ui_utils import show_status_message
from app.constants import APP_NAME

 
logger = logging.getLogger('transcribrr')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # 1. Create DatabaseManager FIRST
        try:
            self.db_manager = DatabaseManager(self)
            logger.info("DatabaseManager created successfully.")
        except Exception as e:
            logger.critical(f"CRITICAL ERROR creating DatabaseManager: {e}", exc_info=True)
            # Handle critical initialization error
            QMessageBox.critical(self, "Initialization Error", f"Failed to initialize Database Manager: {e}")
            sys.exit(1)

        # 2. Initialize FolderManager and attach DB Manager in one call
        try:
            # This single call now handles singleton creation AND attachment
            FolderManager.instance(db_manager=self.db_manager)
            logger.info("FolderManager initialized and DatabaseManager attached.")
        except RuntimeError as e:
            logger.critical(f"CRITICAL ERROR initializing FolderManager: {e}", exc_info=True)
            QMessageBox.critical(self, "Initialization Error", f"Failed to initialize Folder Manager: {e}")
            sys.exit(1)
        except Exception as e:
            logger.critical(f"CRITICAL ERROR during FolderManager initialization: {e}", exc_info=True)
            QMessageBox.critical(self, "Initialization Error", f"Unexpected error during Folder Manager setup: {e}")
            sys.exit(1)
            
        # 3. Now initialize the UI
        try:
            self.init_ui()
            logger.info("MainWindow UI initialized successfully.")
        except Exception as e:
            logger.critical(f"CRITICAL ERROR during MainWindow UI initialization: {e}", exc_info=True)
            QMessageBox.critical(self, "Initialization Error", f"Failed during UI setup: {e}")
            sys.exit(1)


    def init_ui(self):
        self.setWindowTitle(APP_NAME)
        
        screen_size = QApplication.primaryScreen().availableGeometry().size()
        window_width = min(int(screen_size.width() * 0.8), 1690)
        window_height = min(int(screen_size.height() * 0.8), 960)
        self.resize(window_width, window_height)
        
        self.move(
            (screen_size.width() - window_width) // 2,
            (screen_size.height() - window_height) // 2
        )

        # Database manager is initialized in __init__ method
        # and already attached to FolderManager
        
        self.control_panel = ControlPanelWidget(self)
        self.recent_recordings_widget = RecentRecordingsWidget(db_manager=self.db_manager)
        self.main_transcription_widget = MainTranscriptionWidget(db_manager=self.db_manager)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #D0D0D0;
                border-radius: 2px;
            }
            QSplitter::handle:hover {
                background-color: #808080;
            }
        """)

        self.main_layout.addWidget(self.splitter)

        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.recent_recordings_widget, 12)
        self.left_layout.addWidget(self.control_panel, 0)

        self.recent_recordings_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.control_panel.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)

        # Create a widget to hold the left_layout
        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)
        self.left_widget.setMinimumWidth(220) # Set minimum width to prevent excessive shrinking

        self.splitter.addWidget(self.left_widget)
        self.splitter.addWidget(self.main_transcription_widget)
        
        self.recent_recordings_widget.load_recordings()

        self.control_panel.file_ready_for_processing.connect(self.on_new_file)

        window_width = self.width()
        left_panel_width = int(window_width * 0.3)
        right_panel_width = window_width - left_panel_width
        self.splitter.setSizes([left_panel_width, right_panel_width])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_bar.setVisible(True)
        self.status_bar.showMessage("Ready")

        self.recent_recordings_widget.recordingItemSelected.connect(self.main_transcription_widget.on_recording_item_selected)
        
        self.main_transcription_widget.recording_status_updated.connect(self.recent_recordings_widget.update_recording_status)

        self.main_transcription_widget.status_update.connect(self.update_status_bar)

    def set_style(self):
        # Not needed - styling is now handled by the ThemeManager
        pass

    def on_new_file(self, file_path):
        """Handle new file.

Args:
    file_path: path to the audio file
        """
        try:
            filename = os.path.basename(file_path)
            date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Calculate the duration of the recording
            duration = calculate_duration(file_path)
            
            # Store the original source path (same as file_path for local files)
            original_source = file_path
            
            # Create a new recording in the database using the DatabaseManager
            # Include original_source_identifier as the last parameter
            recording_data = (filename, file_path, date_created, duration, "", "", original_source)
            
            # Define callback function to add the recording to UI when database operation completes
            def on_recording_created(recording_id):
                self.recent_recordings_widget.add_recording_to_list(
                    recording_id, filename, file_path, date_created, duration, "", ""
                )
                
                # Select the newly added recording automatically
                widget = self.recent_recordings_widget.unified_view.recordings_map.get(recording_id)
                if widget:
                    for i in range(self.recent_recordings_widget.unified_view.topLevelItemCount()):
                        parent_item = self.recent_recordings_widget.unified_view.topLevelItem(i)
                        self._find_and_select_recording_item(parent_item, recording_id)
                
                self.update_status_bar(f"Added new recording: {filename}")
                
            # Connect to error_occurred signal to catch database errors
            def on_db_error(operation_name, error_message):
                if operation_name == "create_recording":
                    # Format a user-friendly error message
                    error_text = f"DB error while adding '{filename}': {error_message}"
                    logger.error(f"Database error: {error_text}")
                    self.update_status_bar(error_text)
                    
                    # Disconnect after first delivery to avoid memory leaks
                    try:
                        self.db_manager.error_occurred.disconnect(on_db_error)
                    except TypeError:
                        # Already disconnected
                        pass
            
            # Connect with UniqueConnection to avoid duplicates
            from PyQt6.QtCore import Qt
            self.db_manager.error_occurred.connect(on_db_error, Qt.ConnectionType.UniqueConnection)
            
            # Execute the database operation in a background thread
            self.db_manager.create_recording(recording_data, on_recording_created)
            
            # Set a timeout to disconnect the error handler if no error occurs
            from PyQt6.QtCore import QTimer
            def disconnect_error_handler():
                try:
                    self.db_manager.error_occurred.disconnect(on_db_error)
                    logger.debug(f"Disconnected error handler for {filename}")
                except TypeError:
                    # Already disconnected
                    pass
            
            # Disconnect after 5 seconds if no error occurred
            QTimer.singleShot(5000, disconnect_error_handler)
                
        except Exception as e:
            logger.error(f"Error processing new file: {e}", exc_info=True)
            self.update_status_bar(f"Error processing file: {str(e)}")

    def update_status_bar(self, message):
        self.statusBar().showMessage(message)
        logger.debug(f"Status bar updated: {message}")
        
    def _find_and_select_recording_item(self, parent_item, recording_id):
        # First check this item
        item_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
        if item_data and item_data.get("type") == "recording" and item_data.get("id") == recording_id:
            self.recent_recordings_widget.unified_view.setCurrentItem(parent_item)
            # Ensure parent folders are expanded
            current_parent = parent_item.parent()
            while current_parent:
                current_parent.setExpanded(True)
                current_parent = current_parent.parent()
            return True
            
        # Check children
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if self._find_and_select_recording_item(child, recording_id):
                return True
                
        return False

    # Method removed - thread management handled by ThreadManager

