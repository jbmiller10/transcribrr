import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QVBoxLayout, QApplication, QWidget, QHBoxLayout,
    QSizePolicy, QMainWindow, QSplitter, QStatusBar
)
import os
import logging

from app.MainTranscriptionWidget import MainTranscriptionWidget
from app.ControlPanelWidget import ControlPanelWidget
from app.DatabaseManager import DatabaseManager
from app.RecentRecordingsWidget import RecentRecordingsWidget
from app.utils import resource_path
from app.file_utils import calculate_duration
from app.ui_utils import show_status_message
from app.constants import APP_NAME

# Configure logging
logger = logging.getLogger('transcribrr')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()


    def init_ui(self):
        """Init UI."""
        # Initialize the window properties
        self.setWindowTitle(APP_NAME)
        
        # Set a reasonable default size that will be scaled by the window manager
        screen_size = QApplication.primaryScreen().availableGeometry().size()
        window_width = min(int(screen_size.width() * 0.8), 1690)
        window_height = min(int(screen_size.height() * 0.8), 960)
        self.resize(window_width, window_height)
        
        # Center the window on screen
        self.move(
            (screen_size.width() - window_width) // 2,
            (screen_size.height() - window_height) // 2
        )

        # Initialize the database manager
        self.db_manager = DatabaseManager(self)

        # Create instances of widgets
        self.control_panel = ControlPanelWidget(self)
        self.recent_recordings_widget = RecentRecordingsWidget(db_manager=self.db_manager)
        self.main_transcription_widget = MainTranscriptionWidget(db_manager=self.db_manager)

        # Set up the central widget and its layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # Create a QSplitter to manage the layout of the left and right sections
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False) # Prevent collapsing panels completely
        self.splitter.setHandleWidth(8) # Make the splitter handle easier to grab
        
        # Style the splitter handle for better visibility
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

        # Layout for the left side section
        self.left_layout = QVBoxLayout()
        self.left_layout.addWidget(self.recent_recordings_widget, 12)
        self.left_layout.addWidget(self.control_panel, 0)

        self.recent_recordings_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.control_panel.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)

        # Create a widget to hold the left_layout
        self.left_widget = QWidget()
        self.left_widget.setLayout(self.left_layout)
        self.left_widget.setMinimumWidth(220) # Set minimum width to prevent excessive shrinking

        # Add widgets to the splitter
        self.splitter.addWidget(self.left_widget)
        self.splitter.addWidget(self.main_transcription_widget)
        
        # Load existing recordings, if any
        self.recent_recordings_widget.load_recordings()

        # Connect signal for new files (renamed from uploaded_filepath to file_ready_for_processing)
        self.control_panel.file_ready_for_processing.connect(self.on_new_file)

        # Set the initial side ratios of the splitter using proportions of the window width
        window_width = self.width()
        left_panel_width = int(window_width * 0.3)
        right_panel_width = window_width - left_panel_width
        self.splitter.setSizes([left_panel_width, right_panel_width])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.status_bar.setVisible(True)
        self.status_bar.showMessage("Ready")

        # Connect to current signal name (recordingItemSelected) and remove the old one (recordingSelected)
        self.recent_recordings_widget.recordingItemSelected.connect(self.main_transcription_widget.on_recording_item_selected)
        
        # Connect recording status updates from transcription widget to recent recordings list
        self.main_transcription_widget.recording_status_updated.connect(self.recent_recordings_widget.update_recording_status)

        # ------------------------------------------------------------------
        # Status updates – forward progress messages from the transcription
        # widget to the main window's status bar so the user can see what is
        # happening instead of the bar permanently showing "Ready".
        # ------------------------------------------------------------------
        self.main_transcription_widget.status_update.connect(self.update_status_bar)

    def set_style(self):
        # Not needed - styling is now handled by the ThemeManager
        pass

    def on_new_file(self, file_path_or_paths):
        """Handle new file(s).

Args:
    file_path_or_paths: path or list of paths
        """
        try:
            # Check if we have a list of files (chunks) or a single file
            if isinstance(file_path_or_paths, list):
                # For chunked files, add all chunks to the database
                file_paths = file_path_or_paths
                
                # If there's only one chunk, treat it as a normal file
                if len(file_paths) == 1:
                    self.on_new_file(file_paths[0])
                    return
                    
                # Handle multiple chunks
                date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Process each chunk
                for i, file_path in enumerate(file_paths):
                    filename = os.path.basename(file_path)
                    # Calculate the duration for each chunk using our utility function
                    duration = calculate_duration(file_path)
                    
                    # Create a recording in the database for each chunk
                    recording_data = (
                        f"{filename} (Chunk {i+1}/{len(file_paths)})", 
                        file_path, 
                        date_created, 
                        duration, 
                        "", 
                        ""
                    )
                    
                    # Define a closure to capture the current chunk's info for the callback
                    # Capture the current values of the loop variables inside a
                    # factory in order to avoid the classic late‑binding issue
                    # where all callbacks would reference the *last* values of
                    # the loop once it finishes.
                    def make_callback(fname: str, fpath: str, dur: float, created: str):
                        def _on_recording_created(recording_id):
                            self.recent_recordings_widget.add_recording_to_list(
                                recording_id,
                                fname,
                                fpath,
                                created,
                                dur,
                                "",
                                "",
                            )
                        return _on_recording_created
                    
                    # Add the chunk to the database with its specific callback
                    self.db_manager.create_recording(
                        recording_data,
                        make_callback(filename, file_path, duration, date_created),
                    )
                
                # Show a status message about the chunked files
                self.update_status_bar(f"Added {len(file_paths)} audio chunks")
                
            else:
                # Handle a single file (non-chunked)
                file_path = file_path_or_paths
                filename = os.path.basename(file_path)
                date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Calculate the duration of the recording using our utility function
                duration = calculate_duration(file_path)
                
                # Create a new recording in the database using the DatabaseManager
                recording_data = (filename, file_path, date_created, duration, "", "")
                
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
                    
                # Execute the database operation in a background thread
                self.db_manager.create_recording(recording_data, on_recording_created)
                
        except Exception as e:
            logger.error(f"Error processing new file: {e}", exc_info=True)
            self.update_status_bar(f"Error processing file: {str(e)}")

    def update_status_bar(self, message):
        """Update the status bar with a message."""
        self.statusBar().showMessage(message)
        logger.debug(f"Status bar updated: {message}")
        
    def _find_and_select_recording_item(self, parent_item, recording_id):
        """Recursively search for and select a recording item by ID."""
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

