import traceback
import datetime
import os
import logging
from PyQt6.QtCore import (
    pyqtSignal, QSize, Qt, QPropertyAnimation, QEasingCurve, QSortFilterProxyModel, QTimer,
    QThread, QUrl, QMimeData, QPoint
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QMessageBox, QWidget, QLabel, QListWidget, QMenu, QListWidgetItem,
    QHBoxLayout, QPushButton, QLineEdit, QComboBox, QInputDialog, QApplication, QSplitter,
    QFrame, QProgressDialog, QFileDialog, QToolButton, QToolBar, QStatusBar, QSizePolicy,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView
)
from PyQt6.QtGui import QIcon, QFont, QColor, QDesktopServices, QAction, QDrag
from app.RecordingListItem import RecordingListItem
from app.path_utils import resource_path
from app.path_utils import resource_path
from app.utils import create_backup, format_time_duration, PromptManager # Added PromptManager
# Use ui_utils for messages
from app.ui_utils import show_error_message, show_info_message, show_confirmation_dialog
from app.DatabaseManager import DatabaseManager
from app.ResponsiveUI import ResponsiveWidget, ResponsiveSizePolicy
from app.FolderManager import FolderManager
from app.file_utils import calculate_duration
from app.UnifiedFolderTreeView import UnifiedFolderTreeView

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Configured in main
logger = logging.getLogger('transcribrr')


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
        self.search_field.setStyleSheet("QLineEdit { border: 1px solid #ccc; border-radius: 4px; padding: 4px 8px; }")
        self.search_field.setToolTip("Search in filenames and transcript content")
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Has Transcript", "No Transcript", "Recent (24h)", "This Week"])
        self.filter_combo.currentTextChanged.connect(self.filterCriteriaChanged.emit)
        layout.addWidget(self.search_field, 3)
        layout.addWidget(self.filter_combo, 1)

    def clear_search(self): self.search_field.clear()
    def get_search_text(self): return self.search_field.text()
    def get_filter_criteria(self): return self.filter_combo.currentText()


class BatchProcessWorker(QThread):
    """Thread for batch processing recordings."""
    # TODO: Implement actual batch processing logic by integrating
    #       with TranscriptionThread and GPT4ProcessingThread.
    #       This currently only simulates progress.
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, recordings_data, process_type, parent=None): # Pass data, not widgets
        super().__init__(parent)
        self.recordings_data = recordings_data # List of dicts or tuples
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

                rec_id = rec_data['id']
                rec_name = rec_data['filename']
                progress_val = int(((i + 1) / total) * 100)
                status_msg = f"Processing {rec_name} ({i+1}/{total})"
                self.progress.emit(progress_val, status_msg)
                logger.debug(status_msg)

                # --- Placeholder for Actual Processing ---
                if self.process_type == "transcribe":
                    # Example: Start TranscriptionThread for rec_data['file_path']
                    # Need to handle thread management, config, keys etc.
                    # Wait for completion or manage multiple threads.
                    self.msleep(300) # Simulate work
                    pass
                elif self.process_type == "process":
                    # Example: Start GPT4ProcessingThread for rec_data['raw_transcript']
                    # Need to handle thread management, config, keys, prompts etc.
                    self.msleep(500) # Simulate work
                    pass
                # -----------------------------------------

            if not self._is_canceled:
                self.finished.emit(True, f"Batch '{self.process_type}' complete for {total} recordings.")
                logger.info(f"Batch '{self.process_type}' complete.")

        except Exception as e:
            error_msg = f"Error during batch {self.process_type}: {e}"
            logger.error(error_msg, exc_info=True)
            if not self._is_canceled:
                 self.finished.emit(False, error_msg)

    def cancel(self):
        logger.info(f"Cancellation requested for batch '{self.process_type}'.")
        self._is_canceled = True


