"""
Manual test script for testing tree view refresh spam resistance

This script creates a simple UI that allows the user to:
1. Rapidly click a button to trigger multiple tree refreshes
2. Monitor widget count and memory usage
3. Verify no duplicates appear in the view

Usage:
    python -m app.tests.test_tree_refresh_spam
"""

import sys
import os
import gc
import psutil
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, 
    QHBoxLayout, QLabel, QWidget, QTreeView, QScrollArea
)
from PyQt6.QtCore import QTimer, Qt

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.UnifiedFolderTreeView import UnifiedFolderTreeView
from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager

class RefreshSpamTester(QMainWindow):
    """Test window for refresh spam testing"""
    
    def __init__(self):
        super().__init__()
        
        # Get actual DB and folder manager instances
        self.db_manager = DatabaseManager()
        self.folder_manager = FolderManager.instance()
        
        # Create tree view
        self.tree_view = UnifiedFolderTreeView(self.db_manager)
        
        # Setup UI
        self.init_ui()
        
        # Setup monitoring
        self.process = psutil.Process(os.getpid())
        self.refresh_count = 0
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        
        # Start memory monitoring
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_stats)
        self.monitor_timer.start(1000)  # Update every second
        
    def init_ui(self):
        """Initialize the UI components"""
        self.setWindowTitle("Tree View Refresh Spam Tester")
        self.setGeometry(100, 100, 800, 600)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create layouts
        main_layout = QVBoxLayout(central_widget)
        button_layout = QHBoxLayout()
        stats_layout = QHBoxLayout()
        
        # Create refresh button
        self.refresh_button = QPushButton("Refresh Tree")
        self.refresh_button.clicked.connect(self.trigger_refresh)
        self.spam_button = QPushButton("Spam 20 Refreshes")
        self.spam_button.clicked.connect(self.spam_refreshes)
        self.gc_button = QPushButton("Force GC")
        self.gc_button.clicked.connect(self.force_gc)
        
        # Create stats labels
        self.refresh_label = QLabel("Refreshes: 0")
        self.widget_label = QLabel("Widgets: 0")
        self.memory_label = QLabel("Memory: 0 MB")
        self.recording_count_label = QLabel("Recordings: 0")
        
        # Add buttons to layout
        button_layout.addWidget(self.refresh_button)
        button_layout.addWidget(self.spam_button)
        button_layout.addWidget(self.gc_button)
        button_layout.addStretch(1)
        
        # Add stats to layout
        stats_layout.addWidget(self.refresh_label)
        stats_layout.addWidget(self.widget_label)
        stats_layout.addWidget(self.recording_count_label)
        stats_layout.addWidget(self.memory_label)
        stats_layout.addStretch(1)
        
        # Wrap tree view in scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.tree_view)
        
        # Add everything to main layout
        main_layout.addLayout(button_layout)
        main_layout.addLayout(stats_layout)
        main_layout.addWidget(scroll_area)
        
        # Set initial stats
        self.update_stats()
        
    def trigger_refresh(self):
        """Trigger a single tree refresh"""
        self.refresh_count += 1
        self.refresh_label.setText(f"Refreshes: {self.refresh_count}")
        self.tree_view.load_structure()
        
    def spam_refreshes(self):
        """Trigger 20 rapid refreshes"""
        self.spam_button.setEnabled(False)
        self.spam_count = 0
        
        def do_single_refresh():
            if self.spam_count < 20:
                self.refresh_count += 1
                self.spam_count += 1
                self.refresh_label.setText(f"Refreshes: {self.refresh_count}")
                self.tree_view.load_structure()
                # Schedule next refresh with minimal delay
                QTimer.singleShot(50, do_single_refresh)
            else:
                self.spam_button.setEnabled(True)
                
        # Start the spam sequence
        do_single_refresh()
        
    def force_gc(self):
        """Force garbage collection"""
        gc.collect()
        self.update_stats()
        
    def update_stats(self):
        """Update the statistics display"""
        # Count tree view widgets
        widget_count = len(self.tree_view.id_to_widget)
        self.widget_label.setText(f"Widgets: {widget_count}")
        
        # Count model items
        recording_count = sum(1 for key in self.tree_view.source_model.item_map if key[0] == "recording")
        self.recording_count_label.setText(f"Recordings: {recording_count}")
        
        # Memory usage
        current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        memory_diff = current_memory - self.start_memory
        self.memory_label.setText(f"Memory: {current_memory:.1f} MB ({memory_diff:+.1f} MB)")
        
        # Set color based on whether widget count matches recording count
        if widget_count == recording_count:
            self.widget_label.setStyleSheet("color: green;")
            self.recording_count_label.setStyleSheet("color: green;")
        else:
            self.widget_label.setStyleSheet("color: red;")
            self.recording_count_label.setStyleSheet("color: red;")

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Use consistent style
    window = RefreshSpamTester()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()