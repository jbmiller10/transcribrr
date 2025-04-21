"""Unit tests for path_utils.py."""

import unittest
import os
import sys
import importlib
from unittest.mock import patch, MagicMock

# We need to patch the logger to prevent logging during tests
# Create a mock logger
mock_logger = MagicMock()

# Patch the logging configuration to use our mock logger
@patch('logging.getLogger')
def get_patched_module(mock_get_logger):
    # Configure the mock to return our mock logger
    mock_get_logger.return_value = mock_logger
    
    # Clear cached imports to ensure fresh imports
    if 'app.path_utils' in sys.modules:
        del sys.modules['app.path_utils']
    
    # Import the module under test
    import app.path_utils
    # Return the freshly imported module
    return app.path_utils


class TestPathUtils(unittest.TestCase):
    """Test the path_utils module functionality."""
    
    def setUp(self):
        """Set up test environment."""
        # Create a backup of sys attributes we'll modify during tests
        self._sys_has_meipass = hasattr(sys, '_MEIPASS')
        self._sys_frozen = getattr(sys, 'frozen', False)
        self._sys_executable = sys.executable
        self._prev_sys_modules = dict(sys.modules)
        
        # Save original environment
        self._orig_environ = os.environ.copy()
    
    def tearDown(self):
        """Restore system state after tests."""
        # Restore sys attributes
        if self._sys_has_meipass and not hasattr(sys, '_MEIPASS'):
            # Was backed up but is now missing, restore it
            sys._MEIPASS = getattr(self, '_sys_meipass_value', None)
        elif hasattr(sys, '_MEIPASS') and not self._sys_has_meipass:
            # Was added during test, remove it
            delattr(sys, '_MEIPASS')
        
        # Restore frozen attribute if it was modified
        if hasattr(sys, 'frozen'):
            sys.frozen = self._sys_frozen
        elif self._sys_frozen:  # It was there before but now it's gone
            sys.frozen = self._sys_frozen
            
        # Restore executable
        sys.executable = self._sys_executable
        
        # Restore environment variables
        os.environ.clear()
        os.environ.update(self._orig_environ)
        
        # Restore modules dictionary
        sys.modules.clear()
        sys.modules.update(self._prev_sys_modules)
    
    @patch('app.path_utils._get_base_resource_path')
    def test_resource_path_dev_mode(self, mock_get_base_path):
        """Test resource_path in development mode."""
        # Set up the mock to return a specific path
        mock_get_base_path.return_value = '/fake/path/to'
        
        # Get the patched module
        path_utils = get_patched_module()
        
        # Test with relative path
        with patch('os.path.join', lambda base, rel: f"{base}/{rel}"):
            result = path_utils.resource_path('icons/app_icon.svg')
            self.assertEqual(result, '/fake/path/to/icons/app_icon.svg')
            
            # Test with no path (returns resource directory)
            result = path_utils.resource_path()
            self.assertEqual(result, '/fake/path/to')
    
    @patch('app.path_utils._get_base_resource_path')
    def test_resource_path_pyinstaller(self, mock_get_base_path):
        """Test resource_path in PyInstaller environment."""
        # Set up the mock to return a PyInstaller path
        mock_get_base_path.return_value = '/fake/pyinstaller/path'
        
        # Get the patched module
        path_utils = get_patched_module()
        
        # Test with no relative path
        result = path_utils.resource_path()
        self.assertEqual(result, '/fake/pyinstaller/path')
        
        # Test with relative path
        with patch('os.path.join', lambda base, rel: f"{base}/{rel}"):
            result = path_utils.resource_path('icons/app_icon.svg')
            self.assertEqual(result, '/fake/pyinstaller/path/icons/app_icon.svg')
    
    @patch('app.path_utils._get_base_resource_path')
    def test_resource_path_py2app(self, mock_get_base_path):
        """Test resource_path in py2app environment."""
        # Set up the mock to return a py2app path
        mock_get_base_path.return_value = '/Applications/MyApp.app/Contents/Resources'
        
        # Get the patched module
        path_utils = get_patched_module()
        
        # Test with no relative path
        result = path_utils.resource_path()
        self.assertEqual(result, '/Applications/MyApp.app/Contents/Resources')
        
        # Test with relative path
        with patch('os.path.join', lambda base, rel: f"{base}/{rel}"):
            result = path_utils.resource_path('icons/app_icon.svg')
            self.assertEqual(result, '/Applications/MyApp.app/Contents/Resources/icons/app_icon.svg')
    
    @patch('os.path.dirname')
    @patch('os.path.abspath')
    @patch('os.makedirs')
    def test_get_user_data_path_dev(self, mock_makedirs, mock_abspath, mock_dirname):
        """Test get_user_data_path in development mode."""
        # Set up environment for development mode
        if hasattr(sys, '_MEIPASS'):
            delattr(sys, '_MEIPASS')
        if hasattr(sys, 'frozen'):
            del sys.frozen
        if 'TRANSCRIBRR_USER_DATA_DIR' in os.environ:
            del os.environ['TRANSCRIBRR_USER_DATA_DIR']
        
        # Set up mocks
        mock_abspath.return_value = '/fake/path/to/app/path_utils.py'
        mock_dirname.side_effect = ['/fake/path/to/app', '/fake/path/to']
        
        # Get the patched module
        path_utils = get_patched_module()
        
        # Test function
        result = path_utils.get_user_data_path()
        self.assertEqual(result, '/fake/path/to')
        
        # Verify makedirs wasn't called for dev path (it's assumed to exist)
        mock_makedirs.assert_not_called()
    
    @patch('appdirs.user_data_dir')
    @patch('os.makedirs')
    def test_get_user_data_path_packaged(self, mock_makedirs, mock_user_data_dir):
        """Test get_user_data_path in packaged environment."""
        # Set up environment for packaged app
        sys._MEIPASS = '/fake/pyinstaller/path'
        if 'TRANSCRIBRR_USER_DATA_DIR' in os.environ:
            del os.environ['TRANSCRIBRR_USER_DATA_DIR']
        
        # Set up mocks
        mock_user_data_dir.return_value = '/Users/username/Library/Application Support/Transcribrr'
        
        # Get the patched module
        path_utils = get_patched_module()
        
        # Test function
        result = path_utils.get_user_data_path()
        self.assertEqual(result, '/Users/username/Library/Application Support/Transcribrr')
        
        # Verify appdirs was called with expected args
        mock_user_data_dir.assert_called_once_with('Transcribrr', 'John Miller')
        mock_makedirs.assert_called_once_with('/Users/username/Library/Application Support/Transcribrr', exist_ok=True)
    
    @patch('os.makedirs')
    def test_get_user_data_path_env_var(self, mock_makedirs):
        """Test get_user_data_path with environment variable."""
        # Set environment variable
        os.environ['TRANSCRIBRR_USER_DATA_DIR'] = '/custom/data/path'
        
        # Get the patched module
        path_utils = get_patched_module()
        
        # Test function
        result = path_utils.get_user_data_path()
        self.assertEqual(result, '/custom/data/path')
        
        # Verify makedirs was called exactly once
        mock_makedirs.assert_called_once_with('/custom/data/path', exist_ok=True)


if __name__ == '__main__':
    unittest.main()