#!/usr/bin/env python3
"""Test for SpinnerManager and FeedbackManager without GUI."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path to find modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class TestSpinnerFunctionality(unittest.TestCase):
    """Test the SpinnerManager and FeedbackManager functionality."""
    
    @patch('app.ui_utils.QMovie')
    @patch('app.ui_utils.QWidgetAction')
    @patch('app.ui_utils.QAction')
    @patch('app.ui_utils.QLabel')
    @patch('app.ui_utils.QPushButton')
    def test_spinner_creation(self, mock_button, mock_label, mock_action, mock_widget_action, mock_movie):
        """Test creating and toggling a spinner."""
        from app.ui_utils import SpinnerManager, FeedbackManager

        # Set up mocks
        mock_parent = MagicMock()
        mock_toolbar = MagicMock()
        mock_movie.return_value.isValid.return_value = True
        
        # Create spinner manager
        spinner_manager = SpinnerManager(mock_parent)
        
        # Create spinner
        spinner_manager.create_spinner(
            name='test_spinner',
            toolbar=mock_toolbar,
            action_icon='./icons/test.svg',
            action_tooltip='Test Spinner',
            callback=lambda: None
        )
        
        # Check spinner was created
        self.assertIn('test_spinner', spinner_manager.spinners)
        
        # Test toggling spinner
        result = spinner_manager.toggle_spinner('test_spinner')
        self.assertTrue(result)
        self.assertTrue(spinner_manager.is_active('test_spinner'))
        
        # Test toggling again to stop
        result = spinner_manager.toggle_spinner('test_spinner')
        self.assertFalse(result)
        self.assertFalse(spinner_manager.is_active('test_spinner'))

    @patch('app.ui_utils.QMovie')
    @patch('app.ui_utils.QWidgetAction')
    @patch('app.ui_utils.QAction')
    @patch('app.ui_utils.QLabel')
    @patch('app.ui_utils.QPushButton')    
    def test_feedback_manager(self, mock_button, mock_label, mock_action, mock_widget_action, mock_movie):
        """Test FeedbackManager integration with SpinnerManager."""
        from app.ui_utils import SpinnerManager, FeedbackManager
        
        # Set up mocks
        mock_parent = MagicMock()
        mock_parent.spinner_manager = None
        mock_toolbar = MagicMock()
        mock_movie.return_value.isValid.return_value = True
        
        # Create spinner manager
        spinner_manager = SpinnerManager(mock_parent)
        mock_parent.spinner_manager = spinner_manager
        
        # Create spinner
        spinner_manager.create_spinner(
            name='test_spinner',
            toolbar=mock_toolbar,
            action_icon='./icons/test.svg',
            action_tooltip='Test Spinner',
            callback=lambda: None
        )
        
        # Create feedback manager
        feedback_manager = FeedbackManager(mock_parent)
        
        # Test starting spinner
        result = feedback_manager.start_spinner('test_spinner')
        self.assertTrue(result)
        self.assertTrue(spinner_manager.is_active('test_spinner'))
        
        # Test stopping spinner
        result = feedback_manager.stop_spinner('test_spinner')
        self.assertTrue(result)
        self.assertFalse(spinner_manager.is_active('test_spinner'))
        
        # Test non-existent spinner
        result = feedback_manager.start_spinner('nonexistent')
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()