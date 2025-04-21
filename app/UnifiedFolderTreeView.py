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
        
        # Connect to the dataChanged signal for unified refresh
        self.db_manager.dataChanged.connect(self.handle_data_changed)
        
        # Create models
        self.source_model = RecordingFolderModel(self)
        self.proxy_model = RecordingFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        
        # Initialize UI
        self.init_ui()
        
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
        logger.debug("Starting tree structure refresh with model/view approach")
        self._is_loading = True  # Flag to prevent signals during load
        self._load_token += 1  # Increment token to invalidate any pending callbacks
        current_token = self._load_token  # Store current token for callbacks
        
        # Clear existing data
        self.source_model.clear_model()
        self.recordings_map.clear()
        
        # Initialize expanded_folders if not provided
        if expanded_folder_ids is None:
            expanded_folder_ids = [-1]  # Always expand root by default
        
        # Add root item for unorganized recordings
        root_folder = {"type": "folder", "id": -1, "name": "Unorganized Recordings", "children": []}
        root_item = self.source_model.add_folder_item(root_folder)
        
        # Load root folders
        root_folders = self.folder_manager.get_all_root_folders()
        for folder in sorted(root_folders, key=lambda f: f['name'].lower()):
            folder_item = self.source_model.add_folder_item(folder, root_item)
            
            # Set folder expansion state
            folder_index = self.proxy_model.mapFromSource(folder_item.index())
            self.setExpanded(folder_index, folder['id'] in expanded_folder_ids)
            
            # Recursively add child folders
            self._load_nested_folders(folder_item, folder, expanded_folder_ids)
            
            # Load recordings for this folder
            self._load_recordings_for_folder(folder['id'], folder_item, current_token)
        
        # Load unorganized recordings
        self._load_recordings_for_folder(-1, root_item, current_token)
        
        # Expand root initially
        root_index = self.proxy_model.mapFromSource(root_item.index())
        self.setExpanded(root_index, True)
        
        # Restore selection if provided
        if select_item_id is not None and item_type is not None:
            item = self.source_model.get_item_by_id(select_item_id, item_type)
            if item:
                index = self.proxy_model.mapFromSource(item.index())
                self.setCurrentIndex(index)
                self.scrollTo(index)
                
                # Ensure parents are expanded
                parent_index = index.parent()
                while parent_index.isValid():
                    self.setExpanded(parent_index, True)
                    parent_index = parent_index.parent()
        
        self._is_loading = False
        logger.info(f"Tree structure loaded with model/view approach")
        
    def _load_nested_folders(self, parent_item, parent_folder, expanded_folder_ids):
        """Recursively load nested folders."""
        for child_folder in sorted(parent_folder['children'], key=lambda f: f['name'].lower()):
            child_item = self.source_model.add_folder_item(child_folder, parent_item)
            
            # Set expansion state
            child_index = self.proxy_model.mapFromSource(child_item.index())
            self.setExpanded(child_index, child_folder['id'] in expanded_folder_ids)
            
            # Load recordings for this folder
            self._load_recordings_for_folder(child_folder['id'], child_item, self._load_token)
            
            # Recursively process children
            self._load_nested_folders(child_item, child_folder, expanded_folder_ids)
            
    def _load_recordings_for_folder(self, folder_id, folder_item, current_token):
        """Load recordings for a specific folder."""
        # Load recordings from database
        if folder_id == -1:
            # Unorganized recordings (not in any folder)
            recordings = self.db_manager.get_unassigned_recordings()
        else:
            # Regular folder
            recordings = self.db_manager.get_recordings_for_folder(folder_id)
            
        # Skip if loading was cancelled or superseded
        if current_token != self._load_token:
            logger.debug(f"Skipping stale loading operation (token {current_token} vs current {self._load_token})")
            return
            
        # Sort recordings by date (newest first)
        try:
            sorted_recs = sorted(recordings, key=lambda r: datetime.datetime.strptime(r[3], "%Y-%m-%d %H:%M:%S"), reverse=True)
        except Exception as e:
            logger.warning(f"Could not sort recordings for folder {folder_id}: {e}")
            sorted_recs = recordings
            
        # Add recordings to the model
        for rec in sorted_recs:
            rec_id = rec[0]
            # Skip if already added
            if rec_id in self.recordings_map:
                continue
                
            # Create RecordingListItem for compatibility
            recording_item = RecordingListItem(
                rec_id, rec[1], rec[2], rec[3], 
                self.db_manager, self
            )
            recording_item.set_transcript_status(rec[4] is not None and rec[4].strip() != "")
            self.recordings_map[rec_id] = recording_item
            
            # Add to the model
            self.source_model.add_recording_item(rec, folder_item)
            
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
            return ProxyTreeItem(self, self.proxy_model.mapFromSource(item.index()))
        return None
        
    def currentItem(self):
        """Get the current item (compatibility with QTreeWidget)."""
        index = self.currentIndex()
        if not index.isValid():
            return None
        return ProxyTreeItem(self, index)
        
    def get_folder_recording_count(self, folder_id, callback=None):
        """Get the number of recordings in a folder."""
        # This will be a stub implementation for now
        # In the future, we could implement a proper count based on the model
        return 0
        
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
                
    def handle_data_changed(self, entity_type, entity_id):
        """Handle data change notifications."""
        if self._is_loading:
            return
            
        logger.debug(f"Handle data changed: {entity_type} {entity_id}")
        
        # Store expanded folders
        expanded_folder_ids = self.get_expanded_folder_ids()
        
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
                
        # Reload structure
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
        # Implementation for context menu functionality
        pass