class UnifiedFolderListWidget(QTreeWidget):
    """Combined folder and recording tree."""
    # Signals
    folderSelected = pyqtSignal(int, str)
    recordingSelected = pyqtSignal(RecordingListItem) # Keep emitting item for compatibility
    recordingNameChanged = pyqtSignal(int, str) # Signal for rename request
    
    # Recording tracking is now handled via the recordings_map
    # and item_map dictionaries

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.folder_manager = FolderManager.instance()
        self.current_folder_id = -1
        self.recordings_map = {} # Store RecordingListItem widgets by ID
        self.item_map = {} # Store QTreeWidgetItems by (type, id) for quick lookup
        self.seen_recording_ids = set() # Track seen recording IDs to prevent duplicates
        self._load_token = 0 # Monotonically increasing token to track valid callbacks
        self._is_loading = False # Flag to prevent signals during load
        
        # Connect to the dataChanged signal for unified refresh
        self.db_manager.dataChanged.connect(self.handle_data_changed)
        
        self.init_ui()

    def init_ui(self):
        self.setHeaderHidden(True)
        self.setIndentation(15) # Slightly reduced indentation
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection) # Allow multi-select
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.itemClicked.connect(self.on_item_clicked)
        self.itemDoubleClicked.connect(self.on_item_double_clicked) # Handle double click for rename
        self.itemExpanded.connect(self.on_item_expanded)
        self.itemCollapsed.connect(self.on_item_collapsed)

        # Icons
        folder_icon_path = resource_path('icons/folder.svg')
        folder_open_icon_path = resource_path('icons/folder_open.svg')
        self.folder_icon = QIcon(folder_icon_path) if os.path.exists(folder_icon_path) else QIcon.fromTheme("folder")
        self.folder_open_icon = QIcon(folder_open_icon_path) if os.path.exists(folder_open_icon_path) else QIcon.fromTheme("folder-open")
        self.audio_icon = QIcon(resource_path('icons/status/audio.svg'))
        self.video_icon = QIcon(resource_path('icons/status/video.svg'))
        self.file_icon = QIcon(resource_path('icons/status/file.svg'))

        self.load_structure() # Initial load

    def _refresh_with_expansion(self, expanded_folder_ids):
        """Refresh tree, keeping expansion.

Args:
    expanded_folder_ids: folder IDs to expand
        """
        # Store the currently selected item
        current_item = self.currentItem()
        current_id = None
        current_type = None
        
        if current_item:
            item_data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if item_data:
                current_id = item_data.get("id")
                current_type = item_data.get("type")
        
        # Reload the structure
        self.load_structure(current_id, current_type, expanded_folder_ids)
        
    def load_structure(self, select_item_id=None, item_type=None, expanded_folder_ids=None):
        """Load tree structure and recordings.

Args:
    select_item_id: ID to select after load
    item_type: "folder" or "recording"
    expanded_folder_ids: folder IDs to expand
        """
        self.clear()
        self.recordings_map.clear()
        self.item_map.clear()
        self.seen_recording_ids.clear() # Clear seen recordings set
        # Refresh with empty maps
        logger.debug("Starting tree structure refresh")
        self._is_loading = True # Flag to prevent signals during load
        self._load_token += 1 # Increment token to invalidate any pending callbacks
        current_token = self._load_token # Store current token for callbacks

        # Initialize expanded_folders if not provided
        if expanded_folder_ids is None:
            expanded_folder_ids = [-1]  # Always expand root by default
        
        # Check if we're filtering
        is_filtering = getattr(self, '_is_filtering', False)
        search_text = getattr(self, '_filtering_search', "").lower() if is_filtering else ""
        filter_criteria = getattr(self, '_filtering_criteria', "All") if is_filtering else "All"
        
        if is_filtering:
            logger.info(f"Loading structure with filter - Search: '{search_text}', Criteria: {filter_criteria}")

        # Add root item for unorganized recordings
        root_item = QTreeWidgetItem(self)
        root_item.setText(0, "Unorganized Recordings")
        root_item.setIcon(0, self.folder_icon)
        root_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": -1, "name": "Unorganized Recordings"})
        root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsDropEnabled) # Allow drop on root
        self.item_map[("folder", -1)] = root_item

        # Load folders
        root_folders = self.folder_manager.get_all_root_folders()
        for folder in sorted(root_folders, key=lambda f: f['name'].lower()): # Sort folders alphabetically
            # Skip folders during filtering unless we're searching by name
            if is_filtering and search_text and search_text not in folder['name'].lower():
                continue
            folder_item = self.add_folder_to_tree(folder, root_item)
            
            # Set folder expansion state based on expanded_folder_ids
            should_expand = folder['id'] in expanded_folder_ids
            folder_item.setExpanded(should_expand)
            
            # Load recordings for the folder
            self.load_recordings_for_item(folder_item, initial_load=True, current_token=self._load_token)
            
            # Recursively add child folders with their expansion states
            self._load_nested_folders_with_expansion(folder_item, folder, expanded_folder_ids)

        # Expand root initially
        root_item.setExpanded(True)

        # Load recordings for the root ("Unorganized Recordings")
        self.load_recordings_for_item(root_item, initial_load=True, current_token=current_token)

        # Restore selection if provided
        item_to_select = root_item # Default to root
        if select_item_id is not None:
             found_item = self.find_item_by_id(select_item_id, item_type)
             if found_item:
                  item_to_select = found_item
                  # Ensure parent is expanded
                  parent = item_to_select.parent()
                  while parent:
                       parent.setExpanded(True)
                       parent = parent.parent()

        self.setCurrentItem(item_to_select)
        self._is_loading = False
        
        # Finish loading
        logger.info(f"Tree structure loaded with {len(self.recordings_map)} recording items")
        
    def _load_nested_folders_with_expansion(self, parent_item, parent_data, expanded_folder_ids):
        """Recursively add child folders with proper expansion state.
        
        Args:
            parent_item: QTreeWidgetItem of the parent folder
            parent_data: Dictionary containing folder data
            expanded_folder_ids: List of folder IDs that should be expanded
        """
        # Process each child folder
        for child_folder in sorted(parent_data['children'], key=lambda f: f['name'].lower()):
            # Add the child folder to the tree
            child_item = self.add_folder_to_tree(child_folder, parent_item)
            
            # Set expansion state
            should_expand = child_folder['id'] in expanded_folder_ids
            child_item.setExpanded(should_expand)
            
            # Load recordings for this folder
            self.load_recordings_for_item(child_item, initial_load=True, current_token=self._load_token)
            
            # Process grandchildren recursively
            self._load_nested_folders_with_expansion(child_item, child_folder, expanded_folder_ids)

    def find_item_by_id(self, target_id, target_type):
        """Find an item by ID and type using the item_map."""
        # First try to use the efficient item_map
        key = (target_type, target_id)
        if key in self.item_map:
            return self.item_map[key]
        
        # Fallback to recursive search if not found in map
        def search_recursive(parent_item):
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("id") == target_id and data.get("type") == target_type:
                    # Add to map for future lookups
                    self.item_map[(target_type, target_id)] = child
                    return child
                # Recurse
                found = search_recursive(child)
                if found:
                    return found
            return None

        # Search from the invisible root item
        return search_recursive(self.invisibleRootItem())

    def add_folder_to_tree(self, folder_data, parent_item):
        """Add folder and its subfolders recursively."""
        recording_count = self.get_folder_recording_count(folder_data['id'])
        item = QTreeWidgetItem(parent_item)
        display_name = folder_data['name']
        if recording_count > 0:
            # display_name += f" ({recording_count})" # Keep display clean, maybe add tooltip later
            item.setForeground(0, QColor("#333333")) # Slightly darker for non-empty
        else:
            # display_name += " (empty)"
            item.setForeground(0, QColor("#888888")) # Lighter for empty

        item.setText(0, display_name)
        item.setIcon(0, self.folder_icon)
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder_data['id'], "name": folder_data['name']})
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsDragEnabled) # Allow drop/drag
        
        # Add to item_map for quick lookup
        self.item_map[("folder", folder_data['id'])] = item

        # We no longer use placeholders - we'll load everything upfront
        # This makes folders and their contents visible immediately
        pass

        # Recursively add children folders (sorted)
        child_items = []
        for child_folder in sorted(folder_data['children'], key=lambda f: f['name'].lower()):
            child_item = self.add_folder_to_tree(child_folder, item)
            child_items.append(child_item)
            
        # Return the created item so the caller can use it
        return item

    def load_recordings_for_item(self, folder_item, initial_load=False, force_ui_update=False, current_token=None):
        """Load recordings for the specified folder item.
        
        Args:
            folder_item: The folder tree item to load recordings for
            initial_load: Whether this is part of the initial tree construction
            force_ui_update: Whether to force an immediate UI update (for drag operations)
            current_token: Token to validate callbacks against the current load operation
        """
        folder_data = folder_item.data(0, Qt.ItemDataRole.UserRole)
        if not folder_data or folder_data.get("type") != "folder": return

        folder_id = folder_data.get("id")
        
        # Capture the current token value if not provided
        if current_token is None:
            current_token = self._load_token
            
        # Add a debug log to help diagnose the duplication issue
        logger.debug(f"Loading recordings for folder ID {folder_id} (initial_load={initial_load}, force_update={force_ui_update}, token={current_token})")

        # Check if we're filtering
        is_filtering = getattr(self, '_is_filtering', False)
        search_text = getattr(self, '_filtering_search', "").lower() if is_filtering else ""
        filter_criteria = getattr(self, '_filtering_criteria', "All") if is_filtering else "All"

        # Clear existing items - make sure we do this properly
        self._clear_folder_recordings(folder_item)

        # Define callback to add recordings to the UI
        def _add_recordings_to_ui(recordings):
            # Check if this callback is still valid
            if current_token != self._load_token:
                logger.debug(f"Aborting stale callback (token {current_token} vs current {self._load_token})")
                return  # Abort if token has changed
                
            if self.is_loading() and not initial_load: return # Abort if loading cancelled
            # Check if folder_item is still valid
            try: folder_item.text(0)
            except RuntimeError: return # Item was deleted

            visible_count = 0
            
            if recordings:
                # Sort recordings (e.g., by date descending)
                try:
                    sorted_recs = sorted(recordings, key=lambda r: datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S"), reverse=True)
                except Exception as e:
                    logger.warning(f"Could not sort recordings for folder {folder_id}: {e}")
                    sorted_recs = recordings

                # Filter recordings if filtering is active
                filtered_count = 0
                
                # Add recordings to the folder item
                for rec in sorted_recs:
                    # Check if folder_item is still valid before adding each child
                    try: folder_item.text(0)
                    except RuntimeError: return # Item was deleted

                    rec_id = rec[0]
                    # Avoid adding duplicates if this recording is already in ANY folder
                    if rec_id in self.recordings_map:
                        # Log the duplicate case for debugging
                        logger.debug(f"Skipping duplicate recording ID {rec_id} in folder refresh")
                        visible_count += 1  # Count existing items
                        continue

                    # Apply filtering if needed
                    if is_filtering:
                        should_add = True
                        
                        # Search text filter
                        if search_text:
                            # Check filename
                            filename = rec[1].lower()
                            name_match = search_text in filename
                            
                            # Check transcript content
                            transcript_match = False
                            if not name_match and rec[4]:  # Raw transcript
                                transcript_match = search_text in rec[4].lower()
                                
                            # Check processed text
                            if not name_match and not transcript_match and rec[5]:  # Processed text
                                transcript_match = search_text in rec[5].lower()
                                
                            should_add = name_match or transcript_match
                            
                            if not should_add:
                                filtered_count += 1
                                continue
                        
                        # Criteria filter
                        if filter_criteria != "All":
                            if filter_criteria == "Has Transcript":
                                # Check if raw transcript exists and isn't empty
                                has_transcript = rec[4] and rec[4].strip() != ""
                                if not has_transcript:  # No raw transcript
                                    logger.debug(f"Filtering out '{rec[1]}' - no transcript found")
                                    filtered_count += 1
                                    continue
                            elif filter_criteria == "No Transcript":
                                # Check if raw transcript exists and isn't empty
                                has_transcript = rec[4] and rec[4].strip() != ""
                                if has_transcript:  # Has raw transcript
                                    logger.debug(f"Filtering out '{rec[1]}' - has transcript")
                                    filtered_count += 1
                                    continue
                            elif filter_criteria in ["Recent (24h)", "This Week"]:
                                try:
                                    created_date = datetime.datetime.strptime(rec[3], "%Y-%m-%d %H:%M:%S")
                                    now = datetime.datetime.now()
                                    
                                    if filter_criteria == "Recent (24h)":
                                        if (now - created_date).total_seconds() >= 86400:  # Not in last 24h
                                            filtered_count += 1
                                            continue
                                    elif filter_criteria == "This Week":
                                        # Get start of current week (Monday)
                                        start_of_week = now - datetime.timedelta(days=now.weekday())
                                        start_of_week = datetime.datetime(start_of_week.year, start_of_week.month, start_of_week.day)
                                        if created_date < start_of_week:  # Not in current week
                                            filtered_count += 1
                                            continue
                                except (ValueError, TypeError) as e:
                                    logger.error(f"Date filtering error: {e}")
                                    filtered_count += 1
                                    continue

                    # Add recording item using helper method
                    self._add_recording_item(folder_item, rec)
                    visible_count += 1

                # Log filtering results
                if is_filtering:
                    logger.info(f"Filtered recordings: {filtered_count} hidden, {visible_count} visible")

            # Update folder count visually
            self._update_folder_display(folder_item, visible_count)
            
            # Force immediate UI update if requested (for drag operations)
            if force_ui_update:
                self.update()  # Force an immediate repaint
                folder_item.setExpanded(folder_item.isExpanded())  # Trick to force a layout update
            
        # Fetch recordings based on folder_id
        if folder_id == -1:  # Unorganized Recordings
            # Use the method to only show recordings not already in a folder
            self.folder_manager.get_recordings_not_in_folders(lambda success, result: 
                _add_recordings_to_ui(result) if success else None)
        else:  # Specific folder
            self.folder_manager.get_recordings_in_folder(folder_id, lambda success, result: 
                _add_recordings_to_ui(result) if success else None)

    def _add_recording_item(self, parent_item, recording_data):
        """Helper method to add a recording item to the tree."""
        rec_id = recording_data[0]
        
        # Check to prevent duplicates using canonical source of truth
        key = ("recording", rec_id)
        if key in self.item_map:
            logger.debug(f"Avoiding duplicate insertion of recording ID {rec_id} (already in item_map)")
            return None
            
        # Also check seen_recording_ids for duplicates across different refresh cycles
        if rec_id in self.seen_recording_ids:
            logger.debug(f"Avoiding duplicate insertion of recording ID {rec_id} (already in seen_recording_ids)")
            return None
            
        # Add to seen set for deduplication checks
        self.seen_recording_ids.add(rec_id)
            
        # Check if parent_item is still valid - an extra guard against items with deleted parents
        try:
            parent_valid = parent_item and parent_item.treeWidget() is self
            if not parent_valid:
                logger.debug(f"Parent item for recording ID {rec_id} was deleted")
                return None
        except RuntimeError:
            logger.debug(f"Parent item for recording ID {rec_id} had a runtime error - likely deleted")
            return None
        
        # Create widget
        list_item_widget = RecordingListItem(*recording_data)
        # Connect rename signal
        list_item_widget.nameChanged.connect(self.recordingNameChanged.emit)

        # Create tree item
        tree_item = QTreeWidgetItem(parent_item)
        tree_item.setSizeHint(0, list_item_widget.sizeHint())
        # Clear the display text to prevent overlapping with custom widget
        tree_item.setText(0, "")
        tree_item.setData(0, Qt.ItemDataRole.UserRole, {
            "type": "recording",
            "id": rec_id,
            "widget": list_item_widget # Store widget ref
        })
        tree_item.setFlags(tree_item.flags() | Qt.ItemFlag.ItemIsDragEnabled) # Make draggable
        
        # Add to tree and maps
        self.setItemWidget(tree_item, 0, list_item_widget)
        self.recordings_map[rec_id] = list_item_widget # Map ID to widget
        self.item_map[("recording", rec_id)] = tree_item # Add to item_map
        
        logger.debug(f"Added recording ID {rec_id} to parent folder")
        return tree_item

    def _add_folder_item(self, parent_item, folder_id, name):
        """Add a new folder item to the tree."""
        # Create item
        item = QTreeWidgetItem(parent_item)
        item.setText(0, name)
        item.setIcon(0, self.folder_icon)
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder_id, "name": name})
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDropEnabled | Qt.ItemFlag.ItemIsDragEnabled)
        
        # Add to map
        self.item_map[("folder", folder_id)] = item
        
        # Add placeholder for potential future content
        placeholder = QTreeWidgetItem(item)
        placeholder.setText(0, "loading...")
        placeholder.setData(0, Qt.ItemDataRole.UserRole, {"type": "placeholder"})
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        
        # Sort the parent's children alphabetically
        self._sort_folder_children(parent_item)
        
        return item

    def _remove_tree_item(self, item):
        """Remove an item from the tree and item maps."""
        # Get item data
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data:
            return
            
        item_type = item_data.get("type")
        item_id = item_data.get("id")
        
        # Remove from item_map
        if item_type and item_id is not None:
            self.item_map.pop((item_type, item_id), None)
        
        # If it's a recording, remove from recordings_map
        if item_type == "recording":
            self.recordings_map.pop(item_id, None)
            logger.debug(f"Removed recording ID {item_id} from recordings_map")
        
        # If it's a folder, remove all children recursively
        if item_type == "folder":
            # Make a copy of children since we'll be modifying the tree
            children = [item.child(i) for i in range(item.childCount())]
            for child in children:
                self._remove_tree_item(child)
        
        # Remove from parent
        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            # Root item
            index = self.indexOfTopLevelItem(item)
            if index >= 0:
                self.takeTopLevelItem(index)

    def _rename_folder_item(self, item, new_name):
        """Update a folder item's display name."""
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data or item_data.get("type") != "folder":
            return False
            
        # Update display text
        item.setText(0, new_name)
        
        # Update stored data
        item_data["name"] = new_name
        item.setData(0, Qt.ItemDataRole.UserRole, item_data)
        
        # Resort parent's children
        parent = item.parent()
        if parent:
            self._sort_folder_children(parent)
            
        return True

    def _move_recording_item_ui(self, recording_id, new_parent_item):
        """Move a recording item to a new parent folder in the UI."""
        # Find the recording item
        recording_item = self.find_item_by_id(recording_id, "recording")
        if not recording_item:
            return False
            
        # Get the widget before removing from tree
        item_data = recording_item.data(0, Qt.ItemDataRole.UserRole)
        widget = item_data.get("widget")
        
        # Remove from current parent
        old_parent = recording_item.parent()
        if old_parent:
            old_parent.removeChild(recording_item)
        
        # Add to new parent
        new_parent_item.addChild(recording_item)
        
        # Resort children if needed
        self._sort_folder_children(new_parent_item)
        
        return True

    def _update_folder_display(self, folder_item, recording_count=None):
        """Update a folder item's display (name, count, etc)."""
        folder_data = folder_item.data(0, Qt.ItemDataRole.UserRole)
        if not folder_data or folder_data.get("type") != "folder":
            return
            
        folder_name = folder_data.get("name", "Unknown")
        
        # If count is provided, update immediately
        if recording_count is not None:
            self._apply_folder_display_update(folder_item, folder_name, recording_count)
        else:
            # If count not provided, request it asynchronously
            folder_id = folder_data.get("id")
            if folder_id is not None:
                # Set a temporary display name while fetching count
                folder_item.setText(0, f"{folder_name} (...)")
                
                # Request count, will update display when received
                def on_count_received(count):
                    self._apply_folder_display_update(folder_item, folder_name, count)
                
                self.get_folder_recording_count(folder_id, on_count_received)
    
    def _apply_folder_display_update(self, folder_item, folder_name, recording_count):
        """Apply folder display updates with the provided count."""
        # Update visual display
        display_name = folder_name
        if recording_count is not None:
            display_name = f"{folder_name} ({recording_count})"
            
        folder_item.setText(0, display_name)
        
        # Update appearance based on content
        if recording_count and recording_count > 0:
            folder_item.setForeground(0, QColor("#333333"))  # Darker for non-empty
        else:
            folder_item.setForeground(0, QColor("#999999"))  # Lighter for empty

    def _sort_folder_children(self, folder_item):
        """Sort a folder's children alphabetically."""
        # Collect all children
        children = []
        for i in range(folder_item.childCount()):
            children.append(folder_item.child(i))
            
        # No need to sort if less than 2 children
        if len(children) < 2:
            return
            
        # Separate folders and recordings
        folders = []
        recordings = []
        placeholders = []
        
        for child in children:
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                continue
                
            child_type = data.get("type")
            if child_type == "folder":
                folders.append(child)
            elif child_type == "recording":
                recordings.append(child)
            elif child_type == "placeholder":
                placeholders.append(child)
        
        # Sort folders by name
        folders.sort(key=lambda item: item.text(0).lower())
        
        # Sort recordings (if they have widgets - might use recording widget name)
        # This is complex because recordings are custom widgets
        # For now, we'll keep their order as is
        
        # Remove all children
        for _ in range(folder_item.childCount()):
            folder_item.takeChild(0)
            
        # Add back in sorted order: folders first, then recordings, then placeholders
        for child in folders + recordings + placeholders:
            folder_item.addChild(child)

    def get_folder_recording_count(self, folder_id, callback=None):
        """Get folder recording count asynchronously.
        
        Args:
            folder_id: ID of the folder
            callback: Optional callback function that receives the count
            
        Returns:
            0 initially (the actual count will be passed to the callback)
        """
        def on_count_received(count):
            # If caller wants the callback directly
            if callback:
                callback(count)
                
            # Otherwise, find and update the folder display with the count
            if not callback:
                self._update_folder_with_count(folder_id, count)
        
        # Call the FolderManager async method
        FolderManager.instance().get_folder_recording_count(folder_id, on_count_received)
        
        # Return a default value (the real value will be in the callback)
        return 0
        
    def _update_folder_with_count(self, folder_id, count):
        """Update a folder's display with the count received asynchronously."""
        # Find the folder item
        folder_item = self._find_folder_item_by_id(folder_id)
        if folder_item:
            # Update its display
            self._update_folder_display(folder_item, count)
    
    def _find_folder_item_by_id(self, folder_id):
        """Recursively find a folder item by its ID.
        
        Args:
            folder_id: ID of the folder to find
            
        Returns:
            QTreeWidgetItem or None if not found
        """
        def search_item(item):
            # Check this item
            item_data = item.data(0, Qt.ItemDataRole.UserRole)
            if item_data and item_data.get("type") == "folder" and item_data.get("id") == folder_id:
                return item
                
            # Check children
            for i in range(item.childCount()):
                child = item.child(i)
                result = search_item(child)
                if result:
                    return result
                    
            return None
        
        # Search from root items
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            result = search_item(item)
            if result:
                return result
                
        return None

    def on_item_clicked(self, item, column):
        if self._is_loading: return # Ignore clicks during load

        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data: return

        item_type = item_data.get("type")
        if item_type == "folder":
            self.folderSelected.emit(item_data.get("id", -1), item_data.get("name", "Unknown"))
            # Clear selection from recordings if a folder is clicked
            # Or emit a signal indicating folder selection?
            # Let parent handle clearing selection if needed.
        elif item_type == "recording":
            widget = item_data.get("widget")
            if widget:
                self.recordingSelected.emit(widget) # Emit the widget instance

    def on_item_double_clicked(self, item, column):
         """Handle double-click to initiate rename for recordings."""
         item_data = item.data(0, Qt.ItemDataRole.UserRole)
         if item_data and item_data.get("type") == "recording":
              widget = item_data.get("widget")
              if widget and hasattr(widget, 'name_editable'):
                   widget.name_editable.mouseDoubleClickEvent(QApplication.instance().mouseButtons()) # Simulate double-click

    def on_item_expanded(self, item):
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if item_data and item_data.get("type") == "folder":
            # Just update the icon to show open folder
            item.setIcon(0, self.folder_open_icon)

    def on_item_collapsed(self, item):
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if item_data and item_data.get("type") == "folder":
            item.setIcon(0, self.folder_icon)
            # Optional: Could remove recording items here to save memory,
            # but might cause flicker on re-expand. For now, keep them loaded.

    # --- Context Menu Logic ---
    def show_context_menu(self, position):
        item = self.itemAt(position)
        if not item: return
        item_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not item_data: return

        menu = QMenu()
        item_type = item_data.get("type")

        if item_type == "folder":
            self._populate_folder_context_menu(menu, item, item_data)
        elif item_type == "recording":
            self._populate_recording_context_menu(menu, item, item_data)

        menu.exec(self.viewport().mapToGlobal(position))

    def _populate_folder_context_menu(self, menu: QMenu, item: QTreeWidgetItem, data: dict):
        folder_id = data.get("id")
        folder_name = data.get("name")

        # Actions applicable to all folders (including root "All Recordings")
        menu.addAction(QIcon(resource_path('icons/add.svg')), "New Subfolder", lambda: self.create_subfolder(item, folder_id))
        menu.addAction(QIcon(resource_path('icons/refresh.svg')), "Refresh", self.load_structure)

        if folder_id != -1: # Actions for specific folders only
            menu.addSeparator()
            menu.addAction(QIcon(resource_path('icons/rename.svg')), "Rename", lambda: self.rename_folder(item, folder_id))
            menu.addAction(QIcon(resource_path('icons/delete.svg')), "Delete", lambda: self.delete_folder(item, folder_id))


    def _populate_recording_context_menu(self, menu: QMenu, item: QTreeWidgetItem, data: dict):
        widget: RecordingListItem = data.get("widget")
        if not widget: return

        recording_id = widget.get_id()
        file_path = widget.get_filepath()
        filename = widget.get_filename() # Full filename
        has_transcript = widget.has_transcript()
        has_processed = widget.has_processed_text()

        # Common Actions
        menu.addAction(QIcon(resource_path('icons/folder_open.svg')), "Show in File Explorer", lambda: self.open_containing_folder(file_path))
        menu.addAction(QIcon(resource_path('icons/rename.svg')), "Rename", lambda: widget.name_editable.mouseDoubleClickEvent(QApplication.instance().mouseButtons())) # Trigger edit

        # Folder Management Submenu
        folder_menu = menu.addMenu(QIcon(resource_path('icons/folder.svg')), "Folder")
        folder_menu.addAction("Add to Folder...", lambda: self.add_recording_to_folder_dialog(widget))

        # Add "Remove from <Folder>" actions
        current_folders = widget.folders
        if current_folders:
             remove_menu = folder_menu.addMenu("Remove from Folder")
             for folder_info in current_folders:
                  folder_id = folder_info['id']
                  folder_name = folder_info['name']
                  remove_menu.addAction(f"{folder_name}", lambda fid=folder_id, fname=folder_name: self.remove_recording_from_folder_action(widget, fid, fname))

        # Transcript/Processing Actions
        menu.addSeparator()
        if has_transcript:
            menu.addAction(QIcon(resource_path('icons/clear.svg')), "Clear Transcript", lambda: self.clear_transcript(widget))
        if has_processed:
            menu.addAction(QIcon(resource_path('icons/clear.svg')), "Clear Processed Text", lambda: self.clear_processed_text(widget))

        # Export/Delete
        menu.addSeparator()
        menu.addAction(QIcon(resource_path('icons/export.svg')), "Export Recording File...", lambda: self.export_recording(file_path, filename))
        menu.addSeparator()
        menu.addAction(QIcon(resource_path('icons/delete.svg')), "Delete Recording", lambda: self.delete_recording_action(widget))


    # --- Action Handlers ---
    def create_subfolder(self, parent_item, parent_id):
        folder_name, ok = QInputDialog.getText(self, "Create Folder", "Enter folder name:", QLineEdit.EchoMode.Normal, "New Folder")
        if ok and folder_name:
            def on_folder_created(success, result):
                if success:
                    # Use targeted update instead of full reload
                    folder_id = result  # FolderManager returns the new folder ID
                    self._add_folder_item(parent_item, folder_id, folder_name)
                    parent_item.setExpanded(True)  # Expand parent to show new folder
                    
                    # Find and select the new folder
                    new_folder_item = self.find_item_by_id(folder_id, "folder")
                    if new_folder_item:
                        self.setCurrentItem(new_folder_item)
                else:
                    show_error_message(self, "Error", f"Failed to create folder: {result}")
            self.folder_manager.create_folder(folder_name, parent_id if parent_id != -1 else None, on_folder_created)

    def rename_folder(self, item, folder_id):
        current_name = item.data(0, Qt.ItemDataRole.UserRole)['name']
        new_name, ok = QInputDialog.getText(self, "Rename Folder", "Enter new folder name:", QLineEdit.EchoMode.Normal, current_name)
        if ok and new_name and new_name != current_name:
            def on_folder_renamed(success, result):
                if success:
                    # Use targeted update instead of full reload
                    self._rename_folder_item(item, new_name)
                else:
                    show_error_message(self, "Error", f"Failed to rename folder: {result}")
            self.folder_manager.rename_folder(folder_id, new_name, on_folder_renamed)

    def delete_folder(self, item, folder_id):
        folder_name = item.data(0, Qt.ItemDataRole.UserRole)['name']
        if show_confirmation_dialog(self, "Delete Folder", f"Delete folder '{folder_name}' and remove its recordings?"):
            def on_folder_deleted(success, result):
                if success:
                    # Use targeted update instead of full reload
                    self._remove_tree_item(item)
                    
                    # Select root after delete
                    root_item = self.item_map.get(("folder", -1))
                    if root_item:
                        self.setCurrentItem(root_item)
                else:
                    show_error_message(self, "Error", f"Failed to delete folder: {result}")
            self.folder_manager.delete_folder(folder_id, on_folder_deleted)

    def open_containing_folder(self, file_path):
        if not file_path or not os.path.exists(os.path.dirname(file_path)):
            show_error_message(self, "Folder Not Found", f"Could not find folder for: {file_path}")
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file_path)))
        except Exception as e:
             show_error_message(self, "Error", f"Could not open folder: {e}")

    def refresh_all_folders(self):
        """Refresh all folders to update counts and contents."""
        logger.debug("Refreshing all folders")
        # Delegate to the UnifiedFolderListWidget method
        self.unified_view.refresh_all_folders()
        
    def add_recording_to_folder_dialog(self, recording_widget: RecordingListItem):
        recording_id = recording_widget.get_id()
        recording_name = recording_widget.filename_no_ext

        folders = self.folder_manager.folders # Get flat list
        if not folders:
            show_info_message(self, "No Folders", "Create a folder first to organize recordings.")
            return

        folder_dict = {f"{folder['name']} (ID: {folder['id']})": folder['id'] for folder in folders}
        folder_display_names = sorted(folder_dict.keys())

        folder_display_name, ok = QInputDialog.getItem(self, "Add to Folder", f"Select folder for '{recording_name}':", folder_display_names, 0, False)
        if ok and folder_display_name:
            folder_id = folder_dict[folder_display_name]
            folder_name = folder_display_name.split(" (ID:")[0] # Extract name for message

            def on_add_complete(success, result):
                if success:
                    # Refresh this specific item's folder display
                    recording_widget.refresh_folders()
                    
                    # Refresh all folders to update counts and contents
                    self.refresh_all_folders()
                    
                    # Status message
                    if self.parent():
                        self.parent().show_status_message(f"Added '{recording_name}' to '{folder_name}'")
                    else:
                        logger.info(f"Added '{recording_name}' to '{folder_name}'")
                else: 
                    show_error_message(self, "Error", f"Failed to add to folder: {result}")
            self.folder_manager.add_recording_to_folder(recording_id, folder_id, on_add_complete)


    def remove_recording_from_folder_action(self, recording_widget: RecordingListItem, folder_id: int, folder_name: str):
        recording_id = recording_widget.get_id()
        recording_name = recording_widget.filename_no_ext
        if show_confirmation_dialog(self, "Remove from Folder", f"Remove '{recording_name}' from folder '{folder_name}'?"):
            def on_remove_complete(success, result):
                if success:
                    # Update recording's folder display
                    recording_widget.refresh_folders()
                    
                    # Refresh all folders to update counts and contents
                    self.refresh_all_folders()
                    
                    # Status message
                    if self.parent():
                        self.parent().show_status_message(f"Removed '{recording_name}' from '{folder_name}'")
                    else:
                        logger.info(f"Removed '{recording_name}' from '{folder_name}'")
                else:
                    show_error_message(self, "Error", f"Failed to remove from folder: {result}")
            self.folder_manager.remove_recording_from_folder(recording_id, folder_id, on_remove_complete)


    def clear_transcript(self, recording_widget: RecordingListItem):
        recording_id = recording_widget.get_id()
        if show_confirmation_dialog(self, "Clear Transcript", "Clear the transcript for this recording?"):
            def on_update_complete():
                 recording_widget.update_data({'raw_transcript': '', 'raw_transcript_formatted': None})
                 if self.parent():
                     self.parent().show_status_message("Transcript cleared")
                 else:
                     logger.info("Transcript cleared")
            self.db_manager.update_recording(recording_id, on_update_complete, raw_transcript="", raw_transcript_formatted=None)

    def clear_processed_text(self, recording_widget: RecordingListItem):
        recording_id = recording_widget.get_id()
        if show_confirmation_dialog(self, "Clear Processed Text", "Clear the processed text for this recording?"):
             def on_update_complete():
                  recording_widget.update_data({'processed_text': '', 'processed_text_formatted': None})
                  if self.parent():
                      self.parent().show_status_message("Processed text cleared")
                  else:
                      logger.info("Processed text cleared")
             self.db_manager.update_recording(recording_id, on_update_complete, processed_text="", processed_text_formatted=None)


    def export_recording(self, file_path, filename):
        if not file_path or not os.path.exists(file_path):
            show_error_message(self, "File Not Found", f"Original file not found at: {file_path}")
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Export Recording File", filename, "Audio/Video Files (*.mp3 *.wav *.m4a *.mp4 *.mov *.mkv)")
        if save_path:
            try:
                import shutil
                shutil.copy2(file_path, save_path)
                show_info_message(self, "Export Successful", f"Recording exported to:\n{save_path}")
                if self.parent():
                    self.parent().show_status_message(f"Exported to {os.path.basename(save_path)}")
                else:
                    logger.info(f"Exported to {os.path.basename(save_path)}")
            except Exception as e:
                show_error_message(self, "Export Error", f"Failed to export: {e}")

    def delete_recording_action(self, recording_widget: RecordingListItem):
        recording_id = recording_widget.get_id()
        file_path = recording_widget.get_filepath()
        filename = recording_widget.get_filename()

        if show_confirmation_dialog(self, 'Delete Recording', f"Delete '{filename}'? This also deletes the file and cannot be undone."):
            def on_delete_complete():
                try:
                    if file_path and os.path.exists(file_path):
                        # Optionally create backup before deleting file
                        # create_backup(file_path)
                        os.remove(file_path)
                        logger.info(f"Deleted file: {file_path}")
                except OSError as e:
                    logger.warning(f"Could not delete file {file_path}: {e}")
                    show_error_message(self, "File Deletion Error", 
                        f"Could not delete file:\n{file_path}\nError: {e}\n\nDatabase entry removed.")

                # Direct removal from tree view
                item = self.find_item_by_id(recording_id, "recording")
                if item:
                    self._remove_tree_item(item)

                # Status message
                if self.parent():
                    self.parent().show_status_message(f"Deleted '{filename}'")
                else:
                    logger.info(f"Deleted '{filename}'")

            # Delete from DB first
            self.db_manager.delete_recording(recording_id, on_delete_complete)


    # --- Drag and Drop ---
    def mimeTypes(self):
        return ['application/x-transcribrr-recording-id']

    def mimeData(self, items):
        if not items: return None
        # Only allow dragging recordings
        item = items[0]
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "recording":
             mime_data = QMimeData()
             mime_data.setData('application/x-transcribrr-recording-id', str(data['id']).encode())
             return mime_data
        return None

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-transcribrr-recording-id'):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        # Get the item under the cursor
        target_item = self.itemAt(event.position().toPoint())
        
        # Clear any previous highlight (restore normal style)
        if hasattr(self, '_last_highlighted_item') and self._last_highlighted_item:
            # Reset the background and foreground of the previously highlighted item
            self._last_highlighted_item.setBackground(0, QColor(0, 0, 0, 0))  # Transparent background
            
            # Reset any custom font we might have applied
            current_font = self._last_highlighted_item.font(0)
            current_font.setBold(False)
            self._last_highlighted_item.setFont(0, current_font)
            
            self._last_highlighted_item = None
            
        # Check if dropping onto a folder
        if target_item:
            target_data = target_item.data(0, Qt.ItemDataRole.UserRole)
            if target_data and target_data.get("type") == "folder":
                # Apply highlight to the current target item
                target_item.setBackground(0, QColor(180, 220, 255, 150))  # Light blue with increased opacity
                
                # Make the text bold to further emphasize the target
                current_font = target_item.font(0)
                current_font.setBold(True)
                target_item.setFont(0, current_font)
                
                # Save reference to highlighted item for later cleanup
                self._last_highlighted_item = target_item
                
                # Accept the drop
                event.acceptProposedAction()
                return
                
        event.ignore()  # Ignore drop elsewhere

    def dragLeaveEvent(self, event):
        # Clear highlight when drag leaves the widget
        if hasattr(self, '_last_highlighted_item') and self._last_highlighted_item:
            # Reset background 
            self._last_highlighted_item.setBackground(0, QColor(0, 0, 0, 0))  # Transparent background
            
            # Reset font
            current_font = self._last_highlighted_item.font(0)
            current_font.setBold(False)
            self._last_highlighted_item.setFont(0, current_font)
            
            self._last_highlighted_item = None
        event.accept()
    
    def dropEvent(self, event):
        # Clear any highlight when the drop occurs
        if hasattr(self, '_last_highlighted_item') and self._last_highlighted_item:
            # Reset background 
            self._last_highlighted_item.setBackground(0, QColor(0, 0, 0, 0))  # Transparent background
            
            # Reset font
            current_font = self._last_highlighted_item.font(0)
            current_font.setBold(False)
            self._last_highlighted_item.setFont(0, current_font)
            
            self._last_highlighted_item = None
            
        if not event.mimeData().hasFormat('application/x-transcribrr-recording-id'):
             event.ignore()
             return

        target_item = self.itemAt(event.position().toPoint())
        if not target_item:
             event.ignore()
             return

        target_data = target_item.data(0, Qt.ItemDataRole.UserRole)
        if not target_data or target_data.get("type") != "folder":
             event.ignore()
             return

        # Get recording ID being dragged
        recording_id = int(event.mimeData().data('application/x-transcribrr-recording-id').data().decode())
        target_folder_id = target_data.get("id")
        target_folder_name = target_data.get("name")

        # Find the source item
        source_item = self.find_item_by_id(recording_id, "recording")
        source_widget = None
        source_parent = None
        if source_item:
            try:
                source_widget = source_item.data(0, Qt.ItemDataRole.UserRole)['widget']
                source_parent = source_item.parent()  # Store the source parent for refreshing
            except (AttributeError, KeyError, TypeError) as e:
                logger.warning(f"Error getting source widget data: {e}")

        if source_widget and target_folder_id in [f['id'] for f in source_widget.folders]:
             show_info_message(self, "Already in Folder", f"Recording is already in '{target_folder_name}'.")
             event.ignore()
             return

        logger.info(f"Moving recording {recording_id} to folder {target_folder_id}")

        # Add to new folder in DB
        def on_add_complete(success, result):
            if success:
                # Update recording's folders reference
                if source_widget:
                    source_widget.refresh_folders()
                
                # Refresh all folders to update counts and contents
                self.refresh_all_folders()
                
                # Status message
                if self.parent():
                    self.parent().show_status_message(f"Moved recording to '{target_folder_name}'")
                else:
                    logger.info(f"Moved recording to '{target_folder_name}'")
                    
                # We no longer need the delayed full refresh since we do immediate targeted updates
                pass
            else:
                show_error_message(self, "Error", f"Failed to move recording: {result}")
                
        self.folder_manager.add_recording_to_folder(recording_id, target_folder_id, on_add_complete)
        event.acceptProposedAction()

    def is_loading(self):
        return getattr(self, '_is_loading', False)
        
    def handle_data_changed(self):
        """
        Central handler for DatabaseManager.dataChanged signal.
        This is the unified method for handling all data changes to avoid race conditions.
        It performs a complete rebuild of the tree while preserving state.
        """
        logger.info("Database data changed, performing unified refresh")
        
        # Increment load token to invalidate any pending callbacks
        self._load_token += 1
        current_token = self._load_token
        
        # Save the current selection (ID and type)
        selected_id = None
        selected_type = None
        current_item = self.currentItem()
        if current_item:
            data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                selected_id = data.get("id")
                selected_type = data.get("type")
                logger.debug(f"Saving selection: {selected_type} with ID {selected_id}")
        
        # Save IDs of all currently expanded folders
        expanded_folder_ids = []
        
        def collect_expanded_folders(item):
            if item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("type") == "folder":
                    expanded_folder_ids.append(data.get("id"))
            for i in range(item.childCount()):
                collect_expanded_folders(item.child(i))
        
        # Start collecting from the root item
        root_item = self.invisibleRootItem()
        for i in range(root_item.childCount()):
            collect_expanded_folders(root_item.child(i))
        
        # Pause UI updates to reduce flicker
        self.setUpdatesEnabled(False)
        
        # Set loading flag to prevent unwanted signals during rebuild
        self._is_loading = True
        
        try:
            # Clear all items from the tree and internal caches
            self.clear()
            self.recordings_map.clear()  
            self.item_map.clear()
            
            # Show a "Loading..." placeholder in the tree while refreshing
            temp_item = QTreeWidgetItem(self)
            temp_item.setText(0, "Loading...")
            
            # Define a function to rebuild the tree once folder data is ready
            def rebuild_tree_after_folder_load():
                # Check if this callback is still valid
                if current_token != self._load_token:
                    logger.debug(f"Aborting stale rebuild (token {current_token} vs current {self._load_token})")
                    return
                
                # Remove the temporary item
                self.takeTopLevelItem(0)
                
                # Now rebuild the tree with fresh data
                self.load_structure(selected_id, selected_type, expanded_folder_ids)
                
                # Enable UI updates again and refresh
                self.setUpdatesEnabled(True)
                self.update()
                self._is_loading = False
                
                logger.info("Unified data refresh complete")
            
            # Make sure the folder manager refreshes its internal data
            # and rebuild the tree only after folders are fully loaded
            self.folder_manager.load_folders(callback=rebuild_tree_after_folder_load)
            
        except Exception as e:
            logger.error(f"Error in unified refresh: {e}", exc_info=True)
            self._is_loading = False
            self.setUpdatesEnabled(True)
            
    def refresh_all_folders(self):
        """Refresh all folders to update counts and contents."""
        logger.debug("Refreshing all folders in UnifiedFolderListWidget")
        
        # Increment load token to invalidate any pending callbacks
        self._load_token += 1
        
        # First, get all expanded folder IDs to preserve expansion state
        expanded_folder_ids = []
        selected_id = None
        selected_type = None
        
        # Get currently selected item to maintain selection
        current_item = self.currentItem()
        if current_item:
            data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                selected_id = data.get("id")
                selected_type = data.get("type")
                logger.debug(f"Preserving selection of {selected_type} with ID {selected_id}")
        
        def collect_expanded_folders(item):
            if item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data.get("type") == "folder":
                    expanded_folder_ids.append(data.get("id"))
            for i in range(item.childCount()):
                collect_expanded_folders(item.child(i))
        
        # Start collecting from the root item
        root_item = self.invisibleRootItem()
        for i in range(root_item.childCount()):
            collect_expanded_folders(root_item.child(i))
        
        # Set loading flag and clear the maps to prevent duplicates
        self._is_loading = True
        logger.debug(f"Clearing recordings_map with {len(self.recordings_map)} entries before refresh")
        self.recordings_map.clear()
        self.item_map.clear()
        
        # Now reload the structure preserving expansion state and selection
        self.load_structure(selected_id, selected_type, expanded_folder_ids)
        
        # Refresh the UI
        self.update()
        logger.debug("Folder refresh complete")
        
    def _clear_folder_recordings(self, folder_item):
        """
        Args:
            folder_item: The folder item to clear recordings from
        """
        # Safety check
        if not folder_item:
            return
            
        # Create a list of items to remove (we can't remove while iterating)
        items_to_remove = []
        removed_ids = []  # Track which recording IDs we're removing
        
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            child_data = child.data(0, Qt.ItemDataRole.UserRole)
            
            # Only remove recordings and placeholders, not subfolders
            if child_data and child_data.get("type") in ["recording", "placeholder"]:
                items_to_remove.append(child)
                
                # Track recording ID if present
                if child_data.get("type") == "recording" and "id" in child_data:
                    rec_id = child_data.get("id")
                    removed_ids.append(rec_id)
                    
                    # Get the actual widget from the tree item
                    widget = self.itemWidget(child, 0)
                    if widget is not None:
                        self.removeItemWidget(child, 0)  # Detach widget
                        widget.deleteLater()  # Schedule widget for deletion
                    
                    # Clean up ALL tracking maps
                    self.item_map.pop(("recording", rec_id), None)
                    self.recordings_map.pop(rec_id, None)
                    self.seen_recording_ids.discard(rec_id)
                    logger.debug(f"Removed recording ID {rec_id} from tracking maps")
        
        # Now remove the items
        for item in items_to_remove:
            folder_item.removeChild(item)
            
        # Log what we did for debugging
        if items_to_remove:
            logger.debug(f"Cleared {len(items_to_remove)} recording items from folder")
    
    def _load_all_nested_folder_recordings(self, parent_item, expanded_folder_ids=None):
        """Recursively load recordings for all child folders.
        
        Args:
            parent_item: Parent folder item
            expanded_folder_ids: Optional list of folder IDs that should be expanded
        """
        # If expanded_folder_ids not provided, default to expanding all
        expand_all = expanded_folder_ids is None
        
        # Process each child
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            child_data = child.data(0, Qt.ItemDataRole.UserRole)
            
            # If this child is a folder, load its recordings
            if child_data and child_data.get("type") == "folder":
                # Load recordings for this folder
                self.load_recordings_for_item(child, initial_load=True)
                
                # Set expansion state
                folder_id = child_data.get("id")
                should_expand = expand_all or (expanded_folder_ids and folder_id in expanded_folder_ids)
                if should_expand:
                    child.setExpanded(True)
                
                # Recursively load recordings for its children
                self._load_all_nested_folder_recordings(child, expanded_folder_ids)
        
    def apply_filter(self, search_text: str, filter_criteria: str):
        """Apply a filter to show/hide items in the tree based on search text and criteria."""
        # Quick return if we're currently loading data
        if self.is_loading():
            logger.debug("Filtering canceled - tree is currently loading")
            return
        
        # Log filtering operation
        logger.info(f"Applying filter - Search: '{search_text}', Criteria: {filter_criteria}")
        
        # Store filter parameters for later use
        self._current_search = search_text
        self._current_filter = filter_criteria
        
        # In-place filtering approach: keep tree structure intact, just show/hide items
        logger.debug("Applying in-place filtering")
        self.blockSignals(True)  # Block signals during filtering
        
        # Reset flags for filtering
        self._is_filtering = True
        self._filtering_search = search_text
        self._filtering_criteria = filter_criteria
        
        # Get a reference to the root item
        root_item = self.invisibleRootItem()
        
        # Apply filtering recursively to all items without rebuilding the tree
        # Start with root-level items
        for i in range(root_item.childCount()):
            folder_item = root_item.child(i)
            self._filter_tree_item_recursive(folder_item, search_text.lower(), filter_criteria)
        
        # Keep root folder always visible 
        root_folder = self.item_map.get(("folder", -1))
        if root_folder:
            root_folder.setHidden(False)
            root_folder.setExpanded(True)  # Always expand root when filtering
                
        # Reset flags
        self._is_filtering = False
        self.blockSignals(False)  # Unblock signals
        
        # Force update only once after all changes are made
        self.viewport().update()
        logger.info("Filtering complete")
        
    def _filter_tree_item_recursive(self, item, search_text: str, filter_criteria: str) -> bool:
        """
        Apply filtering to an item and its children without rebuilding the tree.
        Returns True if the item or any of its children should be visible.
        """
        if not item:
            return False
            
        # Get item data
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return False
            
        item_type = data.get("type")
        item_visible = False
        
        # Process based on item type
        if item_type == "recording":
            # Handle recording items
            widget = data.get("widget")
            if not widget:
                item.setHidden(True)
                return False
                
            # Check if recording matches search text
            matches_search = True
            if search_text:
                # Search in filename
                name_matches = search_text in widget.filename_no_ext.lower()
                
                # Search in transcripts if name doesn't match
                transcript_matches = False
                if not name_matches:
                    # Check raw transcript
                    if widget.raw_transcript:
                        transcript_matches = search_text in widget.raw_transcript.lower()
                    
                    # If still no match, check processed text
                    if not transcript_matches and widget.processed_text:
                        transcript_matches = search_text in widget.processed_text.lower()
                
                matches_search = name_matches or transcript_matches
                
            # Check if recording matches filter criteria
            matches_criteria = True
            if filter_criteria == "Has Transcript":
                matches_criteria = bool(widget.raw_transcript)
            elif filter_criteria == "No Transcript":
                matches_criteria = not bool(widget.raw_transcript)
            elif filter_criteria == "Recent (24h)":
                try:
                    created_date = datetime.datetime.strptime(widget.date_created, "%Y-%m-%d %H:%M:%S")
                    now = datetime.datetime.now()
                    matches_criteria = (now - created_date).total_seconds() < 86400  # 24 hours in seconds
                except (ValueError, TypeError) as e:
                    logger.error(f"Error parsing date '{widget.date_created}': {e}")
                    matches_criteria = False
            elif filter_criteria == "This Week":
                try:
                    created_date = datetime.datetime.strptime(widget.date_created, "%Y-%m-%d %H:%M:%S")
                    now = datetime.datetime.now()
                    # Get start of current week (Monday)
                    start_of_week = now - datetime.timedelta(days=now.weekday())
                    start_of_week = datetime.datetime(start_of_week.year, start_of_week.month, start_of_week.day)
                    matches_criteria = created_date >= start_of_week
                except (ValueError, TypeError) as e:
                    logger.error(f"Error parsing date for week filter: {e}")
                    matches_criteria = False
                    
            # Recording is visible if it matches both search and criteria
            item_visible = matches_search and matches_criteria
            item.setHidden(not item_visible)
            
            # Also set the widget visibility to match
            if widget:
                widget.setVisible(item_visible)
            
            return item_visible
            
        elif item_type == "folder":
            # Handle folder items
            folder_name = data.get("name", "").lower()
            folder_id = data.get("id")
            
            # Check if folder name matches search text
            folder_matches_search = True
            if search_text:
                folder_matches_search = search_text in folder_name
            
            # Process all children recursively
            any_child_visible = False
            for i in range(item.childCount()):
                child = item.child(i)
                child_visible = self._filter_tree_item_recursive(child, search_text, filter_criteria)
                if child_visible:
                    any_child_visible = True
            
            # Folder is visible if it matches search or any child is visible
            item_visible = folder_matches_search or any_child_visible
            
            # Special handling for root folder (folder ID -1)
            if folder_id == -1:
                item_visible = True  # Root is always visible
                item.setExpanded(True)  # Always expand root when filtering
            else:
                # Hide or show based on visibility
                item.setHidden(not item_visible)
                
                # Auto-expand folders with visible children
                if item_visible and any_child_visible:
                    item.setExpanded(True)
            
            return item_visible
        elif item_type == "placeholder":
            # Always hide placeholders when filtering
            item.setHidden(True)
            return False
        
        # Default for unrecognized types
        item.setHidden(True)
        return False
        
    def _set_all_items_visible(self, item):
        """Helper function to make all items visible."""
        # Make this item visible
        item.setHidden(False)
        
        # Process all children
        for i in range(item.childCount()):
            child = item.child(i)
            child.setHidden(False)
            
            # Also make widget visible if this is a recording
            child_data = child.data(0, Qt.ItemDataRole.UserRole)
            if child_data and child_data.get("type") == "recording":
                widget = child_data.get("widget")
                if widget:
                    widget.setVisible(True)
            
            # Recursively process children
            self._set_all_items_visible(child)
        
    def _apply_filter_recursive(self, item, search_text: str, filter_criteria: str) -> bool:
        """
        Recursively apply filter to an item and its children.
        
        Args:
            item: The QTreeWidgetItem to process
            search_text: Text to search for (lowercase)
            filter_criteria: The filter criteria ("All", "Has Transcript", etc.)
            
        Returns:
            bool: True if this item or any child should be visible, False otherwise
        """
        # Safety check
        if not item:
            return False
            
        # Get item data
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return False
            
        item_type = data.get("type")
        
        # Remove console debug prints
        # if item.isHidden():
        #     print(f"Item is initially HIDDEN: {item_type}")
        # else:
        #     print(f"Item is initially VISIBLE: {item_type}")
            
        # Process based on item type
        if item_type == "recording":
            # Get the recording widget
            widget = data.get("widget")
            if not widget:
                return False
                
            # Check if recording matches search text
            matches_search = True
            if search_text:
                try:
                    # Search in filename
                    name_matches = search_text in widget.filename_no_ext.lower()
                    
                    # Search in transcripts if name doesn't match
                    transcript_matches = False
                    if not name_matches:
                        # Check raw transcript (more common)
                        if widget.raw_transcript:
                            transcript_matches = search_text in widget.raw_transcript.lower()
                        
                        # If still no match, check processed text
                        if not transcript_matches and widget.processed_text:
                            transcript_matches = search_text in widget.processed_text.lower()
                    
                    matches_search = name_matches or transcript_matches
                    
                    logger.debug(f"Search match for '{widget.filename_no_ext}': {matches_search}")
                    
                except Exception as e:
                    logger.error(f"Error in search matching: {e}")
                    matches_search = False
                
            # Check if recording matches filter criteria
            matches_criteria = True
            if filter_criteria == "Has Transcript":
                matches_criteria = bool(widget.raw_transcript)
                logger.debug(f"Has Transcript filter for '{widget.filename_no_ext}': {matches_criteria}")
            elif filter_criteria == "No Transcript":
                matches_criteria = not bool(widget.raw_transcript)
                logger.debug(f"No Transcript filter for '{widget.filename_no_ext}': {matches_criteria}")
            elif filter_criteria == "Recent (24h)":
                try:
                    created_date = datetime.datetime.strptime(widget.date_created, "%Y-%m-%d %H:%M:%S")
                    now = datetime.datetime.now()
                    matches_criteria = (now - created_date).total_seconds() < 86400  # 24 hours in seconds
                    logger.debug(f"Recent filter for '{widget.filename_no_ext}': {matches_criteria}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Error parsing date '{widget.date_created}': {e}")
                    matches_criteria = False
            elif filter_criteria == "This Week":
                try:
                    created_date = datetime.datetime.strptime(widget.date_created, "%Y-%m-%d %H:%M:%S")
                    now = datetime.datetime.now()
                    # Get start of current week (Monday)
                    start_of_week = now - datetime.timedelta(days=now.weekday())
                    start_of_week = datetime.datetime(start_of_week.year, start_of_week.month, start_of_week.day)
                    matches_criteria = created_date >= start_of_week
                    logger.debug(f"This Week filter for '{widget.filename_no_ext}': {matches_criteria}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Error parsing date for week filter: {e}")
                    matches_criteria = False
                    
            # Recording is visible if it matches both search and criteria
            visible = matches_search and matches_criteria
            
            # Use direct API to control visibility
            logger.debug(f"Setting hidden={not visible} for '{widget.filename_no_ext}'")
            
            # Force rendering update
            try:
                # Try direct widget hiding
                widget.setVisible(visible)
                item.setHidden(not visible)
                logger.debug(f"Widget visibility set to {visible}")
            except Exception as e:
                logger.error(f"Error setting visibility: {e}")
                item.setHidden(not visible)
            
            # Force redraw
            try:
                self.viewport().update()
            except Exception as e:
                logger.error(f"Error updating viewport: {e}")
                
            return visible
            
        elif item_type == "folder":
            # Check folder name for match if search text provided
            folder_matches_search = True
            folder_name = data.get("name", "").lower()
            if search_text:
                folder_matches_search = search_text in folder_name
                
            # Process all children
            any_child_visible = False
            for i in range(item.childCount()):
                child = item.child(i)
                child_visible = self._apply_filter_recursive(child, search_text, filter_criteria)
                if child_visible:
                    any_child_visible = True
                    
            # Folder is visible if it matches search or any child is visible
            visible = folder_matches_search or any_child_visible
            
            # Special handling for root folder
            is_root = data.get("id") == -1
            
            # Always keep root visible but expand/collapse based on filter
            if is_root:
                visible = True  # Root is always visible
                item.setExpanded(True)  # Always expand root
                logger.debug("Root folder - keeping visible and expanded")
            else:
                # For non-root folders
                logger.debug(f"Setting folder '{folder_name}' hidden={not visible}")
                item.setHidden(not visible)
                
                # If this folder is visible due to containing matching items,
                # expand it to show those matches
                if visible and any_child_visible and not folder_matches_search:
                    item.setExpanded(True)
                    logger.debug(f"Auto-expanding folder '{folder_name}' to show matches")
                    
            return visible
            
        elif item_type == "placeholder":
            # Always hide placeholders in filtering mode
            item.setHidden(True)
            return False
            
        # Default case
        return False


