"""
Example demonstrating QSortFilterProxyModel usage for filtering and searching.

This example shows:
1. How to create a data model (QStandardItemModel)
2. How to set up a filter proxy model (QSortFilterProxyModel)
3. How to implement custom filtering logic
4. How to apply filters to a hierarchical tree structure
"""

import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTreeView, QVBoxLayout, QWidget,
    QLineEdit, QComboBox, QHBoxLayout, QLabel
)
from PyQt6.QtCore import Qt, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QIcon

class RecordingFilterModel(QSortFilterProxyModel):
    """Filter proxy model with custom filtering logic."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_text = ""
        self.filter_criteria = "All"
        
    def setFilterText(self, text):
        """Set text to filter by."""
        self.filter_text = text.lower()
        self.invalidateFilter()
        
    def setFilterCriteria(self, criteria):
        """Set criteria to filter by."""
        self.filter_criteria = criteria
        self.invalidateFilter()
        
    def filterAcceptsRow(self, source_row, source_parent):
        """Custom filter implementation for tree items."""
        # Get the source index and item
        source_index = self.sourceModel().index(source_row, 0, source_parent)
        item = self.sourceModel().itemFromIndex(source_index)
        
        # Get item type (folder or recording)
        item_type = item.data(Qt.ItemDataRole.UserRole + 1)
        
        # Always show root folder
        if item_type == "folder" and item.data(Qt.ItemDataRole.UserRole + 2) == -1:
            return True
            
        # Handle folders
        if item_type == "folder":
            # Check if folder name matches filter text
            folder_name = item.text().lower()
            if self.filter_text and self.filter_text in folder_name:
                return True
                
            # Check if any child matches the filter
            for row in range(self.sourceModel().rowCount(source_index)):
                if self.filterAcceptsRow(row, source_index):
                    return True
                    
            # If nothing matches, hide the folder
            return False
            
        # Handle recordings
        elif item_type == "recording":
            # Check text match
            if self.filter_text:
                # Get full text for searching
                full_text = item.data(Qt.ItemDataRole.UserRole + 3)
                if not self.filter_text in full_text.lower():
                    return False
                    
            # Check criteria match
            if self.filter_criteria != "All":
                if self.filter_criteria == "Has Transcript":
                    has_transcript = item.data(Qt.ItemDataRole.UserRole + 4)
                    if not has_transcript:
                        return False
                elif self.filter_criteria == "No Transcript":
                    has_transcript = item.data(Qt.ItemDataRole.UserRole + 4)
                    if has_transcript:
                        return False
                    
            # If we got here, the recording matches all filters
            return True
            
        # Default case - show the item
        return True


class FilterProxyModelExample(QMainWindow):
    """Main window for the example."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QSortFilterProxyModel Example")
        self.setGeometry(100, 100, 800, 600)
        
        # Central widget and layout
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        
        # Create the filter controls
        filter_layout = QHBoxLayout()
        
        # Text filter
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Search...")
        self.search_field.textChanged.connect(self.apply_filter)
        
        # Criteria filter
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Has Transcript", "No Transcript"])
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        
        filter_layout.addWidget(QLabel("Search:"))
        filter_layout.addWidget(self.search_field, 3)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.filter_combo, 1)
        layout.addLayout(filter_layout)
        
        # Create tree view
        self.tree_view = QTreeView()
        self.tree_view.setHeaderHidden(True)
        layout.addWidget(self.tree_view)
        
        self.setCentralWidget(central_widget)
        
        # Create source model and populate it
        self.create_model()
        
        # Create filter proxy model
        self.proxy_model = RecordingFilterModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        
        # Set proxy model to tree view
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.expandAll()
        
    def create_model(self):
        """Create and populate the model with sample data."""
        self.source_model = QStandardItemModel()
        
        # Root folder
        root = QStandardItem("Recordings")
        root.setData("folder", Qt.ItemDataRole.UserRole + 1)  # Type
        root.setData(-1, Qt.ItemDataRole.UserRole + 2)  # ID
        self.source_model.appendRow(root)
        
        # Sample folders
        folders = [
            ("Interviews", 1),
            ("Meetings", 2),
            ("Lectures", 3)
        ]
        
        for folder_name, folder_id in folders:
            folder = QStandardItem(folder_name)
            folder.setData("folder", Qt.ItemDataRole.UserRole + 1)  # Type
            folder.setData(folder_id, Qt.ItemDataRole.UserRole + 2)  # ID
            root.appendRow(folder)
            
            # Add sample recordings to each folder
            self.add_sample_recordings(folder, folder_name.lower())
            
        # Also add recordings to root
        self.add_sample_recordings(root, "misc")
        
    def add_sample_recordings(self, parent, prefix):
        """Add sample recordings to the specified parent item."""
        recordings = [
            (f"{prefix}_recording1.mp3", True, "This is a sample transcript for recording 1."),
            (f"{prefix}_recording2.mp3", False, ""),
            (f"{prefix}_recording3.mp3", True, "Sample transcript for the third recording with more content."),
            (f"{prefix}_recording4.mp3", False, ""),
            (f"{prefix}_recording5.mp3", True, "This is a longer transcript with multiple sentences. It contains more information for searching.")
        ]
        
        for i, (name, has_transcript, transcript) in enumerate(recordings):
            rec = QStandardItem(name)
            rec.setData("recording", Qt.ItemDataRole.UserRole + 1)  # Type
            rec.setData(i, Qt.ItemDataRole.UserRole + 2)  # ID
            
            # Store full text for searching (name + transcript)
            full_text = f"{name} {transcript}"
            rec.setData(full_text, Qt.ItemDataRole.UserRole + 3)
            
            # Store transcript status
            rec.setData(has_transcript, Qt.ItemDataRole.UserRole + 4)
            
            parent.appendRow(rec)
    
    def apply_filter(self):
        """Apply filters to the tree view."""
        search_text = self.search_field.text()
        filter_criteria = self.filter_combo.currentText()
        
        self.proxy_model.setFilterText(search_text)
        self.proxy_model.setFilterCriteria(filter_criteria)
        
        # Expand all when filtering
        if search_text or filter_criteria != "All":
            self.tree_view.expandAll()
        

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FilterProxyModelExample()
    window.show()
    sys.exit(app.exec())