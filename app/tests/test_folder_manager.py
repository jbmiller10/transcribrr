"""
Unit tests for FolderManager class.
"""

import os
import sys
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock, MagicMock, call
from PyQt6.QtCore import QApplication, QTimer, QEventLoop

# Import the modules to be tested
from app.FolderManager import FolderManager
from app.DatabaseManager import DatabaseManager
import app.constants

class TestFolderManager(unittest.TestCase):
    """Test suite for the FolderManager class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # Create a temporary file for the test database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='.sqlite')
        
        # Save the original database path
        cls.original_db_path = app.constants.DATABASE_PATH
        
        # Reset singleton instances
        FolderManager._instance = None
        DatabaseManager._instance = None
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment after all tests."""
        # Restore the original database path
        app.constants.DATABASE_PATH = cls.original_db_path
        
        # Close and remove the temporary database file
        os.close(cls.temp_db_fd)
        if os.path.exists(cls.temp_db_path):
            os.unlink(cls.temp_db_path)
        
        # Reset singleton instances
        FolderManager._instance = None
        DatabaseManager._instance = None
    
    def setUp(self):
        """Set up before each test."""
        # Override the database path for testing
        app.constants.DATABASE_PATH = self.temp_db_path
        
        # Reset singleton instances
        FolderManager._instance = None
        DatabaseManager._instance = None
        
        # Create test database schema
        conn = sqlite3.connect(self.temp_db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (parent_id) REFERENCES folders (id)
                    ON DELETE CASCADE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                date_created TEXT NOT NULL,
                duration TEXT,
                raw_transcript TEXT,
                processed_text TEXT,
                raw_transcript_formatted BLOB,
                processed_text_formatted BLOB
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recording_folders (
                recording_id INTEGER NOT NULL,
                folder_id INTEGER NOT NULL,
                PRIMARY KEY (recording_id, folder_id),
                FOREIGN KEY (recording_id) REFERENCES recordings (id)
                    ON DELETE CASCADE,
                FOREIGN KEY (folder_id) REFERENCES folders (id)
                    ON DELETE CASCADE
            )
        ''')
        conn.commit()
        conn.close()
        
        # Mock DatabaseManager for faster testing
        self.mock_db_manager = MagicMock()
        
        # Patch DatabaseManager.instance() to return our mock
        self.db_manager_patch = patch('app.DatabaseManager.DatabaseManager.instance', 
                                     return_value=self.mock_db_manager)
        self.mock_db_instance = self.db_manager_patch.start()
        
        # Also patch FolderManager's init to use our mock
        original_init = FolderManager.__init__
        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.db_manager = TestFolderManager.mock_db_manager
        self.init_patch = patch.object(FolderManager, '__init__', patched_init)
        self.init_patch.start()
    
    def tearDown(self):
        """Clean up after each test."""
        # Stop patches
        self.db_manager_patch.stop()
        self.init_patch.stop()
        
        # Clean up any pending DB operations
        if hasattr(self, 'folder_manager') and hasattr(self.folder_manager, 'db_manager'):
            if hasattr(self.folder_manager.db_manager, 'shutdown'):
                self.folder_manager.db_manager.shutdown()
    
    def test_singleton_instance(self):
        """Test that the instance() method returns the same object."""
        folder_manager1 = FolderManager.instance()
        folder_manager2 = FolderManager.instance()
        self.assertIs(folder_manager1, folder_manager2, "FolderManager.instance() should return the same object")
    
    def test_load_folders_builds_hierarchy(self):
        """Test that load_folders builds the folder hierarchy correctly."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Mock DB response with sample folder data (including parent/child relationships)
        sample_folders = [
            (1, "Root Folder 1", None, "2025-01-01 12:00:00"),
            (2, "Child Folder 1", 1, "2025-01-01 12:01:00"),
            (3, "Grandchild Folder", 2, "2025-01-01 12:02:00"),
            (4, "Root Folder 2", None, "2025-01-01 12:03:00"),
            (5, "Child Folder 2", 1, "2025-01-01 12:04:00")
        ]
        
        # Set up the mock to return our sample folders
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback from kwargs
            callback = kwargs.get('callback')
            if callback and args[0].strip().startswith('SELECT id, name, parent_id'):
                callback(sample_folders)
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call load_folders
        callback_called = False
        def test_callback():
            nonlocal callback_called
            callback_called = True
        
        folder_manager.load_folders(callback=test_callback)
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Verify the folders were loaded
        self.assertEqual(len(folder_manager.folders), 5, "Should have loaded 5 folders")
        
        # Verify parent-child relationships
        root_folders = [f for f in folder_manager.folders if f['parent_id'] is None]
        self.assertEqual(len(root_folders), 2, "Should have 2 root folders")
        
        # Find Root Folder 1 and verify its children
        root_folder_1 = next((f for f in folder_manager.folders if f['id'] == 1), None)
        self.assertIsNotNone(root_folder_1, "Root Folder 1 should exist")
        self.assertEqual(len(root_folder_1['children']), 2, "Root Folder 1 should have 2 children")
        
        # Find Child Folder 1 and verify its children
        child_folder_1 = next((f for f in folder_manager.folders if f['id'] == 2), None)
        self.assertIsNotNone(child_folder_1, "Child Folder 1 should exist")
        self.assertEqual(len(child_folder_1['children']), 1, "Child Folder 1 should have 1 child")
        
        # Verify callback was called
        self.assertTrue(callback_called, "Callback should have been called")
    
    def test_create_folder_root_success(self):
        """Test creating a new root folder successfully."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        folder_manager.folders = []  # Start with empty folders
        
        # Set up the mock to simulate successful folder creation
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback from kwargs
            callback = kwargs.get('callback')
            if callback and args[0].strip().startswith('INSERT INTO folders'):
                callback(1)  # Return folder ID 1
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call create_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.create_folder("Test Root Folder", callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "create_folder should return True to indicate operation started")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        self.assertEqual(callback_result, 1, "Callback should have been called with folder_id=1")
        
        # Verify the folder was added to the in-memory structure
        self.assertEqual(len(folder_manager.folders), 1, "Should have 1 folder in memory")
        self.assertEqual(folder_manager.folders[0]['name'], "Test Root Folder", 
                      "Folder name should be 'Test Root Folder'")
        self.assertIsNone(folder_manager.folders[0]['parent_id'], "Root folder should have parent_id=None")
        self.assertEqual(folder_manager.folders[0]['id'], 1, "Folder ID should be 1")
    
    def test_create_folder_sub_success(self):
        """Test creating a new subfolder successfully."""
        # Create a FolderManager instance with a root folder
        folder_manager = FolderManager.instance()
        folder_manager.folders = [{
            'id': 1,
            'name': "Root Folder",
            'parent_id': None,
            'created_at': "2025-01-01 12:00:00",
            'children': []
        }]
        
        # Set up the mock to simulate successful folder creation
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback from kwargs
            callback = kwargs.get('callback')
            if callback and args[0].strip().startswith('INSERT INTO folders'):
                callback(2)  # Return folder ID 2
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call create_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.create_folder("Child Folder", parent_id=1, callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "create_folder should return True to indicate operation started")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        self.assertEqual(callback_result, 2, "Callback should have been called with folder_id=2")
        
        # Verify the folder was added to the in-memory structure
        self.assertEqual(len(folder_manager.folders), 2, "Should have 2 folders in memory")
        child_folder = next((f for f in folder_manager.folders if f['id'] == 2), None)
        self.assertIsNotNone(child_folder, "Child folder should exist")
        self.assertEqual(child_folder['name'], "Child Folder", "Folder name should be 'Child Folder'")
        self.assertEqual(child_folder['parent_id'], 1, "Child folder should have parent_id=1")
        
        # Verify the child was added to the parent's children list
        root_folder = next((f for f in folder_manager.folders if f['id'] == 1), None)
        self.assertEqual(len(root_folder['children']), 1, "Root folder should have 1 child")
        self.assertEqual(root_folder['children'][0]['id'], 2, "Child's ID should be 2")
    
    def test_create_folder_duplicate_name_at_same_level(self):
        """Test creating a folder with a duplicate name at the same level fails."""
        # Create a FolderManager instance with an existing folder
        folder_manager = FolderManager.instance()
        folder_manager.folders = [{
            'id': 1,
            'name': "Existing Folder",
            'parent_id': None,
            'created_at': "2025-01-01 12:00:00",
            'children': []
        }]
        
        # Call create_folder with the same name
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.create_folder("Existing Folder", callback=test_callback)
        
        # Verify the operation failed
        self.assertFalse(result, "create_folder should return False for duplicate folder name")
        
        # Verify the DB was not called
        self.mock_db_manager.execute_query.assert_not_called()
        
        # Verify the callback was called with failure
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertFalse(callback_success, "Callback should have been called with success=False")
        self.assertEqual(callback_result, "A folder with this name already exists", 
                       "Callback should have been called with error message")
        
        # Verify no new folder was added
        self.assertEqual(len(folder_manager.folders), 1, "Should still have 1 folder in memory")
    
    def test_create_folder_db_error(self):
        """Test handling database error during folder creation."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        folder_manager.folders = []  # Start with empty folders
        
        # Set up the mock to simulate a database error
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback from kwargs
            callback = kwargs.get('callback')
            if callback and args[0].strip().startswith('INSERT INTO folders'):
                callback(None)  # Return None to simulate failure
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call create_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.create_folder("Test Folder", callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "create_folder should return True to indicate operation started")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Verify the callback was called with failure
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertFalse(callback_success, "Callback should have been called with success=False")
        self.assertEqual(callback_result, "Database error: Failed to get new folder ID", 
                       "Callback should have been called with error message")
        
        # Verify no folder was added to the in-memory structure
        self.assertEqual(len(folder_manager.folders), 0, "Should have 0 folders in memory")
    
    def test_rename_folder_success(self):
        """Test renaming a folder successfully."""
        # Create a FolderManager instance with an existing folder
        folder_manager = FolderManager.instance()
        folder_manager.folders = [{
            'id': 1,
            'name': "Original Name",
            'parent_id': None,
            'created_at': "2025-01-01 12:00:00",
            'children': []
        }]
        
        # Set up the mock to simulate successful folder rename
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback from kwargs
            callback = kwargs.get('callback')
            if callback and args[0].strip().startswith('UPDATE folders'):
                callback([])  # Return empty result to simulate success
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call rename_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.rename_folder(1, "New Name", callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "rename_folder should return True to indicate operation started")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        
        # Verify the folder was renamed in the in-memory structure
        self.assertEqual(folder_manager.folders[0]['name'], "New Name", 
                      "Folder name should have been updated to 'New Name'")
    
    def test_rename_folder_not_found(self):
        """Test renaming a non-existent folder fails."""
        # Create a FolderManager instance with an existing folder
        folder_manager = FolderManager.instance()
        folder_manager.folders = [{
            'id': 1,
            'name': "Existing Folder",
            'parent_id': None,
            'created_at': "2025-01-01 12:00:00",
            'children': []
        }]
        
        # Call rename_folder with a non-existent ID
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.rename_folder(999, "New Name", callback=test_callback)
        
        # Verify the operation failed
        self.assertFalse(result, "rename_folder should return False for non-existent folder")
        
        # Verify the DB was not called
        self.mock_db_manager.execute_query.assert_not_called()
        
        # Verify the callback was called with failure
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertFalse(callback_success, "Callback should have been called with success=False")
        self.assertEqual(callback_result, "Folder not found", 
                       "Callback should have been called with error message")
    
    def test_rename_folder_duplicate_name_at_same_level(self):
        """Test renaming a folder to a duplicate name at the same level fails."""
        # Create a FolderManager instance with two folders at the same level
        folder_manager = FolderManager.instance()
        folder_manager.folders = [
            {
                'id': 1,
                'name': "Folder One",
                'parent_id': None,
                'created_at': "2025-01-01 12:00:00",
                'children': []
            },
            {
                'id': 2,
                'name': "Folder Two",
                'parent_id': None,
                'created_at': "2025-01-01 12:01:00",
                'children': []
            }
        ]
        
        # Call rename_folder to rename Folder One to Folder Two
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.rename_folder(1, "Folder Two", callback=test_callback)
        
        # Verify the operation failed
        self.assertFalse(result, "rename_folder should return False for duplicate folder name")
        
        # Verify the DB was not called
        self.mock_db_manager.execute_query.assert_not_called()
        
        # Verify the callback was called with failure
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertFalse(callback_success, "Callback should have been called with success=False")
        self.assertEqual(callback_result, "A folder with this name already exists", 
                       "Callback should have been called with error message")
        
        # Verify the folder name was not changed
        self.assertEqual(folder_manager.folders[0]['name'], "Folder One", 
                      "Folder name should not have been changed")
    
    def test_delete_folder_success(self):
        """Test deleting a folder successfully."""
        # Create a FolderManager instance with a folder
        folder_manager = FolderManager.instance()
        folder_manager.folders = [{
            'id': 1,
            'name': "Test Folder",
            'parent_id': None,
            'created_at': "2025-01-01 12:00:00",
            'children': []
        }]
        
        # Set up the mock to simulate successful folder deletion
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback from kwargs
            callback = kwargs.get('callback')
            # First query: remove associations
            if callback and args[0].strip().startswith('DELETE FROM recording_folders'):
                callback([])  # Return empty result
            # Second query: delete folder
            elif callback and args[0].strip().startswith('DELETE FROM folders'):
                callback([])  # Return empty result
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call delete_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.delete_folder(1, callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "delete_folder should return True to indicate operation started")
        
        # Verify the queries were executed
        self.assertEqual(self.mock_db_manager.execute_query.call_count, 2,
                      "execute_query should have been called twice")
        
        # Verify the callbacks executed to completion
        # Since the callbacks modify the state over time, we need to check the final state
        
        # Wait for the callbacks to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        
        # Verify the folder was removed from the in-memory structure
        self.assertEqual(len(folder_manager.folders), 0, "Folder should have been removed from memory")
    
    def test_delete_folder_not_found(self):
        """Test deleting a non-existent folder fails."""
        # Create a FolderManager instance with a folder
        folder_manager = FolderManager.instance()
        folder_manager.folders = [{
            'id': 1,
            'name': "Test Folder",
            'parent_id': None,
            'created_at': "2025-01-01 12:00:00",
            'children': []
        }]
        
        # Call delete_folder with a non-existent ID
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.delete_folder(999, callback=test_callback)
        
        # Verify the operation failed
        self.assertFalse(result, "delete_folder should return False for non-existent folder")
        
        # Verify the DB was not called
        self.mock_db_manager.execute_query.assert_not_called()
        
        # Verify the callback was called with failure
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertFalse(callback_success, "Callback should have been called with success=False")
        self.assertEqual(callback_result, "Folder not found", 
                       "Callback should have been called with error message")
    
    def test_add_recording_to_folder_new_association(self):
        """Test adding a recording to a folder creates a new association."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Set up the mock to simulate the sequence of operations
        call_sequence = []
        
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback and query from args
            callback = kwargs.get('callback')
            query = args[0].strip()
            
            if callback:
                # Step 1: Check if association exists
                if query.startswith('SELECT 1 FROM recording_folders'):
                    call_sequence.append('check')
                    callback([])  # Return empty result, association doesn't exist
                
                # Step 2: Remove from all other folders
                elif query.startswith('DELETE FROM recording_folders WHERE recording_id'):
                    call_sequence.append('delete')
                    callback([])  # Return empty result
                
                # Step 3: Insert the new association
                elif query.startswith('INSERT INTO recording_folders'):
                    call_sequence.append('insert')
                    callback([])  # Return empty result
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call add_recording_to_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.add_recording_to_folder(1, 2, callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "add_recording_to_folder should return True to indicate operation started")
        
        # Verify the queries were executed in the correct sequence
        self.assertEqual(self.mock_db_manager.execute_query.call_count, 3,
                      "execute_query should have been called three times")
        
        # Wait for all callbacks to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the operation sequence was correct
        self.assertEqual(call_sequence, ['check', 'delete', 'insert'],
                      "Operations should have been performed in the correct sequence")
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
    
    def test_add_recording_to_folder_already_exists(self):
        """Test adding a recording to a folder where the association already exists."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Set up the mock to simulate existing association
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback and query from args
            callback = kwargs.get('callback')
            query = args[0].strip()
            
            if callback and query.startswith('SELECT 1 FROM recording_folders'):
                callback([(1,)])  # Return a result to indicate association exists
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call add_recording_to_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.add_recording_to_folder(1, 2, callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "add_recording_to_folder should return True to indicate operation started")
        
        # Verify only the check query was executed
        self.assertEqual(self.mock_db_manager.execute_query.call_count, 1,
                      "execute_query should have been called once")
        
        # Wait for the callback to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
    
    def test_remove_recording_from_folder(self):
        """Test removing a recording from a folder."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Set up the mock to simulate successful removal
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback and query from args
            callback = kwargs.get('callback')
            query = args[0].strip()
            
            if callback and query.startswith('DELETE FROM recording_folders WHERE recording_id'):
                callback([])  # Return empty result
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call remove_recording_from_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.remove_recording_from_folder(1, 2, callback=test_callback)
        
        # Verify the operation was initiated
        self.assertTrue(result, "remove_recording_from_folder should return True to indicate operation started")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Wait for the callback to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the callback was called with success
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
    
    def test_get_recordings_in_folder(self):
        """Test retrieving recordings in a folder."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Mock sample recordings
        sample_recordings = [
            (1, "recording1.mp3", "/path/to/recording1.mp3", "2025-01-01", "00:05:00", 
             "Raw transcript 1", "Processed text 1", None, None),
            (2, "recording2.mp3", "/path/to/recording2.mp3", "2025-01-02", "00:03:30", 
             "Raw transcript 2", "Processed text 2", None, None)
        ]
        
        # Set up the mock to return sample recordings
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback and query from args
            callback = kwargs.get('callback')
            query = args[0].strip()
            
            if callback and query.startswith('SELECT r.id, r.filename'):
                callback(sample_recordings)
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call get_recordings_in_folder
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.get_recordings_in_folder(1, callback=test_callback)
        
        # Verify the return value is None (async operation)
        self.assertIsNone(result, "get_recordings_in_folder should return None for async operation")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Wait for the callback to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the callback was called with success and the recordings
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        self.assertEqual(callback_result, sample_recordings, 
                       "Callback should have been called with the sample recordings")
    
    def test_get_folders_for_recording(self):
        """Test retrieving folders for a recording."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Mock sample folders
        sample_folders = [
            (1, "Folder 1", None, "2025-01-01 12:00:00"),
            (2, "Folder 2", 1, "2025-01-01 12:01:00")
        ]
        
        # Set up the mock to return sample folders
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback and query from args
            callback = kwargs.get('callback')
            query = args[0].strip()
            
            if callback and query.startswith('SELECT f.id, f.name'):
                callback(sample_folders)
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call get_folders_for_recording
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.get_folders_for_recording(1, callback=test_callback)
        
        # Verify the return value is an empty list (async operation)
        self.assertEqual(result, [], "get_folders_for_recording should return [] for async operation")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Wait for the callback to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the callback was called with success and the folders
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        self.assertEqual(callback_result, sample_folders, 
                       "Callback should have been called with the sample folders")
    
    def test_get_recordings_not_in_folders(self):
        """Test retrieving recordings not in any folder."""
        # Create a FolderManager instance
        folder_manager = FolderManager.instance()
        
        # Mock sample recordings
        sample_recordings = [
            (1, "recording1.mp3", "/path/to/recording1.mp3", "2025-01-01", "00:05:00", 
             "Raw transcript 1", "Processed text 1", None, None),
            (2, "recording2.mp3", "/path/to/recording2.mp3", "2025-01-02", "00:03:30", 
             "Raw transcript 2", "Processed text 2", None, None)
        ]
        
        # Set up the mock to return sample recordings
        def execute_query_side_effect(*args, **kwargs):
            # Extract the callback and query from args
            callback = kwargs.get('callback')
            query = args[0].strip()
            
            if callback and query.startswith('SELECT r.id, r.filename'):
                callback(sample_recordings)
        
        self.mock_db_manager.execute_query.side_effect = execute_query_side_effect
        
        # Call get_recordings_not_in_folders
        callback_called = False
        callback_success = None
        callback_result = None
        
        def test_callback(success, result):
            nonlocal callback_called, callback_success, callback_result
            callback_called = True
            callback_success = success
            callback_result = result
        
        result = folder_manager.get_recordings_not_in_folders(callback=test_callback)
        
        # Verify the return value is None (async operation)
        self.assertIsNone(result, "get_recordings_not_in_folders should return None for async operation")
        
        # Verify the query was executed
        self.mock_db_manager.execute_query.assert_called_once()
        
        # Wait for the callback to complete
        callback_executed = False
        while not callback_executed:
            if callback_called:
                callback_executed = True
            QApplication.processEvents()
        
        # Verify the callback was called with success and the recordings
        self.assertTrue(callback_called, "Callback should have been called")
        self.assertTrue(callback_success, "Callback should have been called with success=True")
        self.assertEqual(callback_result, sample_recordings, 
                       "Callback should have been called with the sample recordings")
    
    def test_get_folder_by_id(self):
        """Test retrieving a folder by ID."""
        # Create a FolderManager instance with a few folders
        folder_manager = FolderManager.instance()
        folder_manager.folders = [
            {
                'id': 1,
                'name': "Folder 1",
                'parent_id': None,
                'created_at': "2025-01-01 12:00:00",
                'children': []
            },
            {
                'id': 2,
                'name': "Folder 2",
                'parent_id': 1,
                'created_at': "2025-01-01 12:01:00",
                'children': []
            }
        ]
        
        # Call get_folder_by_id for an existing folder
        folder = folder_manager.get_folder_by_id(2)
        
        # Verify the correct folder was returned
        self.assertIsNotNone(folder, "get_folder_by_id should return a folder for valid ID")
        self.assertEqual(folder['id'], 2, "Folder ID should be 2")
        self.assertEqual(folder['name'], "Folder 2", "Folder name should be 'Folder 2'")
        
        # Call get_folder_by_id for a non-existent folder
        folder = folder_manager.get_folder_by_id(999)
        
        # Verify None was returned
        self.assertIsNone(folder, "get_folder_by_id should return None for invalid ID")
    
    def test_folder_exists(self):
        """Test checking if a folder name exists at a specific level."""
        # Create a FolderManager instance with a few folders
        folder_manager = FolderManager.instance()
        folder_manager.folders = [
            {
                'id': 1,
                'name': "Root Folder",
                'parent_id': None,
                'created_at': "2025-01-01 12:00:00",
                'children': []
            },
            {
                'id': 2,
                'name': "Child Folder",
                'parent_id': 1,
                'created_at': "2025-01-01 12:01:00",
                'children': []
            },
            {
                'id': 3,
                'name': "Another Root",
                'parent_id': None,
                'created_at': "2025-01-01 12:02:00",
                'children': []
            }
        ]
        
        # Test with existing root folder
        self.assertTrue(folder_manager.folder_exists("Root Folder", None), 
                      "folder_exists should return True for existing root folder")
        
        # Test with existing child folder
        self.assertTrue(folder_manager.folder_exists("Child Folder", 1), 
                      "folder_exists should return True for existing child folder")
        
        # Test with non-existent folder name
        self.assertFalse(folder_manager.folder_exists("Non-existent", None), 
                       "folder_exists should return False for non-existent folder name")
        
        # Test with existing name but at different level
        self.assertFalse(folder_manager.folder_exists("Child Folder", None), 
                       "folder_exists should return False for name at different level")
        
        # Test with exclude_id parameter
        self.assertFalse(folder_manager.folder_exists("Root Folder", None, exclude_id=1), 
                       "folder_exists should return False when excluding the matching folder")


if __name__ == '__main__':
    unittest.main()