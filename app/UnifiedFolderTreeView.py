import os
import datetime
import logging
from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex, QTimer, QMimeData, QPoint
from PyQt6.QtWidgets import QTreeView, QAbstractItemView, QMenu
from PyQt6.QtGui import QIcon, QAction, QDrag
from app.RecordingFolderModel import RecordingFolderModel, RecordingFilterProxyModel
from app.RecordingListItem import RecordingListItem
from app.FolderManager import FolderManager
from app.path_utils import resource_path

logger = logging.getLogger('transcribrr')

class UnifiedFolderTreeView(QTreeView):
    """Combined folder and recording tree using Qt's Model/View framework."""
    
    # Signals
    folderSelected = pyqtSignal(int, str)
    recordingSelected = pyqtSignal(RecordingListItem)  # Keep for compatibility
    recordingNameChanged = pyqtSignal(int, str)  # Signal for rename request
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.folder_manager = FolderManager.instance()
        self.current_folder_id = -1
        self._load_token = 0  # Monotonically increasing token to track valid callbacks
        self._is_loading = False  # Flag to prevent signals during load
        self.recordings_map = {}  # Store RecordingListItem widgets by ID (for compatibility)
        self.seen_recording_ids = set()  # Track seen recording IDs to prevent duplicates
        
        # Connect to the dataChanged signal for unified refresh
        logger.info("Connecting to DatabaseManager.dataChanged signal for tree updates")
        self.db_manager.dataChanged.connect(self.handle_data_changed)
        
        # Create models
        self.source_model = RecordingFolderModel(self)
        self.proxy_model = RecordingFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        
        # Initialize UI
        self.init_ui()
        
        # Schedule a delayed refresh to ensure folder manager is fully initialized
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, lambda: self.handle_data_changed("init", -1))
        logger.info("Scheduled initial delayed refresh for tree view")
        
    def init_ui(self):
        """Initialize the tree view UI."""
        # Set model
        self.setModel(self.proxy_model)
        
        # Configure view
        self.setHeaderHidden(True)
        self.setIndentation(15)  # Slightly reduced indentation
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # Allow multi-select
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        
        # Connect signals
        self.clicked.connect(self.on_item_clicked)
        self.doubleClicked.connect(self.on_item_double_clicked)
        self.expanded.connect(self.on_item_expanded)
        self.collapsed.connect(self.on_item_collapsed)
        
        # Load icons
        folder_icon_path = resource_path('icons/folder.svg')
        folder_open_icon_path = resource_path('icons/folder_open.svg')
        
        self.folder_icon = QIcon(folder_icon_path) if os.path.exists(folder_icon_path) else QIcon.fromTheme("folder")
        self.folder_open_icon = QIcon(folder_open_icon_path) if os.path.exists(folder_open_icon_path) else QIcon.fromTheme("folder-open")
        self.audio_icon = QIcon(resource_path('icons/status/audio.svg'))
        self.video_icon = QIcon(resource_path('icons/status/video.svg'))
        self.file_icon = QIcon(resource_path('icons/status/file.svg'))
        
        # Set icons in model
        self.source_model.set_icons(
            self.folder_icon, 
            self.folder_open_icon,
            self.audio_icon,
            self.video_icon,
            self.file_icon
        )
        
        # Initial data load
        self.load_structure()
        
    def load_structure(self, select_item_id=None, item_type=None, expanded_folder_ids=None):
        """Load tree structure and recordings."""
        logger.info("Starting tree structure refresh with model/view approach")
        self._is_loading = True  # Flag to prevent signals during load
        self._load_token += 1  # Increment token to invalidate any pending callbacks
        current_token = self._load_token  # Store current token for callbacks
        logger.debug(f"Using load token: {current_token}")
        
        # Clear existing data
        self.source_model.clear_model()
        logger.debug(f"Cleared source model, entries before: {len(self.recordings_map)}")
        self.recordings_map.clear()
        self.seen_recording_ids.clear()  # Clear set of seen recording IDs
        logger.debug("Cleared recordings map and seen_recording_ids")
        
        # Initialize expanded_folders if not provided
        if expanded_folder_ids is None:
            expanded_folder_ids = [-1]  # Always expand root by default
            logger.debug("No expanded folder IDs provided, using default [-1]")
        else:
            logger.debug(f"Using provided expanded folder IDs: {expanded_folder_ids}")
        
        # Add root item for unorganized recordings
        root_folder = {"type": "folder", "id": -1, "name": "Unorganized Recordings", "children": []}
        root_item = self.source_model.add_folder_item(root_folder)
        logger.info("Added root folder item for unorganized recordings")
        
        # Load root folders
        root_folders = self.folder_manager.get_all_root_folders()
        logger.info(f"Found {len(root_folders)} root folders")
        
        for folder in sorted(root_folders, key=lambda f: f['name'].lower()):
            logger.debug(f"Processing root folder: {folder['name']} (ID: {folder['id']})")
            folder_item = self.source_model.add_folder_item(folder, root_item)
            
            # Set folder expansion state
            folder_index = self.proxy_model.mapFromSource(folder_item.index())
            is_expanded = folder['id'] in expanded_folder_ids
            self.setExpanded(folder_index, is_expanded)
            logger.debug(f"Set expansion state for folder {folder['name']}: {is_expanded}")
            
            # Recursively add child folders
            self._load_nested_folders(folder_item, folder, expanded_folder_ids)
            
            # Load recordings for this folder
            logger.debug(f"Requesting recordings for folder ID {folder['id']}")
            self._load_recordings_for_folder(folder['id'], folder_item, current_token)
        
        # Load unorganized recordings
        logger.info("Requesting unorganized recordings")
        self._load_recordings_for_folder(-1, root_item, current_token)
        
        # Expand root initially
        root_index = self.proxy_model.mapFromSource(root_item.index())
        self.setExpanded(root_index, True)
        logger.debug("Expanded root folder")
        
        # Restore selection if provided
        if select_item_id is not None and item_type is not None:
            logger.debug(f"Attempting to restore selection: {item_type} with ID {select_item_id}")
            item = self.source_model.get_item_by_id(select_item_id, item_type)
            if item:
                index = self.proxy_model.mapFromSource(item.index())
                self.setCurrentIndex(index)
                self.scrollTo(index)
                logger.debug(f"Restored selection to {item_type} {select_item_id}")
                
                # Ensure parents are expanded
                parent_index = index.parent()
                while parent_index.isValid():
                    self.setExpanded(parent_index, True)
                    parent_index = parent_index.parent()
            else:
                logger.warning(f"Could not find item to restore selection: {item_type} with ID {select_item_id}")
        
        # Check model content after loading
        logger.info(f"Tree structure loaded with {self.source_model.rowCount()} top-level items")
        logger.info(f"Recordings map contains {len(self.recordings_map)} recordings")
        
        self._is_loading = False
        logger.info("Tree structure loading completed")
        
    def _load_nested_folders(self, parent_item, parent_folder, expanded_folder_ids):
        """Recursively load nested folders."""
        if not parent_folder.get('children'):
            logger.debug(f"No children for folder {parent_folder.get('name')} (ID: {parent_folder.get('id')})")
            return
            
        logger.debug(f"Loading {len(parent_folder['children'])} nested folders for parent {parent_folder.get('name')} (ID: {parent_folder.get('id')})")
        
        for child_folder in sorted(parent_folder['children'], key=lambda f: f['name'].lower()):
            logger.debug(f"Processing child folder: {child_folder['name']} (ID: {child_folder['id']})")
            child_item = self.source_model.add_folder_item(child_folder, parent_item)
            
            # Set expansion state
            child_index = self.proxy_model.mapFromSource(child_item.index())
            is_expanded = child_folder['id'] in expanded_folder_ids if expanded_folder_ids else False
            self.setExpanded(child_index, is_expanded)
            logger.debug(f"Set expansion state for folder {child_folder['name']}: {is_expanded}")
            
            # Load recordings for this folder
            current_token = self._load_token  # Get current token for consistency
            logger.debug(f"Requesting recordings for folder ID {child_folder['id']}")
            self._load_recordings_for_folder(child_folder['id'], child_item, current_token)
            
            # Recursively process children
            self._load_nested_folders(child_item, child_folder, expanded_folder_ids)
            
    def _load_recordings_for_folder(self, folder_id, folder_item, current_token):
        """Load recordings for a specific folder."""
        logger.debug(f"Loading recordings for folder ID {folder_id} with token {current_token}")
        
        # Load recordings from database
        if folder_id == -1:
            # Unorganized recordings (not in any folder)
            def _add_unassigned_recordings(success, recordings):
                logger.info(f"Callback _add_unassigned_recordings called, success={success}, received {len(recordings) if recordings else 0} recordings")
                
                if not success:
                    logger.error("Failed to load unassigned recordings")
                    return
                    
                if current_token != self._load_token:
                    logger.warning(f"Skipping stale loading operation (token {current_token} vs current {self._load_token})")
                    return
                
                if not recordings:
                    logger.info("No unassigned recordings found")
                    return
                
                logger.info(f"Processing {len(recordings)} unassigned recordings")
                    
                # Sort recordings by date (newest first)
                try:
                    sorted_recs = sorted(recordings, key=lambda r: datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S"), reverse=True)
                except Exception as e:
                    logger.warning(f"Could not sort unassigned recordings: {e}")
                    sorted_recs = recordings
                    
                # Add recordings to the model
                added_count = 0
                skipped_count = 0
                for rec in sorted_recs:
                    rec_id = rec[0]
                    # Skip if already added - check both maps for comprehensive deduplication
                    key = ("recording", rec_id)
                    if key in self.source_model.item_map or rec_id in self.recordings_map or rec_id in self.seen_recording_ids:
                        logger.debug(f"Skipping recording ID {rec_id}, already tracked in one of the maps")
                        skipped_count += 1
                        continue
                    
                    # Mark as seen for deduplication
                    self.seen_recording_ids.add(rec_id)
                    
                    # Create RecordingListItem for compatibility - fix parameter order
                    recording_item = RecordingListItem(
                        rec_id, rec[1], rec[2], rec[3], 
                        rec[4], # duration
                        rec[5], # raw_transcript
                        rec[6], # processed_text
                        rec[7], # raw_transcript_formatted
                        rec[8], # processed_text_formatted
                        parent=self
                    )
                    # Store db_manager as a property - fix QWidget constructor issue
                    recording_item.db_manager = self.db_manager
                    self.recordings_map[rec_id] = recording_item
                    
                    # Add to the model
                    self.source_model.add_recording_item(rec, folder_item)
                    added_count += 1
                    logger.debug(f"Added unassigned recording ID {rec_id}: {rec[1]}")
                
                logger.info(f"Added {added_count} unassigned recordings, skipped {skipped_count}")
            
            # Use folder manager to get unassigned recordings
            logger.info("Requesting unassigned recordings from folder manager")
            self.folder_manager.get_recordings_not_in_folders(_add_unassigned_recordings)
        else:
            # Regular folder
            def _add_folder_recordings(success, recordings):
                logger.info(f"Callback _add_folder_recordings for folder {folder_id} called, success={success}, received {len(recordings) if recordings else 0} recordings")
                
                if not success:
                    logger.error(f"Failed to load recordings for folder {folder_id}")
                    return
                    
                if current_token != self._load_token:
                    logger.warning(f"Skipping stale loading operation for folder {folder_id} (token {current_token} vs current {self._load_token})")
                    return
                
                if not recordings:
                    logger.info(f"No recordings found in folder {folder_id}")
                    return
                
                logger.info(f"Processing {len(recordings)} recordings for folder {folder_id}")
                    
                # Sort recordings by date (newest first)
                try:
                    sorted_recs = sorted(recordings, key=lambda r: datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S"), reverse=True)
                except Exception as e:
                    logger.warning(f"Could not sort recordings for folder {folder_id}: {e}")
                    sorted_recs = recordings
                    
                # Add recordings to the model
                added_count = 0
                skipped_count = 0
                for rec in sorted_recs:
                    rec_id = rec[0]
                    # Skip if already added - check both maps for comprehensive deduplication
                    key = ("recording", rec_id)
                    if key in self.source_model.item_map or rec_id in self.recordings_map or rec_id in self.seen_recording_ids:
                        logger.debug(f"Skipping recording ID {rec_id} in folder {folder_id}, already tracked in one of the maps")
                        skipped_count += 1
                        continue
                    
                    # Mark as seen for deduplication
                    self.seen_recording_ids.add(rec_id)
                    
                    # Create RecordingListItem for compatibility - fix parameter order
                    recording_item = RecordingListItem(
                        rec_id, rec[1], rec[2], rec[3], 
                        rec[4], # duration
                        rec[5], # raw_transcript
                        rec[6], # processed_text
                        rec[7], # raw_transcript_formatted
                        rec[8], # processed_text_formatted
                        parent=self
                    )
                    # Store db_manager as a property - fix QWidget constructor issue
                    recording_item.db_manager = self.db_manager
                    self.recordings_map[rec_id] = recording_item
                    
                    # Add to the model
                    self.source_model.add_recording_item(rec, folder_item)
                    added_count += 1
                    logger.debug(f"Added recording ID {rec_id} to folder {folder_id}: {rec[1]}")
                
                logger.info(f"Added {added_count} recordings to folder {folder_id}, skipped {skipped_count}")
            
            # Get recordings for this folder
            logger.info(f"Requesting recordings for folder {folder_id} from folder manager")
            self.folder_manager.get_recordings_in_folder(folder_id, _add_folder_recordings)
            
    def set_filter(self, search_text, filter_criteria):
        """Apply filter to the tree view."""
        logger.info(f"Setting filter - Search: '{search_text}', Criteria: {filter_criteria}")
        self.proxy_model.setFilterText(search_text)
        self.proxy_model.setFilterCriteria(filter_criteria)
        
        # Expand all folders when filtering
        if search_text or filter_criteria != "All":
            self.expandAll()
        else:
            # Collapse all except root when clearing filter
            self.collapseAll()
            # Expand root
            root_item = self.source_model.item(0, 0)
            if root_item:
                root_index = self.proxy_model.mapFromSource(root_item.index())
                self.setExpanded(root_index, True)
                
    # Compatibility method for legacy code that might call apply_filter instead of set_filter
    def apply_filter(self, search_text, filter_criteria):
        """Legacy method - redirects to set_filter for compatibility."""
        logger.info(f"Legacy apply_filter called, redirecting to set_filter")
        self.set_filter(search_text, filter_criteria)
        
    # ----- Compatibility methods for QTreeWidget API -----
    
    def invisibleRootItem(self):
        """Compatibility method for QTreeWidget API."""
        # Return a proxy object that emulates a QTreeWidgetItem
        class ProxyRootItem:
            def __init__(self, tree_view):
                self.tree_view = tree_view
                
            def childCount(self):
                return self.tree_view.model().rowCount()
                
            def child(self, row):
                index = self.tree_view.model().index(row, 0)
                if not index.isValid():
                    return None
                return self.tree_view.ProxyTreeItem(self.tree_view, index)
                
        return ProxyRootItem(self)
        
    def find_item_by_id(self, target_id, target_type):
        """Find an item by ID and type."""
        item = self.source_model.get_item_by_id(target_id, target_type)
        if item:
            return self.ProxyTreeItem(self, self.proxy_model.mapFromSource(item.index()))
        return None
        
    def currentItem(self):
        """Get the current item (compatibility with QTreeWidget)."""
        index = self.currentIndex()
        if not index.isValid():
            logger.debug("No current item selected")
            return None
        logger.debug("Returning current item proxy")
        return self.ProxyTreeItem(self, index)
        
    def get_folder_recording_count(self, folder_id, callback=None):
        """Get the number of recordings in a folder."""
        # If there's a callback, use the folder manager to get the count asynchronously
        if callback:
            self.folder_manager.get_folder_recording_count(folder_id, callback)
            return 0  # Return a placeholder, real value will be provided in callback
            
        # Otherwise use a synchronous count of model items (less accurate but immediate)
        folder_item = self.source_model.get_item_by_id(folder_id, "folder")
        if not folder_item:
            return 0
            
        # Count recording items directly in the model
        count = 0
        for row in range(folder_item.rowCount()):
            child = folder_item.child(row, 0)
            if child and child.data(RecordingFolderModel.ITEM_TYPE_ROLE) == "recording":
                count += 1
                
        return count
        
    # Helper methods for compatibility with QTreeWidget API
    
    def topLevelItem(self, index):
        """Get a top-level item by index - compatibility with QTreeWidget."""
        if index >= self.source_model.rowCount():
            return None
            
        item = self.source_model.item(index, 0)
        if not item:
            return None
            
        # Return as ProxyTreeItem for compatibility
        proxy_index = self.proxy_model.mapFromSource(item.index())
        return self.ProxyTreeItem(self, proxy_index)
        
    # This class emulates a QTreeWidgetItem for compatibility
    class ProxyTreeItem:
        def __init__(self, tree_view, index):
            self.tree_view = tree_view
            self.index = index
            
        def data(self, column, role):
            source_index = self.tree_view.proxy_model.mapToSource(self.index)
            item = self.tree_view.source_model.itemFromIndex(source_index)
            if role == Qt.ItemDataRole.UserRole:
                return {
                    "type": item.data(RecordingFolderModel.ITEM_TYPE_ROLE),
                    "id": item.data(RecordingFolderModel.ITEM_ID_ROLE),
                    "name": item.text()
                }
            return self.tree_view.model().data(self.index, role)
            
        def childCount(self):
            return self.tree_view.model().rowCount(self.index)
            
        def child(self, row):
            child_index = self.tree_view.model().index(row, 0, self.index)
            if not child_index.isValid():
                return None
            return self.tree_view.ProxyTreeItem(self.tree_view, child_index)
            
        def text(self, column=0):
            return self.tree_view.model().data(self.index, Qt.ItemDataRole.DisplayRole)
            
        def isExpanded(self):
            return self.tree_view.isExpanded(self.index)
            
        def setExpanded(self, expanded):
            self.tree_view.setExpanded(self.index, expanded)
            
        def parent(self):
            parent_index = self.index.parent()
            if not parent_index.isValid():
                return None
            return self.tree_view.ProxyTreeItem(self.tree_view, parent_index)
                
    def handle_data_changed(self, entity_type=None, entity_id=None):
        """Handle data change notifications."""
        if self._is_loading:
            logger.warning("Ignoring data change notification while loading")
            return
            
        logger.info(f"Handle data changed: {entity_type} {entity_id}")
        
        # Store expanded folders
        expanded_folder_ids = self.get_expanded_folder_ids()
        logger.debug(f"Expanded folder IDs: {expanded_folder_ids}")
        
        # Get currently selected item
        current_index = self.currentIndex()
        current_id = None
        current_type = None
        
        if current_index.isValid():
            source_index = self.proxy_model.mapToSource(current_index)
            item = self.source_model.itemFromIndex(source_index)
            if item:
                current_type = item.data(RecordingFolderModel.ITEM_TYPE_ROLE)
                current_id = item.data(RecordingFolderModel.ITEM_ID_ROLE)
                logger.debug(f"Selected item: {current_type} with ID {current_id}")
        else:
            logger.debug("No item currently selected")
                
        # Reload structure
        logger.info(f"Triggering structure reload due to data change")
        self.load_structure(current_id, current_type, expanded_folder_ids)
        
    def get_expanded_folder_ids(self):
        """Get IDs of all expanded folders."""
        expanded_ids = [-1]  # Root is always expanded
        
        def collect_expanded(parent_index):
            rows = self.model().rowCount(parent_index)
            for row in range(rows):
                index = self.model().index(row, 0, parent_index)
                if not index.isValid():
                    continue
                    
                # Map to source model
                source_index = self.proxy_model.mapToSource(index)
                item = self.source_model.itemFromIndex(source_index)
                
                if item and item.data(RecordingFolderModel.ITEM_TYPE_ROLE) == "folder":
                    folder_id = item.data(RecordingFolderModel.ITEM_ID_ROLE)
                    
                    if self.isExpanded(index):
                        expanded_ids.append(folder_id)
                        
                    # Recursively check children
                    collect_expanded(index)
                    
        # Start from the root
        collect_expanded(QModelIndex())
        return expanded_ids
        
    def on_item_clicked(self, index):
        """Handle item click."""
        if self._is_loading:
            return
            
        source_index = self.proxy_model.mapToSource(index)
        item = self.source_model.itemFromIndex(source_index)
        
        if not item:
            return
            
        item_type = item.data(RecordingFolderModel.ITEM_TYPE_ROLE)
        item_id = item.data(RecordingFolderModel.ITEM_ID_ROLE)
        
        if item_type == "folder":
            self.current_folder_id = item_id
            self.folderSelected.emit(item_id, item.text())
        elif item_type == "recording":
            if item_id in self.recordings_map:
                recording_item = self.recordings_map[item_id]
                self.recordingSelected.emit(recording_item)
                
    def on_item_double_clicked(self, index):
        """Handle item double click (rename)."""
        # Implementation for rename functionality
        pass
        
    def on_item_expanded(self, index):
        """Handle item expansion."""
        source_index = self.proxy_model.mapToSource(index)
        item = self.source_model.itemFromIndex(source_index)
        
        if item and item.data(RecordingFolderModel.ITEM_TYPE_ROLE) == "folder":
            item.setIcon(self.folder_open_icon)
            
    def on_item_collapsed(self, index):
        """Handle item collapse."""
        source_index = self.proxy_model.mapToSource(index)
        item = self.source_model.itemFromIndex(source_index)
        
        if item and item.data(RecordingFolderModel.ITEM_TYPE_ROLE) == "folder":
            item.setIcon(self.folder_icon)
            
    def show_context_menu(self, position):
        """Show context menu for tree items."""
        # Get the item at the requested position
        index = self.indexAt(position)
        if not index.isValid():
            return
            
        # Convert to source model
        source_index = self.proxy_model.mapToSource(index)
        item = self.source_model.itemFromIndex(source_index)
        
        if not item:
            return
            
        # Get item data
        item_type = item.data(RecordingFolderModel.ITEM_TYPE_ROLE)
        item_id = item.data(RecordingFolderModel.ITEM_ID_ROLE)
        
        # Create context menu
        menu = QMenu(self)
        
        if item_type == "folder":
            # Folder options
            new_subfolder_action = menu.addAction("New Subfolder")
            new_subfolder_action.triggered.connect(lambda: self.create_subfolder(item_id))
            
            if item_id != -1:  # Not the root folder
                menu.addSeparator()
                rename_action = menu.addAction("Rename Folder")
                rename_action.triggered.connect(lambda: self.rename_folder(item_id))
                
                delete_action = menu.addAction("Delete Folder")
                delete_action.triggered.connect(lambda: self.delete_folder(item_id))
        
        elif item_type == "recording":
            # Recording options
            # (Add recording-specific actions here)
            pass
            
        # Show the menu
        if not menu.isEmpty():
            menu.exec(self.viewport().mapToGlobal(position))
            
    def create_subfolder(self, parent_id):
        """Create a new subfolder under the specified parent folder."""
        logger.info(f"Creating subfolder under parent ID {parent_id}")
        
        # Prompt for folder name
        from PyQt6.QtWidgets import QInputDialog
        folder_name, ok = QInputDialog.getText(
            self, "Create Folder", "Enter folder name:", text="New Folder"
        )
        
        if not ok or not folder_name.strip():
            logger.debug("Folder creation canceled or empty name provided")
            return
            
        # Create the folder
        def on_folder_created(success, result):
            if success:
                folder_id = result
                logger.info(f"Successfully created folder {folder_name} with ID {folder_id}")
                # Trigger a refresh
                self.handle_data_changed("folder", folder_id)
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Failed to create folder: {result}")
                logger.error(f"Failed to create folder: {result}")
                
        self.folder_manager.create_folder(folder_name, parent_id, on_folder_created)
        
    def rename_folder(self, folder_id):
        """Rename a folder."""
        logger.info(f"Renaming folder with ID {folder_id}")
        
        # Get current folder name
        folder_item = self.source_model.get_item_by_id(folder_id, "folder")
        if not folder_item:
            logger.warning(f"Could not find folder with ID {folder_id}")
            return
            
        current_name = folder_item.text()
        
        # Prompt for new name
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Rename Folder", "Enter new folder name:", text=current_name
        )
        
        if not ok or not new_name.strip() or new_name == current_name:
            logger.debug("Folder rename canceled or no change")
            return
            
        # Rename the folder
        def on_folder_renamed(success, result):
            if success:
                logger.info(f"Successfully renamed folder to {new_name}")
                # Trigger a refresh
                self.handle_data_changed("folder", folder_id)
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Failed to rename folder: {result}")
                logger.error(f"Failed to rename folder: {result}")
                
        self.folder_manager.rename_folder(folder_id, new_name, on_folder_renamed)
        
    def delete_folder(self, folder_id):
        """Delete a folder."""
        logger.info(f"Deleting folder with ID {folder_id}")
        
        # Get folder name
        folder_item = self.source_model.get_item_by_id(folder_id, "folder")
        if not folder_item:
            logger.warning(f"Could not find folder with ID {folder_id}")
            return
            
        folder_name = folder_item.text()
        
        # Confirm deletion
        from PyQt6.QtWidgets import QMessageBox
        response = QMessageBox.question(
            self, "Delete Folder",
            f"Are you sure you want to delete '{folder_name}'?\n\n"
            "This will remove all recording associations with this folder, but will not delete the recordings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if response != QMessageBox.StandardButton.Yes:
            logger.debug("Folder deletion canceled")
            return
            
        # Delete the folder
        def on_folder_deleted(success, result):
            if success:
                logger.info(f"Successfully deleted folder {folder_name}")
                # Trigger a refresh
                self.handle_data_changed("folder", -1)  # -1 means refresh everything
            else:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"Failed to delete folder: {result}")
                logger.error(f"Failed to delete folder: {result}")
                
        self.folder_manager.delete_folder(folder_id, on_folder_deleted)
        
    def _add_recording_item(self, parent_item, recording_data):
        """Add a recording item to the parent folder item (compatibility method)."""
        logger.info(f"Adding recording {recording_data[1]} to model")
        
        rec_id = recording_data[0]
        # Skip if already added - check both maps and set for comprehensive deduplication
        key = ("recording", rec_id)
        if key in self.source_model.item_map or rec_id in self.recordings_map or rec_id in self.seen_recording_ids:
            logger.debug(f"Skipping duplicate recording ID {rec_id}, already tracked in one of the maps")
            return
            
        # Mark as seen for deduplication
        self.seen_recording_ids.add(rec_id)
            
        # Create RecordingListItem for compatibility
        recording_item = RecordingListItem(
            rec_id, recording_data[1], recording_data[2], recording_data[3], 
            recording_data[4], # duration
            recording_data[5], # raw_transcript
            recording_data[6], # processed_text
            None, # raw_transcript_formatted (not provided in this case)
            None, # processed_text_formatted (not provided in this case)
            parent=self
        )
        # Store db_manager as a property
        recording_item.db_manager = self.db_manager
        self.recordings_map[rec_id] = recording_item
        
        # Add to the model
        self.source_model.add_recording_item(recording_data, parent_item)
        logger.info(f"Added recording ID {rec_id} to model")