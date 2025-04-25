import unittest
import os
import sqlite3
import tempfile
import time
from unittest.mock import MagicMock, patch

from app.FolderManager import FolderManager
from app.DatabaseManager import DatabaseManager


class TestCreateFolder(unittest.TestCase):
    """Test the folder creation functionality, specifically ID retrieval."""

    def setUp(self):
        """Set up test environment with temp database."""
        # Create a temp directory for our test database
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_db.sqlite")
        
        # Patch the DATABASE_PATH constant
        self.db_path_patcher = patch('app.constants.DATABASE_PATH', self.db_path)
        self.db_path_patcher.start()
        
        # Create test database
        self._create_test_db()
        
        # Initialize the folder manager with our test database
        self.folder_manager = FolderManager()

    def tearDown(self):
        """Clean up test environment."""
        # Stop all patches
        self.db_path_patcher.stop()
        
        # Shutdown database connections
        if hasattr(self, 'folder_manager') and self.folder_manager:
            self.folder_manager.db_manager.shutdown()
        
        # Remove test database
        try:
            os.remove(self.db_path)
        except:
            pass  # Ignore errors
            
        # Remove temp directory
        try:
            os.rmdir(self.temp_dir)
        except:
            pass  # Ignore errors

    def _create_test_db(self):
        """Create test database with necessary tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create folders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_id INTEGER,
                created_at TEXT,
                FOREIGN KEY (parent_id) REFERENCES folders(id) ON DELETE CASCADE
            )
        """)
        
        # Create recording_folders table for relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recording_folders (
                recording_id INTEGER,
                folder_id INTEGER,
                PRIMARY KEY (recording_id, folder_id),
                FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
            )
        """)
        
        # Create recordings table (minimal schema for testing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT,
                file_path TEXT,
                date_created TEXT,
                duration REAL,
                raw_transcript TEXT,
                processed_text TEXT,
                raw_transcript_formatted TEXT,
                processed_text_formatted TEXT
            )
        """)
        
        conn.commit()
        conn.close()

    def test_create_folder_returns_valid_id(self):
        """Test that create_folder returns a valid ID immediately after creation."""
        # Arrange
        test_folder_name = "Test Folder"
        create_success = False
        folder_id = None
        error_message = None
        
        # Define callback to capture results
        def folder_created_callback(success, result):
            nonlocal create_success, folder_id, error_message
            create_success = success
            if success:
                folder_id = result
            else:
                error_message = result
                print(f"Folder creation failed: {error_message}")
        
        # Act
        self.folder_manager.create_folder(test_folder_name, None, folder_created_callback)
        
        # Wait for async operations to complete
        # This is necessary because the database operations are async
        timeout = 10.0  # 10 seconds timeout
        start_time = time.time()
        
        # Print debug info in the loop
        while time.time() - start_time < timeout:
            print(f"Waiting... create_success: {create_success}, folder_id: {folder_id}, error: {error_message}")
            if create_success and folder_id is not None:
                break
            time.sleep(0.5)
        
        # Assert
        self.assertTrue(create_success, f"Folder creation should succeed. Error: {error_message}")
        self.assertIsNotNone(folder_id, "Folder ID should not be None")
        self.assertGreater(folder_id, 0, "Folder ID should be greater than 0")
        
        # Verify the folder exists in the database with the correct ID
        def verify_folder_callback(success, result):
            nonlocal create_success
            create_success = success
            self.assertEqual(len(result), 1, "Should find exactly one folder")
            self.assertEqual(result[0][0], folder_id, "Retrieved folder ID should match")
            self.assertEqual(result[0][1], test_folder_name, "Retrieved folder name should match")
        
        # Query the database directly to verify
        self.folder_manager.db_manager.execute_query(
            "SELECT id, name FROM folders WHERE id = ?", 
            [folder_id], 
            callback=verify_folder_callback
        )
        
        # Wait for the query to complete
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(0.1)


if __name__ == '__main__':
    unittest.main()