class RecentRecordingsWidget(ResponsiveWidget):
    # recordingSelected = pyqtSignal(str) # Replaced by recordingItemSelected
    # recordButtonPressed = pyqtSignal() # Handled internally by controls now
    recordingItemSelected = pyqtSignal(RecordingListItem) # Emit the item widget

    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(8)
        self.setSizePolicy(ResponsiveSizePolicy.preferred()) # Changed policy

        self.db_manager = db_manager or DatabaseManager(self)
        self.current_folder_id = -1 # Default to "All Recordings"

        # Create a timer for debouncing search
        self.filter_timer = QTimer()
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(250)  # 250ms debounce delay
        self.filter_timer.timeout.connect(self._apply_filter)
        self.pending_search_text = ""
        self.pending_filter_criteria = "All"
        
        self.init_toolbar() # Add toolbar

        # Header (Simplified - folder name updated by Unified view selection)
        self.header_label = QLabel("Recordings") # Static header
        self.header_label.setObjectName("RecentRecordingHeader")
        self.header_label.setFont(QFont("Arial", 14, QFont.Weight.Bold)) # Slightly larger
        self.layout.addWidget(self.header_label)

        # Search and filter
        self.search_widget = SearchWidget()
        self.search_widget.searchTextChanged.connect(self.filter_recordings)
        self.search_widget.filterCriteriaChanged.connect(self.filter_recordings)
        self.layout.addWidget(self.search_widget)

        # Unified folder and recordings view using model/view framework
        self.unified_view = UnifiedFolderTreeView(self.db_manager, self)
        self.unified_view.folderSelected.connect(self.on_folder_selected)
        self.unified_view.recordingSelected.connect(self.recordingItemSelected.emit) # Pass signal through
        self.unified_view.recordingNameChanged.connect(self.handle_recording_rename) # Connect rename handler
        self.layout.addWidget(self.unified_view, 1) # Allow view to stretch

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
        toolbar.setIconSize(QSize(18, 18)) # Slightly larger icons
        toolbar.setMovable(False)

        new_folder_action = QAction(QIcon(resource_path('icons/folder.svg')), "New Folder", self)
        new_folder_action.triggered.connect(self.create_new_folder)
        toolbar.addAction(new_folder_action)

        refresh_action = QAction(QIcon(resource_path('icons/refresh.svg')), "Refresh", self)
        refresh_action.triggered.connect(self.refresh_recordings)
        toolbar.addAction(refresh_action)

        toolbar.addSeparator()

        import_action = QAction(QIcon(resource_path('icons/import.svg')), "Import Files", self)
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
        file_dialog.setNameFilter("Media Files (*.mp3 *.wav *.m4a *.ogg *.mp4 *.mkv *.avi *.mov *.flac *.aac *.aiff *.wma *.webm *.flv *.wmv)")
        if file_dialog.exec() != QFileDialog.DialogCode.Accepted: return

        selected_files = file_dialog.selectedFiles()
        if not selected_files: return

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
                 self.add_imported_file_to_db(dest_path) # Add directly here

                 imported_count += 1
            except Exception as e:
                 logger.error(f"Error importing {file_path}: {e}", exc_info=True)
                 error_count += 1
                 show_error_message(self, "Import Error", f"Failed to import {os.path.basename(file_path)}: {e}")

        # Update status after import loop
        if error_count == 0:
            self.show_status_message(f"Import complete: {imported_count} files added.", 5000)
        else:
            self.show_status_message(f"Import complete: {imported_count} added, {error_count} failed.", 5000)

        self.refresh_recordings() # Refresh list after import


    def add_imported_file_to_db(self, file_path):
         """Adds an imported file record to the database."""
         try:
              filename = os.path.basename(file_path)
              date_created = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
              # Calculate duration (potential performance hit for many files)
              from app.file_utils import calculate_duration
              duration = calculate_duration(file_path) # Returns "HH:MM:SS" or "MM:SS"

              recording_data = (filename, file_path, date_created, duration, "", "")

              # Define callback (optional, can just refresh later)
              def on_import_added(recording_id):
                   if recording_id:
                        logger.info(f"Imported file '{filename}' added to DB with ID {recording_id}")
                   else:
                        logger.error(f"Failed to add imported file '{filename}' to DB")

              self.db_manager.create_recording(recording_data, on_import_added)
         except Exception as e:
              logger.error(f"Error preparing imported file '{file_path}' for DB: {e}", exc_info=True)
              show_error_message(self, "Import DB Error", f"Could not add '{os.path.basename(file_path)}' to database: {e}")

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
        
        # Refresh the selected folder to ensure we have the latest contents
        folder_item = self.unified_view.find_item_by_id(folder_id, "folder")
        if folder_item:
            self.unified_view.load_recordings_for_item(folder_item, force_ui_update=True)


    def update_recording_status(self, recording_id, status_updates):
        """Update the status of a recording item based on external processing events."""
        logger.info(f"Updating recording status for ID {recording_id}")
        
        # Find the recording widget in our map
        widget = self.unified_view.recordings_map.get(recording_id)
        if not widget:
            logger.error(f"Cannot update status: RecordingListItem widget not found for ID {recording_id}")
            return
        
        # Update the widget with new status
        widget.update_data(status_updates)
        
        # Refresh the visual appearance
        self.unified_view.viewport().update()

    def handle_recording_rename(self, recording_id: int, new_name_no_ext: str):
         """
         Handle the rename request from a RecordingListItem.
         Synchronizes both database and filesystem changes.
         """
         logger.info(f"Handling rename for ID {recording_id} to '{new_name_no_ext}'")

         # Construct new full filename (keep original extension)
         widget = self.unified_view.recordings_map.get(recording_id)
         if not widget:
              logger.error(f"Cannot rename: RecordingListItem widget not found for ID {recording_id}")
              return

         _ , ext = os.path.splitext(widget.get_filename())
         new_full_filename = new_name_no_ext + ext

         # Get current file path
         old_file_path = widget.file_path
         if not os.path.exists(old_file_path):
              logger.error(f"Cannot rename: Original file does not exist at {old_file_path}")
              show_error_message(self, "Rename Failed", "The original file could not be found on disk.")
              return

         # Generate new file path (same directory, new name)
         directory = os.path.dirname(old_file_path)
         new_file_path = os.path.join(directory, new_full_filename)

         # Check if target path already exists
         if os.path.exists(new_file_path):
              logger.error(f"Cannot rename: Target path already exists at {new_file_path}")
              show_error_message(self, "Rename Failed", "A file with this name already exists.")
              # Revert UI change
              widget.name_editable.setText(widget.filename_no_ext)
              return

         # --- Database Update with Filesystem Sync ---
         def on_rename_complete():
             try:
                 # Attempt to rename the physical file
                 os.rename(old_file_path, new_file_path)
                 logger.info(f"Successfully renamed file on disk from {old_file_path} to {new_file_path}")
                 
                 # Update the database with the new file path
                 self.db_manager.update_recording(
                     recording_id,
                     lambda: on_filesystem_sync_complete(),
                     file_path=new_file_path
                 )
             except OSError as e:
                 logger.error(f"Failed to rename file on disk: {e}")
                 show_error_message(self, "Rename Failed", f"Could not rename file on disk: {str(e)}")
                 # Revert the database change
                 self.db_manager.update_recording(
                     recording_id,
                     lambda: logger.info(f"Reverted database filename back to original"),
                     filename=os.path.basename(old_file_path)
                 )
                 # Revert UI change
                 widget.name_editable.setText(widget.filename_no_ext)

         def on_filesystem_sync_complete():
             logger.info(f"Successfully completed rename operation for recording {recording_id}")
             # Update the widget's internal state and UI
             widget.update_data({
                 'filename': new_name_no_ext,  # base name for UI
                 'file_path': new_file_path    # update file path reference
             })
             self.show_status_message(f"Renamed to '{new_name_no_ext}'")

         def on_rename_error(op_name, error_msg):
             logger.error(f"Failed to rename recording {recording_id} in DB: {error_msg}")
             show_error_message(self, "Rename Failed", f"Could not rename recording: {error_msg}")
             # Revert UI change if necessary
             widget.name_editable.setText(widget.filename_no_ext)

         # Create a unique connection ID for this specific rename operation
         connection_id = f"rename_{recording_id}_{new_name_no_ext}"
         
         # Disconnect any existing error handler for rename operations
         try:
             for signal in self.db_manager.error_occurred.receivers:
                 if hasattr(signal, '__self__') and signal.__self__.__name__.startswith('on_rename_error'):
                     self.db_manager.error_occurred.disconnect(signal)
         except (TypeError, AttributeError):
             pass
             
         # Connect the new error handler
         self.db_manager.error_occurred.connect(on_rename_error)

         # Start the transaction - first update the filename in DB
         self.db_manager.update_recording(
             recording_id,
             on_rename_complete,
             filename=new_full_filename
         )


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
            self.show_status_message(f"Filtering for: '{self.pending_search_text}'...", 250)
    
    def _apply_filter(self):
        """Apply the actual filtering logic after debounce."""
        search_text = self.pending_search_text
        filter_criteria = self.pending_filter_criteria
        folder_id = self.current_folder_id
        
        # Show status message based on filtering parameters
        if search_text:
            self.show_status_message(f"Searching for: '{search_text}' in names and transcripts")
        elif filter_criteria != "All":
            self.show_status_message(f"Filtering: {filter_criteria}")
        else:
            self.show_status_message("Showing all recordings")
            
        logger.info(f"Filtering recordings - Search: '{search_text}', Criteria: {filter_criteria}")
        
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

    def add_recording_to_list(self, recording_id, filename, file_path, date_created, duration, raw_transcript, processed_text):
        """Add a new recording to the recordings list."""
        # Find the root "All Recordings" folder - fix item_map reference
        root_item = self.unified_view.source_model.get_item_by_id(-1, "folder")
        if not root_item:
            logger.error("Root 'All Recordings' folder not found")
            return
            
        # Add recording to the folder directly
        recording_data = (recording_id, filename, file_path, date_created, duration, raw_transcript, processed_text)
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
            QTimer.singleShot(timeout + 100, lambda: self.status_bar.hide() if self.status_bar.currentMessage() == message else None)

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
                       selected_data.append({
                            'id': widget.get_id(),
                            'filename': widget.get_filename(),
                            'file_path': widget.get_filepath(),
                            'raw_transcript': widget.get_raw_transcript() # Needed for GPT processing
                       })

        if not selected_data:
            show_info_message(self, "No Selection", f"Please select recordings to {process_type}.")
            return

        action_text = "Transcribe" if process_type == "transcribe" else "Process with GPT"
        if not show_confirmation_dialog(self, f"Batch {action_text}", f"{action_text} {len(selected_data)} recording(s)?"):
            return

        self.progress_dialog = QProgressDialog(f"Starting batch {process_type}...", "Cancel", 0, 100, self)
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
              if self.progress_dialog: self.progress_dialog.setLabelText("Cancelling...")


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

         self.refresh_recordings() # Refresh list after batch operation
         self.batch_worker = None # Clear worker


    def batch_export(self):
         selected_items = self.unified_view.selectedItems()
         files_to_export = []
         for item in selected_items:
              data = item.data(0, Qt.ItemDataRole.UserRole)
              if data and data.get("type") == "recording":
                   widget = data.get("widget")
                   if widget and widget.get_filepath():
                        files_to_export.append((widget.get_filepath(), widget.get_filename()))

         if not files_to_export:
              show_info_message(self, "No Selection", "Select recordings with associated files to export.")
              return

         export_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
         if not export_dir: return

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
         show_info_message(self, "Not Implemented", "Sorting within the unified view is not yet implemented.")
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
