import os
import datetime
import logging
from PyQt6.QtCore import pyqtSignal, Qt, QModelIndex, QTimer, QSize
from PyQt6.QtWidgets import (
    QTreeView,
    QAbstractItemView,
    QMenu,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)
from PyQt6.QtGui import QIcon
from app.RecordingFolderModel import RecordingFolderModel, RecordingFilterProxyModel
from app.RecordingListItem import RecordingListItem
from app.FolderManager import FolderManager
from app.path_utils import resource_path

logger = logging.getLogger("transcribrr")


class RecordingItemDelegate(QStyledItemDelegate):
    """Custom delegate for rendering recording items in the tree."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def sizeHint(self, option, index):
        """Return the size hint for the item."""
        # Get the model item
        item_type = index.data(RecordingFolderModel.ITEM_TYPE_ROLE)

        # If it's a recording, use the RecordingListItem's size hint
        if item_type == "recording":
            return QSize(
                option.rect.width(), 70
            )  # Match the height in RecordingListItem

        # Otherwise use the default size hint
        return super().sizeHint(option, index)

    def paint(self, painter, option, index):
        """Paint the item."""
        # Use default rendering for folders
        item_type = index.data(RecordingFolderModel.ITEM_TYPE_ROLE)
        if item_type != "recording":
            super().paint(painter, option, index)
            return

        # For recordings, we need to handle selection state but not paint text
        # In PyQt6, selection state is checked against QStyle.StateFlag.State_Selected
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        # Draw only the icon (text is handled by RecordingListItem)
        option_copy = QStyleOptionViewItem(option)
        option_copy.text = ""  # Clear text to avoid overlapping with widget
        super().paint(painter, option_copy, index)


class UnifiedFolderTreeView(QTreeView):
    """Combined folder and recording tree using Qt's Model/View framework."""

    # Signals
    folderSelected = pyqtSignal(int, str)
    recordingSelected = pyqtSignal(RecordingListItem)  # Keep for compatibility
    recordingNameChanged = pyqtSignal(int, str)  # Signal for rename request

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager

        # Get the properly initialized FolderManager instance with shared DatabaseManager
        try:
            # Pass the database manager to ensure proper initialization
            self.folder_manager = FolderManager.instance(db_manager=self.db_manager)
        except RuntimeError as e:
            # Log the error and handle the case when FolderManager is not yet initialized
            logger.error(f"FolderManager initialization error: {e}")
            # Since we've passed the db_manager, this should only happen if there's a more serious issue
            # Use a dummy reference until the manager is properly initialized by MainWindow
            self.folder_manager = None

        self.current_folder_id = -1
        self._load_token = 0  # Monotonically increasing token to track valid callbacks
        self._is_loading = False  # Flag to prevent signals during load
        self._pending_refresh = False  # Flag to track queued refreshes
        self._pending_refresh_params = (
            None  # Store the parameters for the pending refresh
        )
        self.id_to_widget = (
            {}
        )  # Maps recording ID to widget AFTER widget is attached to view

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
        # Allow multi-select
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        # Ensure rows can have different heights for custom widgets
        self.setUniformRowHeights(False)

        # Set custom item delegate to handle recording items
        self.item_delegate = RecordingItemDelegate(self)
        self.setItemDelegate(self.item_delegate)

        # Connect signals
        self.clicked.connect(self.on_item_clicked)
        self.doubleClicked.connect(self.on_item_double_clicked)
        self.expanded.connect(self.on_item_expanded)
        self.collapsed.connect(self.on_item_collapsed)

        # Load icons
        folder_icon_path = resource_path("icons/folder.svg")
        folder_open_icon_path = resource_path("icons/folder_open.svg")

        self.folder_icon = (
            QIcon(folder_icon_path)
            if os.path.exists(folder_icon_path)
            else QIcon.fromTheme("folder")
        )
        self.folder_open_icon = (
            QIcon(folder_open_icon_path)
            if os.path.exists(folder_open_icon_path)
            else QIcon.fromTheme("folder-open")
        )
        self.audio_icon = QIcon(resource_path("icons/status/audio.svg"))
        self.video_icon = QIcon(resource_path("icons/status/video.svg"))
        self.file_icon = QIcon(resource_path("icons/status/file.svg"))

        # Set icons in model
        self.source_model.set_icons(
            self.folder_icon,
            self.folder_open_icon,
            self.audio_icon,
            self.video_icon,
            self.file_icon,
        )

        # Initial data load
        self.load_structure()

    def load_structure(
        self, select_item_id=None, item_type=None, expanded_folder_ids=None
    ):
        """Load tree structure and recordings."""
        logger.info("Starting tree structure refresh with model/view approach")
        self._is_loading = True  # Flag to prevent signals during load
        self._load_token += 1  # Increment token to invalidate any pending callbacks
        current_token = self._load_token  # Store current token for callbacks
        logger.debug(f"Using load token: {current_token}")

        # Clean up existing widgets to prevent memory leaks
        self._cleanup_widgets()

        # Clear existing data
        self.source_model.clear_model()
        logger.debug(f"Cleared source model, entries before: {len(self.id_to_widget)}")
        self.id_to_widget.clear()
        logger.debug("Cleared id_to_widget mapping")

        # Initialize expanded_folders if not provided
        if expanded_folder_ids is None:
            expanded_folder_ids = [-1]  # Always expand root by default
            logger.debug("No expanded folder IDs provided, using default [-1]")
        else:
            logger.debug(f"Using provided expanded folder IDs: {expanded_folder_ids}")

        # Add root item for unorganized recordings
        root_folder = {
            "type": "folder",
            "id": -1,
            "name": "Unorganized Recordings",
            "children": [],
        }
        root_item = self.source_model.add_folder_item(root_folder)
        logger.info("Added root folder item for unorganized recordings")

        # Load root folders
        root_folders = self.folder_manager.get_all_root_folders()
        logger.info(f"Found {len(root_folders)} root folders")

        for folder in sorted(root_folders, key=lambda f: f["name"].lower()):
            logger.debug(
                f"Processing root folder: {folder['name']} (ID: {folder['id']})"
            )
            folder_item = self.source_model.add_folder_item(folder, root_item)

            # Set folder expansion state
            folder_index = self.proxy_model.mapFromSource(folder_item.index())
            is_expanded = folder["id"] in expanded_folder_ids
            self.setExpanded(folder_index, is_expanded)
            logger.debug(
                f"Set expansion state for folder {folder['name']}: {is_expanded}"
            )

            # Recursively add child folders
            self._load_nested_folders(folder_item, folder, expanded_folder_ids)

            # Load recordings for this folder
            logger.debug(f"Requesting recordings for folder ID {folder['id']}")
            self._load_recordings_for_folder(folder["id"], folder_item, current_token)

        # Load unorganized recordings
        logger.info("Requesting unorganized recordings")
        self._load_recordings_for_folder(-1, root_item, current_token)

        # Expand root initially
        root_index = self.proxy_model.mapFromSource(root_item.index())
        self.setExpanded(root_index, True)
        logger.debug("Expanded root folder")

        # Restore selection if provided
        if select_item_id is not None and item_type is not None:
            logger.debug(
                f"Attempting to restore selection: {item_type} with ID {select_item_id}"
            )
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
                logger.warning(
                    f"Could not find item to restore selection: {item_type} with ID {select_item_id}"
                )

        # Check model content after loading
        logger.info(
            f"Tree structure loaded with {self.source_model.rowCount()} top-level items"
        )
        logger.info(f"Widget map contains {len(self.id_to_widget)} recording widgets")

        # Reset the loading flag
        self._is_loading = False
        logger.info("Tree structure loading completed")

        # Process any pending refreshes that came in during loading
        if self._pending_refresh:
            logger.info("Processing pending refresh after load completed")
            # Use a small delay to ensure the UI is responsive after loading
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(50, lambda: self._process_pending_refresh())

    def _cleanup_widgets(self):
        """Clean up widget references to prevent memory leaks."""
        logger.debug(f"Cleaning up {len(self.id_to_widget)} recording widgets")
        # Remove all indexed widgets from the view
        for rec_id, widget in self.id_to_widget.items():
            try:
                # Get the model item for this recording
                item = self.source_model.get_item_by_id(rec_id, "recording")
                if item:
                    # Get the index and remove the widget
                    source_index = item.index()
                    proxy_index = self.proxy_model.mapFromSource(source_index)
                    self.setIndexWidget(proxy_index, None)

                # Delete the widget to free memory
                if widget and hasattr(widget, "deleteLater"):
                    widget.deleteLater()
            except Exception as e:
                logger.warning(f"Error cleaning up widget for recording {rec_id}: {e}")

        # Clear the map
        self.id_to_widget.clear()

    def _load_nested_folders(self, parent_item, parent_folder, expanded_folder_ids):
        """Recursively load nested folders."""
        if not parent_folder.get("children"):
            logger.debug(
                f"No children for folder {parent_folder.get('name')} (ID: {parent_folder.get('id')})"
            )
            return

        logger.debug(
            f"Loading {len(parent_folder['children'])} nested folders for parent {parent_folder.get('name')} (ID: {parent_folder.get('id')})"
        )

        for child_folder in sorted(
            parent_folder["children"], key=lambda f: f["name"].lower()
        ):
            logger.debug(
                f"Processing child folder: {child_folder['name']} (ID: {child_folder['id']})"
            )
            child_item = self.source_model.add_folder_item(child_folder, parent_item)

            # Set expansion state
            child_index = self.proxy_model.mapFromSource(child_item.index())
            is_expanded = (
                child_folder["id"] in expanded_folder_ids
                if expanded_folder_ids
                else False
            )
            self.setExpanded(child_index, is_expanded)
            logger.debug(
                f"Set expansion state for folder {child_folder['name']}: {is_expanded}"
            )

            # Load recordings for this folder
            current_token = self._load_token  # Get current token for consistency
            logger.debug(f"Requesting recordings for folder ID {child_folder['id']}")
            self._load_recordings_for_folder(
                child_folder["id"], child_item, current_token
            )

            # Recursively process children
            self._load_nested_folders(child_item, child_folder, expanded_folder_ids)

    def _load_recordings_for_folder(self, folder_id, folder_item, current_token):
        """Load recordings for a specific folder."""
        logger.debug(
            f"Loading recordings for folder ID {folder_id} with token {current_token}"
        )

        # Load recordings from database
        if folder_id == -1:
            # Unorganized recordings (not in any folder)
            def _add_unassigned_recordings(success, recordings):
                # Helper to disconnect this callback when done or if stale
                def _disconnect_callback():
                    try:
                        # Find reference to this operation in the FolderManager's callback
                        self.folder_manager.operation_complete.disconnect(
                            _add_unassigned_recordings
                        )
                        logger.debug("Disconnected unassigned recordings callback")
                    except (TypeError, RuntimeError, AttributeError) as e:
                        # Ignore errors if already disconnected
                        logger.debug(f"Could not disconnect callback: {e}")

                logger.info(
                    f"Callback for unassigned recordings, success={success}, received {len(recordings) if recordings else 0} recordings"
                )

                if not success:
                    logger.error("Failed to load unassigned recordings")
                    _disconnect_callback()
                    return

                # Check if this callback is stale (and disconnect if it is)
                if current_token != self._load_token:
                    logger.warning(
                        f"Skipping stale callback (token {current_token} vs current {self._load_token})"
                    )
                    _disconnect_callback()
                    return

                if not recordings:
                    logger.info("No unassigned recordings found")
                    _disconnect_callback()
                    return

                logger.info(f"Processing {len(recordings)} unassigned recordings")

                # Sort recordings by date (newest first)
                try:
                    sorted_recs = sorted(
                        recordings,
                        key=lambda r: datetime.datetime.strptime(
                            r[3], "%Y-%m-%d %H:%M:%S"
                        ),
                        reverse=True,
                    )
                except Exception as e:
                    logger.warning(f"Could not sort unassigned recordings: {e}")
                    sorted_recs = recordings

                # Add recordings to the model
                added_count = 0
                skipped_count = 0
                for rec in sorted_recs:
                    rec_id = rec[0]
                    # Check if already exists in the model (single source of truth)
                    if self.source_model.get_item_by_id(rec_id, "recording"):
                        logger.debug(
                            f"Skipping recording ID {rec_id}, already exists in model"
                        )
                        skipped_count += 1
                        continue

                    # First add to the model
                    recording_model_item = self.source_model.add_recording_item(
                        rec, folder_item
                    )

                    # Create the index for the model item
                    source_index = recording_model_item.index()
                    proxy_index = self.proxy_model.mapFromSource(source_index)

                    # Create RecordingListItem for the UI
                    recording_item = RecordingListItem(
                        rec_id,
                        rec[1],
                        rec[2],
                        rec[3],
                        rec[4],  # duration
                        rec[5],  # raw_transcript
                        rec[6],  # processed_text
                        rec[7],  # raw_transcript_formatted
                        rec[8],  # processed_text_formatted
                        parent=self,
                    )
                    # Store db_manager as a property
                    recording_item.db_manager = self.db_manager

                    # Set the RecordingListItem widget for this index
                    self.setIndexWidget(proxy_index, recording_item)

                    # Only add to widget map AFTER successful attachment
                    self.id_to_widget[rec_id] = recording_item

                    added_count += 1
                    logger.debug(f"Added unassigned recording ID {rec_id}: {rec[1]}")

                # Force layout update to accommodate widgets
                # Schedule a delayed update to allow geometries to settle
                QTimer.singleShot(0, self.updateGeometries)
                QTimer.singleShot(0, self.viewport().update)

                logger.info(
                    f"Added {added_count} unassigned recordings, skipped {skipped_count}"
                )
                _disconnect_callback()

            # Use folder manager to get unassigned recordings
            logger.info("Requesting unassigned recordings from folder manager")
            self.folder_manager.get_recordings_not_in_folders(
                _add_unassigned_recordings
            )
        else:
            # Regular folder
            def _add_folder_recordings(success, recordings):
                # Helper to disconnect this callback when done or if stale
                def _disconnect_callback():
                    try:
                        # Find reference to this operation in the FolderManager's callback
                        self.folder_manager.operation_complete.disconnect(
                            _add_folder_recordings
                        )
                        logger.debug(f"Disconnected callback for folder {folder_id}")
                    except (TypeError, RuntimeError, AttributeError) as e:
                        # Ignore errors if already disconnected
                        logger.debug(f"Could not disconnect callback: {e}")

                logger.info(
                    f"Callback for folder {folder_id}, success={success}, received {len(recordings) if recordings else 0} recordings"
                )

                if not success:
                    logger.error(f"Failed to load recordings for folder {folder_id}")
                    _disconnect_callback()
                    return

                # Check if this callback is stale (and disconnect if it is)
                if current_token != self._load_token:
                    logger.warning(
                        f"Skipping stale callback for folder {folder_id} (token {current_token} vs current {self._load_token})"
                    )
                    _disconnect_callback()
                    return

                if not recordings:
                    logger.info(f"No recordings found in folder {folder_id}")
                    _disconnect_callback()
                    return

                logger.info(
                    f"Processing {len(recordings)} recordings for folder {folder_id}"
                )

                # Sort recordings by date (newest first)
                try:
                    sorted_recs = sorted(
                        recordings,
                        key=lambda r: datetime.datetime.strptime(
                            r[3], "%Y-%m-%d %H:%M:%S"
                        ),
                        reverse=True,
                    )
                except Exception as e:
                    logger.warning(
                        f"Could not sort recordings for folder {folder_id}: {e}"
                    )
                    sorted_recs = recordings

                # Add recordings to the model
                added_count = 0
                skipped_count = 0
                for rec in sorted_recs:
                    rec_id = rec[0]
                    # Check if already exists in the model (single source of truth)
                    if self.source_model.get_item_by_id(rec_id, "recording"):
                        logger.debug(
                            f"Skipping recording ID {rec_id} in folder {folder_id}, already exists in model"
                        )
                        skipped_count += 1
                        continue

                    # First add to the model
                    recording_model_item = self.source_model.add_recording_item(
                        rec, folder_item
                    )

                    # Create the index for the model item
                    source_index = recording_model_item.index()
                    proxy_index = self.proxy_model.mapFromSource(source_index)

                    # Create RecordingListItem for the UI
                    recording_item = RecordingListItem(
                        rec_id,
                        rec[1],
                        rec[2],
                        rec[3],
                        rec[4],  # duration
                        rec[5],  # raw_transcript
                        rec[6],  # processed_text
                        rec[7],  # raw_transcript_formatted
                        rec[8],  # processed_text_formatted
                        parent=self,
                    )
                    # Store db_manager as a property
                    recording_item.db_manager = self.db_manager

                    # Set the RecordingListItem widget for this index
                    self.setIndexWidget(proxy_index, recording_item)

                    # Only add to widget map AFTER successful attachment
                    self.id_to_widget[rec_id] = recording_item

                    added_count += 1
                    logger.debug(
                        f"Added recording ID {rec_id} to folder {folder_id}: {rec[1]}"
                    )

                # Force layout update to accommodate widgets
                # Schedule a delayed update to allow geometries to settle
                QTimer.singleShot(0, self.updateGeometries)
                QTimer.singleShot(0, self.viewport().update)

                logger.info(
                    f"Added {added_count} recordings to folder {folder_id}, skipped {skipped_count}"
                )
                _disconnect_callback()

            # Get recordings for this folder
            logger.info(
                f"Requesting recordings for folder {folder_id} from folder manager"
            )
            self.folder_manager.get_recordings_in_folder(
                folder_id, _add_folder_recordings
            )

    def set_filter(self, search_text, filter_criteria):
        """Apply filter to the tree view."""
        logger.info(
            f"Setting filter - Search: '{search_text}', Criteria: {filter_criteria}"
        )
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
        logger.info("Legacy apply_filter called, redirecting to set_filter")
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
            return self.ProxyTreeItem(
                self, self.proxy_model.mapFromSource(item.index())
            )
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
                    "name": item.text(),
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
            logger.warning(
                "Data change notification received while loading, queuing refresh..."
            )

            # Queue the refresh with a timer if one isn't already pending
            if not self._pending_refresh:
                self._pending_refresh = True
                self._pending_refresh_params = (entity_type, entity_id)

                # Schedule a delayed refresh
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(200, lambda: self._process_pending_refresh())
                logger.info(f"Queued refresh for {entity_type} {entity_id} in 200ms")
            else:
                logger.info(
                    f"Refresh already pending, will include changes for {entity_type} {entity_id}"
                )

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
        logger.info("Triggering structure reload due to data change")
        self.load_structure(current_id, current_type, expanded_folder_ids)

    def _process_pending_refresh(self):
        """Process a pending refresh that was queued during loading."""
        if self._pending_refresh:
            logger.info("Processing pending refresh")

            # Reset the flag first to avoid recursion issues
            self._pending_refresh = False

            # If we're still loading, queue another refresh
            if self._is_loading:
                logger.warning(
                    "Still loading when pending refresh triggered, re-queuing..."
                )
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(200, lambda: self._process_pending_refresh())
                self._pending_refresh = True
                return

            # Extract parameters from the last queued refresh
            entity_type, entity_id = self._pending_refresh_params
            self._pending_refresh_params = None

            # Now trigger the actual refresh
            logger.info(f"Executing queued refresh for {entity_type} {entity_id}")
            self.handle_data_changed(entity_type, entity_id)

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
            if item_id in self.id_to_widget:
                recording_item = self.id_to_widget[item_id]
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
            # Resize rows based on newly visible children
            self.resizeColumnToContents(0)
            self.updateGeometries()  # Might also be needed here

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
            new_subfolder_action.triggered.connect(
                lambda: self.create_subfolder(item_id)
            )

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
                logger.info(
                    f"Successfully created folder {folder_name} with ID {folder_id}"
                )
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
            self,
            "Delete Folder",
            f"Are you sure you want to delete '{folder_name}'?\n\n"
            "This will remove all recording associations with this folder, but will not delete the recordings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
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
        # Check the model (single source of truth) for existing item
        if self.source_model.get_item_by_id(rec_id, "recording"):
            logger.debug(
                f"Skipping duplicate recording ID {rec_id}, already exists in model"
            )
            return None

        # First add to the model
        recording_model_item = self.source_model.add_recording_item(
            recording_data, parent_item
        )

        # Create the index for the model item
        source_index = recording_model_item.index()
        proxy_index = self.proxy_model.mapFromSource(source_index)

        # Create RecordingListItem for the UI
        recording_item = RecordingListItem(
            rec_id,
            recording_data[1],
            recording_data[2],
            recording_data[3],
            recording_data[4],  # duration
            recording_data[5],  # raw_transcript
            recording_data[6],  # processed_text
            None,  # raw_transcript_formatted (not provided in this case)
            None,  # processed_text_formatted (not provided in this case)
            parent=self,
        )
        # Store db_manager as a property
        recording_item.db_manager = self.db_manager

        # Set the RecordingListItem widget for this index
        self.setIndexWidget(proxy_index, recording_item)

        # Add to widget map only after successful attachment
        self.id_to_widget[rec_id] = recording_item

        # Ensure the view adjusts row height for the new widget
        self.resizeColumnToContents(0)

        logger.info(f"Added recording ID {rec_id} to model")
        return recording_model_item

    # ------------------------------------------------------------------
    # Public helper: select_item_by_id
    # ------------------------------------------------------------------

    def select_item_by_id(self, item_id, item_type):
        """Find and select an item in the tree view by its ID and type.

        Parameters
        ----------
        item_id : int
            The database ID of the item to select.
        item_type : str
            Either "folder" or "recording".

        Returns
        -------
        bool
            True if the item was found and selected, False otherwise.
        """

        logger.debug(f"Attempting to select {item_type} with ID {item_id}")

        # Look up the underlying QStandardItem in the source model
        item = self.source_model.get_item_by_id(item_id, item_type)
        if item is None:
            logger.warning(f"Item not found in source model: {item_type} ID {item_id}")
            return False

        source_index = item.index()
        proxy_index = self.proxy_model.mapFromSource(source_index)

        if not proxy_index.isValid():
            logger.warning(
                f"Could not map source index to proxy index for {item_type} ID {item_id}"
            )
            return False

        # Expand ancestor nodes so that the index is visible
        parent = proxy_index.parent()
        while parent.isValid():
            self.setExpanded(parent, True)
            parent = parent.parent()

        # Perform selection
        self.setCurrentIndex(proxy_index)
        self.scrollTo(proxy_index, QAbstractItemView.ScrollHint.PositionAtCenter)

        logger.info(f"Successfully selected {item_type} ID {item_id}")
        return True
