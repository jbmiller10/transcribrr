"""Simple unit tests for path_utils.py."""

import unittest
import os
import sys
from unittest.mock import patch

# Directly import functions from path_utils
from app.path_utils import resource_path, get_user_data_path

class TestPathUtils(unittest.TestCase):
    """Unit tests for path utils functions."""
    
    @patch('app.path_utils._get_base_resource_path')
    def test_resource_path(self, mock_base_path):
        """Test resource_path function."""
        # Configure mock
        mock_base_path.return_value = '/mock/path'
        
        # Test with no relative path
        self.assertEqual(resource_path(), '/mock/path')
        
        # Test with relative path
        self.assertEqual(resource_path('file.txt'), os.path.join('/mock/path', 'file.txt'))
    
    @patch('os.environ')
    @patch('os.makedirs')
    def test_user_data_path_env_var(self, mock_makedirs, mock_environ):
        """Test user data path with environment variable."""
        # Setup environment variable
        mock_environ.get.return_value = '/custom/path'
        mock_environ.__contains__.return_value = True
        
        # Test the function
        self.assertEqual(get_user_data_path(), '/custom/path')
        mock_makedirs.assert_called_once_with('/custom/path', exist_ok=True)
    
    @patch('sys._MEIPASS', new='/mock/meipass', create=True)
    @patch('appdirs.user_data_dir')
    @patch('os.makedirs')
    def test_user_data_path_pyinstaller(self, mock_makedirs, mock_appdirs):
        """Test get_user_data_path in PyInstaller environment."""
        # Configure mock
        mock_appdirs.return_value = '/user/appdata'
        
        # Setup environment
        with patch('os.environ', {}) as mock_env:
            # Test the function
            self.assertEqual(get_user_data_path(), '/user/appdata')
            mock_makedirs.assert_called_once_with('/user/appdata', exist_ok=True)
            mock_appdirs.assert_called_once_with('Transcribrr', 'John Miller')

if __name__ == '__main__':
    unittest.main()