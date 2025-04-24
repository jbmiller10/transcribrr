import unittest
import os
import tempfile
import shutil
import stat
from unittest.mock import MagicMock, patch

# Simple mock implementation of the key function to test the atomic rename logic
def atomic_rename(old_path, new_path, update_db_func):
    """
    Test version of atomic rename logic from handle_recording_rename.
    
    Args:
        old_path: Path to the file to be renamed
        new_path: New path for the file
        update_db_func: Function to call to update database
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # First attempt the filesystem rename
        os.rename(old_path, new_path)
        
        try:
            # Then update the database
            update_db_func()
            return True, None
            
        except Exception as db_error:
            # If DB update fails, roll back the filesystem rename
            try:
                os.rename(new_path, old_path)  # Roll back
                return False, f"Database error: {str(db_error)}"
            except OSError as rollback_error:
                return False, f"Critical error: DB update failed AND rollback failed: {str(rollback_error)}"
    
    except OSError as fs_error:
        # Filesystem rename failed
        return False, f"Filesystem error: {str(fs_error)}"


class TestAtomicRename(unittest.TestCase):
    """Test the atomic rename functionality isolated from PyQt dependencies."""

    def setUp(self):
        """Set up test environment with a temporary directory."""
        # Create a temporary directory for our test files
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test file to rename
        self.test_file_path = os.path.join(self.temp_dir, "test_recording.mp3")
        with open(self.test_file_path, "w") as f:
            f.write("test content")
        
        # Create a read-only subdirectory to simulate permission errors
        self.readonly_dir = os.path.join(self.temp_dir, "readonly")
        os.makedirs(self.readonly_dir)
        
        # Make the directory read-only on Unix systems
        if os.name != 'nt':  # Skip on Windows as permissions work differently
            os.chmod(self.readonly_dir, stat.S_IRUSR | stat.S_IXUSR)  # Read + execute only

    def tearDown(self):
        """Clean up temporary files."""
        # Restore permissions to allow deletion
        if os.name != 'nt' and os.path.exists(self.readonly_dir):  
            os.chmod(self.readonly_dir, stat.S_IRWXU)  # Read, write, execute
        
        # Remove temporary directory and all contents
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_successful_rename(self):
        """Test a successful atomic rename operation."""
        # Set up the test
        new_path = os.path.join(self.temp_dir, "renamed_recording.mp3")
        db_update_func = MagicMock()  # Mock function that succeeds
        
        # Call the function
        success, error = atomic_rename(self.test_file_path, new_path, db_update_func)
        
        # Verify success
        self.assertTrue(success)
        self.assertIsNone(error)
        
        # Verify that the file was renamed
        self.assertFalse(os.path.exists(self.test_file_path))
        self.assertTrue(os.path.exists(new_path))
        
        # Verify that DB update was called
        db_update_func.assert_called_once()

    def test_rename_to_readonly_directory(self):
        """Test rename operation to a read-only directory - should fail atomically."""
        # Set up the test - target path in read-only directory
        source_path = os.path.join(self.temp_dir, "test_readonly.mp3")
        with open(source_path, "w") as f:
            f.write("test content")
            
        target_path = os.path.join(self.readonly_dir, "read_only_test.mp3")
        db_update_func = MagicMock()  # This shouldn't be called
        
        # Call the function - should fail on filesystem rename
        success, error = atomic_rename(source_path, target_path, db_update_func)
        
        # Verify failure
        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertTrue("Filesystem error" in error)
        
        # Verify that original file still exists and target doesn't
        self.assertTrue(os.path.exists(source_path))
        self.assertFalse(os.path.exists(target_path))
        
        # Verify that DB update was NOT called
        db_update_func.assert_not_called()

    def test_db_error_with_rollback(self):
        """Test a scenario where DB update fails but filesystem rename succeeds and is rolled back."""
        # Set up the test
        new_path = os.path.join(self.temp_dir, "db_error_test.mp3")
        db_update_func = MagicMock(side_effect=Exception("DB update failed"))
        
        # Call the function
        success, error = atomic_rename(self.test_file_path, new_path, db_update_func)
        
        # Verify failure
        self.assertFalse(success)
        self.assertIsNotNone(error)
        self.assertTrue("Database error" in error)
        
        # Verify that original file was restored
        self.assertTrue(os.path.exists(self.test_file_path))
        self.assertFalse(os.path.exists(new_path))
        
        # Verify that DB update was attempted
        db_update_func.assert_called_once()


if __name__ == '__main__':
    unittest.main()