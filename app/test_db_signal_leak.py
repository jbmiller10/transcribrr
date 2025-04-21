import unittest
import os
import sys
import time
import psutil
import sqlite3
from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer
from PyQt6.QtTest import QTest

from app.DatabaseManager import DatabaseManager

class TestDBSignalLeak(unittest.TestCase):
    """Test case for database signal memory leak."""
    
    def setUp(self):
        """Set up the test environment."""
        # Create a test application
        self.app = QCoreApplication([])
        # Create a test database
        self.test_db_file = "/tmp/test_db_signal_leak.db"
        
        # Set up a mock database path
        import app.constants
        app.constants.DATABASE_PATH = self.test_db_file
        
        # Initialize database
        conn = sqlite3.connect(self.test_db_file)
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS recordings (
            id INTEGER PRIMARY KEY,
            file_path TEXT NOT NULL,
            original_filename TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transcription_status TEXT DEFAULT 'pending',
            transcription TEXT,
            duration REAL,
            file_size INTEGER,
            file_type TEXT,
            processing_status TEXT DEFAULT 'pending'
        )
        ''')
        conn.commit()
        conn.close()
        
        # Create database manager
        self.db_manager = DatabaseManager()
        
        # Add a test recording
        test_recording = (
            "/path/to/test.mp3",
            "test.mp3",
            "pending",
            "",
            120.5,
            1024,
            "audio",
            "pending"
        )
        self.recording_id = None
        
        # Helper function to wait for signal
        def on_created(result):
            self.recording_id = result
            loop.quit()
        
        # Create a recording and get its ID
        loop = QEventLoop()
        self.db_manager.create_recording(test_recording, on_created)
        QTimer.singleShot(1000, loop.quit)  # Timeout after 1s in case operation fails
        loop.exec()
        
        # Ensure we have a valid recording ID
        self.assertIsNotNone(self.recording_id, "Failed to create test recording")
    
    def tearDown(self):
        """Clean up after the test."""
        # Shutdown database manager
        if hasattr(self, 'db_manager'):
            self.db_manager.shutdown()
        
        # Delete test database
        if os.path.exists(self.test_db_file):
            os.unlink(self.test_db_file)
        
        # Clean up application
        if hasattr(self, 'app'):
            self.app.quit()
    
    def test_signal_leak(self):
        """Test for signal leaks in database operations."""
        # Get initial receiver counts
        initial_counts = self.db_manager.get_signal_receiver_count()
        print(f"Initial signal receivers: {initial_counts}")
        
        # Memory usage before operations
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        print(f"Initial memory usage: {initial_memory:.2f} MB")
        
        # Run 100 update operations
        for i in range(100):
            loop = QEventLoop()
            
            # Update operation with different values
            self.db_manager.update_recording(
                self.recording_id, 
                lambda: loop.quit(), 
                transcription_status=f"status_{i}",
                transcription=f"test transcription {i}"
            )
            
            # Add timeout to prevent hanging
            QTimer.singleShot(100, loop.quit)  # 100ms timeout
            loop.exec()
            
            # Force error on every 10th operation to test error path
            if i % 10 == 0:
                # Invalid operation that will cause an error
                invalid_id = 999999  # Non-existent ID
                error_loop = QEventLoop()
                self.db_manager.update_recording(
                    invalid_id,
                    lambda: None,  # This should not be called
                    transcription=f"this will fail {i}"
                )
                # Allow time for error to be processed
                QTimer.singleShot(100, error_loop.quit)
                error_loop.exec()
        
        # Process any pending events
        QTest.qWait(500)
        
        # Get final receiver counts
        final_counts = self.db_manager.get_signal_receiver_count()
        print(f"Final signal receivers: {final_counts}")
        
        # Memory usage after operations
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        print(f"Final memory usage: {final_memory:.2f} MB")
        print(f"Memory difference: {final_memory - initial_memory:.2f} MB")
        
        # The signal receiver count should be the same as initial count
        # allowing for a small fixed difference due to application structure
        self.assertLessEqual(
            final_counts['operation_complete'] - initial_counts['operation_complete'],
            2,  # Allow for up to 2 extra receivers from test setup
            "Signal leak detected in operation_complete"
        )
        
        self.assertLessEqual(
            final_counts['error_occurred'] - initial_counts['error_occurred'],
            2,  # Allow for up to 2 extra receivers from test setup
            "Signal leak detected in error_occurred"
        )
        
        # Memory should be stable (±2 MB as specified in acceptance criteria)
        self.assertLess(
            abs(final_memory - initial_memory),
            2.0,  # Allow for up to 2 MB difference
            f"Memory leak detected: {final_memory - initial_memory:.2f} MB increase"
        )


if __name__ == '__main__':
    unittest.main()