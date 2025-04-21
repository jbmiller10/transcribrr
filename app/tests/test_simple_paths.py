"""Simple tests for path_utils.py."""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Import the module before patching
from app.path_utils import resource_path, get_user_data_path, _get_base_resource_path

class TestSimplePaths(unittest.TestCase):
    """Simple tests for path_utils.py."""
    
    def setUp(self):
        """Set up test environment."""
        self._original_meipass = hasattr(sys, '_MEIPASS')
        self._original_frozen = hasattr(sys, 'frozen')
        self._original_env = os.environ.copy()
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original _MEIPASS attribute
        if hasattr(sys, '_MEIPASS') and not self._original_meipass:
            delattr(sys, '_MEIPASS')
        elif not hasattr(sys, '_MEIPASS') and self._original_meipass:
            # Restore original value if needed
            pass
        
        # Restore original frozen attribute
        if hasattr(sys, 'frozen') and not self._original_frozen:
            delattr(sys, 'frozen')
        elif not hasattr(sys, 'frozen') and self._original_frozen:
            # Restore original value if needed
            pass
        
        # Restore environment
        os.environ.clear()
        os.environ.update(self._original_env)
    
    def test_resource_path_with_mocks(self):
        """Test resource_path with mocked functions."""
        # Test with mocked _get_base_resource_path
        with patch('app.path_utils._get_base_resource_path', return_value='/mock/base/path'):
            # Test with no path
            result = resource_path()
            self.assertEqual(result, '/mock/base/path')
            
            # Test with path
            with patch('os.path.join', return_value='/mock/base/path/test.txt'):
                result = resource_path('test.txt')
                self.assertEqual(result, '/mock/base/path/test.txt')
    
    def test_environment_specific_paths(self):
        """Test environment-specific path resolution."""
        # Set up PyInstaller case
        with patch.object(sys, '_MEIPASS', '/pyinstaller/path', create=True):
            base_path = _get_base_resource_path()
            self.assertEqual(base_path, '/pyinstaller/path')
        
        # Set up py2app case
        with patch.object(sys, 'frozen', True, create=True), \
             patch('sys.executable', '/Applications/App.app/Contents/MacOS/app'), \
             patch('os.path.dirname', return_value='/Applications/App.app/Contents/MacOS'), \
             patch('os.path.normpath', return_value='/Applications/App.app/Contents/Resources'):
            base_path = _get_base_resource_path()
            self.assertEqual(base_path, '/Applications/App.app/Contents/Resources')
        
        # Development mode case
        with patch('os.path.abspath', return_value='/home/user/project/app/path_utils.py'), \
             patch('os.path.dirname', side_effect=['/home/user/project/app', '/home/user/project']):
            # Make sure sys attributes are not present
            if hasattr(sys, '_MEIPASS'):
                delattr(sys, '_MEIPASS')
            if hasattr(sys, 'frozen'):
                delattr(sys, 'frozen')
            
            base_path = _get_base_resource_path()
            self.assertEqual(base_path, '/home/user/project')
    
    def test_get_user_data_path_env_var(self):
        """Test get_user_data_path with environment variable."""
        with patch('os.makedirs') as mock_makedirs:
            # Set environment variable
            os.environ['TRANSCRIBRR_USER_DATA_DIR'] = '/custom/data/path'
            
            # Call the function
            result = get_user_data_path()
            
            # Check result
            self.assertEqual(result, '/custom/data/path')
            
            # Verify makedirs was called
            mock_makedirs.assert_called_once_with('/custom/data/path', exist_ok=True)
    
    @patch('appdirs.user_data_dir')
    @patch('os.makedirs')
    def test_get_user_data_path_packaged(self, mock_makedirs, mock_user_data_dir):
        """Test get_user_data_path in packaged environment."""
        # Set up environment
        if hasattr(sys, '_MEIPASS'):
            delattr(sys, '_MEIPASS')
        setattr(sys, 'frozen', True)
        
        # Remove environment variable if exists
        if 'TRANSCRIBRR_USER_DATA_DIR' in os.environ:
            del os.environ['TRANSCRIBRR_USER_DATA_DIR']
        
        # Set up mocks
        mock_user_data_dir.return_value = '/user/data/dir'
        
        # Call function
        result = get_user_data_path()
        
        # Check result
        self.assertEqual(result, '/user/data/dir')
        
        # Verify mocks
        mock_user_data_dir.assert_called_once_with('Transcribrr', 'John Miller')
        mock_makedirs.assert_called_once_with('/user/data/dir', exist_ok=True)
    
    @patch('os.path.abspath')
    @patch('os.path.dirname')
    def test_get_user_data_path_dev(self, mock_dirname, mock_abspath):
        """Test get_user_data_path in development environment."""
        # Set up environment
        if hasattr(sys, '_MEIPASS'):
            delattr(sys, '_MEIPASS')
        if hasattr(sys, 'frozen'):
            delattr(sys, 'frozen')
        
        # Remove environment variable if exists
        if 'TRANSCRIBRR_USER_DATA_DIR' in os.environ:
            del os.environ['TRANSCRIBRR_USER_DATA_DIR']
        
        # Set up mocks
        mock_abspath.return_value = '/dev/path/app/path_utils.py'
        mock_dirname.side_effect = ['/dev/path/app', '/dev/path']
        
        # Call function
        result = get_user_data_path()
        
        # Check result
        self.assertEqual(result, '/dev/path')


if __name__ == '__main__':
    unittest.main()