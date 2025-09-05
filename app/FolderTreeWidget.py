from PyQt6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
    QMenu,
    QInputDialog,
    QMessageBox,
    QWidget,
    QVBoxLayout,
    QToolBar,
    QLabel,
    QSizePolicy,
    QHBoxLayout,
    QToolButton,
)
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon, QFont, QColor
import logging
from app.FolderManager import FolderManager
from app.path_utils import resource_path
from app.ui_utils.icon_utils import load_icon


logger = logging.getLogger("transcribrr")


class FolderTreeWidget(QWidget):
    """Tree view for folder navigation."""

    folderSelected = pyqtSignal(int, str)  # Folder ID, Folder Name
    folderCreated = pyqtSignal(int, str)
    folderRenamed = pyqtSignal(int, str)
    folderDeleted = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.init_ui()
        self.load_folders()

    def init_ui(self):
        """Initialize UI components and layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(8, 8, 8, 8)

        header_label = QLabel("Folders")
        header_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        header_layout.addWidget(header_label)

        self.refresh_button = QToolButton()
        self.refresh_button.setIcon(load_icon("icons/refresh.svg", size=24))
        self.refresh_button.setToolTip("Refresh Folders")
        self.refresh_button.setFixedSize(24, 24)
        self.refresh_button.clicked.connect(self.load_folders)
        header_layout.addWidget(self.refresh_button)

        self.add_folder_button = QToolButton()
        self.add_folder_button.setIcon(load_icon("icons/folder.svg", size=24))
        self.add_folder_button.setToolTip("Add New Folder")
        self.add_folder_button.setFixedSize(24, 24)
        self.add_folder_button.clicked.connect(self.create_folder)
        header_layout.addWidget(self.add_folder_button)

        main_layout.addLayout(header_layout)

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setIconSize(QSize(16, 16))
        self.folder_tree.setIndentation(20)
        self.folder_tree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(
            self.show_context_menu)
        self.folder_tree.itemClicked.connect(self.on_folder_selected)
        self.folder_tree.itemExpanded.connect(self.on_item_expanded)
        self.folder_tree.itemCollapsed.connect(self.on_item_collapsed)

        self.folder_tree.setStyleSheet(
            """
            QTreeWidget {
                background-color: transparent;
                border: none;
                padding: 5px;
            }
            QTreeWidget::item {
                padding: 5px;
                border-radius: 4px;
            }
            QTreeWidget::item:selected {
                background-color: #e0e0e0;
            }
            QTreeWidget::item:hover {
                background-color: #f0f0f0;
            }
        """
        )

        main_layout.addWidget(self.folder_tree)

        root_item = QTreeWidgetItem(self.folder_tree)
        root_item.setText(0, "Unorganized Recordings")
        root_item.setIcon(0, load_icon("icons/folder.svg", size=24))
        root_item.setData(
            0, Qt.ItemDataRole.UserRole, {
                "id": -1, "name": "Unorganized Recordings"}
        )
        root_item.setExpanded(True)
        self.folder_tree.setCurrentItem(root_item)

        self.folder_icon = load_icon("icons/folder.svg", size=24)
        self.folder_open_icon = load_icon("icons/folder_open.svg", size=24)

    def load_folders(self):
        """Load and rebuild the folder tree."""
        current_item = self.folder_tree.currentItem()
        current_folder_id = -1
        if current_item:
            folder_data = current_item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(folder_data, dict) and "id" in folder_data:
                current_folder_id = folder_data["id"]

        root_item = self.folder_tree.topLevelItem(0)
        if root_item:
            while root_item.childCount() > 0:
                root_item.removeChild(root_item.child(0))

        # Get FolderManager instance safely
        from app.FolderManager import FolderManager

        try:
            # Try to get instance, or initialize with db_manager if available
            if hasattr(self, "db_manager") and self.db_manager is not None:
                folder_manager = FolderManager.instance(
                    db_manager=self.db_manager)
            else:
                # Try to initialize with db_manager if available
                if hasattr(self, "db_manager") and self.db_manager is not None:
                    folder_manager = FolderManager.instance(
                        db_manager=self.db_manager)
                else:
                    folder_manager = FolderManager.instance()
            root_folders = folder_manager.get_all_root_folders()
        except RuntimeError as e:
            logger.error(f"Error accessing FolderManager: {e}")
            root_folders = []

        try:
            import sqlite3
            from app.constants import get_database_path

            db_path = get_database_path()
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM recordings
                WHERE NOT EXISTS (
                    SELECT 1 FROM recording_folders 
                    WHERE recording_id = recordings.id
                )
            """
            )
            unorganized_count = cursor.fetchone()[0]
            conn.close()

            if root_item:
                root_item.setText(
                    0, f"Unorganized Recordings ({unorganized_count})")
        except Exception as e:
            logger.error(f"Error getting unorganized recording count: {e}")
            unorganized_count = 0

        for folder in root_folders:
            self.add_folder_to_tree(folder, root_item)

        if root_item:
            root_item.setExpanded(True)

        if current_folder_id >= 0:
            self.select_folder_by_id(current_folder_id)
        else:
            if root_item:
                self.folder_tree.setCurrentItem(root_item)
                self.folderSelected.emit(-1, "Unorganized Recordings")

    def add_folder_to_tree(self, folder, parent_item):
        """Recursively add a folder and its children to the tree."""
        recording_count = self.get_folder_recording_count(folder["id"])

        item = QTreeWidgetItem(parent_item)
        if recording_count > 0:
            item.setText(0, f"{folder['name']} ({recording_count})")
            item.setForeground(0, QColor("#000000"))
        else:
            item.setText(0, folder["name"] + " (empty)")
            item.setForeground(0, QColor("#888888"))

        item.setIcon(0, self.folder_icon)
        item.setData(
            0,
            Qt.ItemDataRole.UserRole,
            {
                "id": folder["id"],
                "name": folder["name"],
                "recording_count": recording_count,
            },
        )

        for child in folder["children"]:
            self.add_folder_to_tree(child, item)

    def get_folder_recording_count(self, folder_id):
        """Return recording count in folder."""
        try:
            from app.FolderManager import FolderManager

            try:
                # Try to initialize with db_manager if available
                if hasattr(self, "db_manager") and self.db_manager is not None:
                    folder_manager = FolderManager.instance(
                        db_manager=self.db_manager)
                else:
                    folder_manager = FolderManager.instance()
                recordings = folder_manager.get_recordings_in_folder(folder_id)
                return len(recordings) if recordings else 0
            except RuntimeError as e:
                logger.error(f"Error accessing FolderManager: {e}")
                return 0
        except Exception as e:
            logger.error(
                f"Error getting recording count for folder {folder_id}: {e}")
            return 0

    def on_item_expanded(self, item):
        """Handle item expansion to update the folder icon."""
        # Skip for "All Recordings" item
        folder_data = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_data and folder_data.get("id") != -1:
            item.setIcon(0, self.folder_open_icon)

    def on_item_collapsed(self, item):
        """Handle item collapse to update the folder icon."""
        # Skip for "All Recordings" item
        folder_data = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_data and folder_data.get("id") != -1:
            item.setIcon(0, self.folder_icon)

    def select_folder_by_id(self, folder_id):
        """Find and select a folder by ID."""
        if folder_id == -1:
            # Select "Unorganized Recordings" root item
            root_item = self.folder_tree.topLevelItem(0)
            if root_item:
                self.folder_tree.setCurrentItem(root_item)
                return True

        # Search for the folder item
        for i in range(self.folder_tree.topLevelItemCount()):
            top_item = self.folder_tree.topLevelItem(i)
            item = self.find_folder_item(top_item, folder_id)
            if item:
                self.folder_tree.setCurrentItem(item)
                return True

        return False

    def find_folder_item(self, parent_item, folder_id):
        """Recursively search for a folder item by ID."""
        # Check parent item
        folder_data = parent_item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(folder_data, dict) and folder_data.get("id") == folder_id:
            return parent_item

        # Check children
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            result = self.find_folder_item(child, folder_id)
            if result:
                return result

        return None

    def on_folder_selected(self, item, column):
        """Handle folder selection."""
        folder_data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(folder_data, dict):
            folder_id = folder_data.get("id", -1)
            folder_name = folder_data.get("name", "Unknown")

            # When emitting the signal, use the plain folder name (without the count)
            # This ensures the header in RecentRecordingsWidget shows the clean name
            self.folderSelected.emit(folder_id, folder_name)

    def show_context_menu(self, position):
        """Show context menu for folder operations."""
        # Get the item at position
        item = self.folder_tree.itemAt(position)
        if not item:
            return

        folder_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(folder_data, dict):
            return

        folder_id = folder_data.get("id")
        is_all_recordings = folder_id == -1
        recording_count = folder_data.get("recording_count", 0)

        # Create context menu
        menu = QMenu()

        if not is_all_recordings:
            # Regular folder options
            rename_action = menu.addAction("Rename Folder")
            rename_action.triggered.connect(
                lambda: self.rename_folder(item, folder_id))

            delete_action = menu.addAction("Delete Folder")
            delete_action.triggered.connect(
                lambda: self.delete_folder(item, folder_id))

            # Show recording count in the menu
            menu.addSeparator()
            if recording_count == 0:
                empty_label = menu.addAction("Empty Folder")
                empty_label.setEnabled(False)
            else:
                count_label = menu.addAction(
                    f"Contains {recording_count} recording(s)")
                count_label.setEnabled(False)

        menu.addSeparator()

        # Common options for all folders
        add_subfolder_action = menu.addAction("Add Subfolder")
        add_subfolder_action.triggered.connect(
            lambda: self.create_subfolder(item, folder_id)
        )

        # Option to refresh folder count
        refresh_action = menu.addAction("Refresh")
        refresh_action.triggered.connect(self.load_folders)

        menu.exec(self.folder_tree.viewport().mapToGlobal(position))

    def create_folder(self):
        """Create a new folder at root level."""
        folder_name, ok = QInputDialog.getText(
            self, "Create Folder", "Enter folder name:", text="New Folder"
        )

        if ok and folder_name:
            # Get FolderManager instance safely
            from app.FolderManager import FolderManager

            try:
                # Try to initialize with db_manager if available
                if hasattr(self, "db_manager") and self.db_manager is not None:
                    folder_manager = FolderManager.instance(
                        db_manager=self.db_manager)
                else:
                    folder_manager = FolderManager.instance()
            except RuntimeError as e:
                logger.error(f"Error accessing FolderManager: {e}")
                QMessageBox.warning(
                    self,
                    "Error",
                    "Cannot create folder: Database manager not initialized",
                )
                return

            # Define callback for when folder creation completes
            def on_folder_created(success, result):
                if success:
                    folder_id = result
                    self.load_folders()
                    self.folderCreated.emit(folder_id, folder_name)
                else:
                    QMessageBox.warning(
                        self, "Error", f"Failed to create folder: {result}"
                    )

            folder_manager.create_folder(folder_name, None, on_folder_created)

    def create_subfolder(self, parent_item, parent_id):
        """Create a subfolder under the selected folder."""
        folder_name, ok = QInputDialog.getText(
            self, "Create Subfolder", "Enter subfolder name:", text="New Subfolder"
        )

        if ok and folder_name:
            # Get FolderManager instance safely
            from app.FolderManager import FolderManager

            try:
                # Try to initialize with db_manager if available
                if hasattr(self, "db_manager") and self.db_manager is not None:
                    folder_manager = FolderManager.instance(
                        db_manager=self.db_manager)
                else:
                    folder_manager = FolderManager.instance()
            except RuntimeError as e:
                logger.error(f"Error accessing FolderManager: {e}")
                QMessageBox.warning(
                    self,
                    "Error",
                    "Cannot create folder: Database manager not initialized",
                )
                return

            # Define callback for when folder creation completes
            def on_folder_created(success, result):
                if success:
                    folder_id = result
                    self.load_folders()
                    self.folderCreated.emit(folder_id, folder_name)
                else:
                    QMessageBox.warning(
                        self, "Error", f"Failed to create subfolder: {result}"
                    )

            folder_manager.create_folder(
                folder_name, parent_id, on_folder_created)

    def rename_folder(self, item, folder_id):
        """Rename a folder."""
        current_name = item.text(0)
        new_name, ok = QInputDialog.getText(
            self, "Rename Folder", "Enter new folder name:", text=current_name
        )

        if ok and new_name and new_name != current_name:
            # Get FolderManager instance safely
            from app.FolderManager import FolderManager

            try:
                # Try to initialize with db_manager if available
                if hasattr(self, "db_manager") and self.db_manager is not None:
                    folder_manager = FolderManager.instance(
                        db_manager=self.db_manager)
                else:
                    folder_manager = FolderManager.instance()
            except RuntimeError as e:
                logger.error(f"Error accessing FolderManager: {e}")
                QMessageBox.warning(
                    self,
                    "Error",
                    "Cannot rename folder: Database manager not initialized",
                )
                return

            # Define callback for when folder rename completes
            def on_folder_renamed(success, result):
                if success:
                    self.load_folders()
                    self.folderRenamed.emit(folder_id, new_name)
                else:
                    QMessageBox.warning(
                        self, "Error", f"Failed to rename folder: {result}"
                    )

            folder_manager.rename_folder(
                folder_id, new_name, on_folder_renamed)

    def delete_folder(self, item, folder_id):
        """Delete a folder."""
        folder_name = item.text(0)

        # Confirm deletion
        response = QMessageBox.question(
            self,
            "Delete Folder",
            f"Are you sure you want to delete the folder '{folder_name}'?\n\nThis will remove all recording associations with this folder.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if response == QMessageBox.StandardButton.Yes:
            # Get FolderManager instance safely
            from app.FolderManager import FolderManager

            try:
                # Try to initialize with db_manager if available
                if hasattr(self, "db_manager") and self.db_manager is not None:
                    folder_manager = FolderManager.instance(
                        db_manager=self.db_manager)
                else:
                    folder_manager = FolderManager.instance()
            except RuntimeError as e:
                logger.error(f"Error accessing FolderManager: {e}")
                QMessageBox.warning(
                    self,
                    "Error",
                    "Cannot delete folder: Database manager not initialized",
                )
                return

            # Define callback for when folder deletion completes
            def on_folder_deleted(success, result):
                if success:
                    # Select "Unorganized Recordings" after deletion
                    root_item = self.folder_tree.topLevelItem(0)
                    if root_item:
                        self.folder_tree.setCurrentItem(root_item)

                    self.load_folders()
                    self.folderDeleted.emit(folder_id)
                else:
                    QMessageBox.warning(
                        self, "Error", f"Failed to delete folder: {result}"
                    )

            folder_manager.delete_folder(folder_id, on_folder_deleted)
