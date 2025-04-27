# app/tests/test_spinner_no_gui.py
#!/usr/bin/env python3
"""Test for SpinnerManager and FeedbackManager without GUI."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path to find modules
# Ensure this path adjustment is correct for your structure
if os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")) not in sys.path:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


class TestSpinnerFunctionality(unittest.TestCase):
    """Test the SpinnerManager and FeedbackManager functionality."""

    @patch('app.ui_utils_legacy.QMovie')
    @patch('app.ui_utils_legacy.QWidgetAction')
    @patch('app.ui_utils_legacy.QAction')
    @patch('app.ui_utils_legacy.QLabel')
    @patch('app.ui_utils_legacy.QPushButton')
    def test_spinner_creation(self, mock_button, mock_label, mock_action, mock_widget_action, mock_movie):
        """Test creating and toggling a spinner."""
        from app.ui_utils import SpinnerManager

        # Set up mocks
        mock_parent = MagicMock()
        mock_toolbar = MagicMock()
        mock_movie.return_value.isValid.return_value = True

        # Create spinner manager
        spinner_manager = SpinnerManager(mock_parent)

        # --- FIX: Use None for icon path as it's not needed with mocks ---
        spinner_manager.create_spinner(
            name='test_spinner',
            toolbar=mock_toolbar,
            action_icon=None,  # Changed from './icons/test.svg'
            action_tooltip='Test Spinner',
            callback=lambda: None
        )
        # --- End FIX ---

        # Check spinner was created
        self.assertIn('test_spinner', spinner_manager.spinners)

        # Test toggling spinner
        result = spinner_manager.toggle_spinner('test_spinner')
        self.assertTrue(result)
        self.assertTrue(spinner_manager.is_active('test_spinner'))

        # Test toggling again to stop
        result = spinner_manager.toggle_spinner('test_spinner')
        self.assertFalse(result)  # Should return False indicating it's now inactive
        self.assertFalse(spinner_manager.is_active('test_spinner'))

    @patch('app.ui_utils_legacy.QMovie')
    @patch('app.ui_utils_legacy.QWidgetAction')
    @patch('app.ui_utils_legacy.QAction')
    @patch('app.ui_utils_legacy.QLabel')
    @patch('app.ui_utils_legacy.QPushButton')
    def test_feedback_manager(self, mock_button, mock_label, mock_action, mock_widget_action, mock_movie):
        """Test FeedbackManager integration with SpinnerManager."""
        from app.ui_utils import FeedbackManager

        # Set up mocks
        mock_parent = MagicMock()
        mock_parent.spinner_manager = None  # Ensure FeedbackManager creates its own
        mock_toolbar = MagicMock()
        mock_movie.return_value.isValid.return_value = True

        # Create feedback manager (which should create a SpinnerManager)
        feedback_manager = FeedbackManager(mock_parent)
        spinner_manager = feedback_manager.spinner_manager  # Get the created manager

        # --- FIX: Use None for icon path ---
        spinner_manager.create_spinner(
            name='test_spinner',
            toolbar=mock_toolbar,
            action_icon=None,  # Changed from './icons/test.svg'
            action_tooltip='Test Spinner',
            callback=lambda: None
        )
        # --- End FIX ---

        # Test starting spinner via feedback manager
        result = feedback_manager.start_spinner('test_spinner')
        self.assertTrue(result)  # Should return True indicating it's now active
        self.assertTrue(spinner_manager.is_active('test_spinner'))

        # Test stopping spinner via feedback manager
        result = feedback_manager.stop_spinner('test_spinner')
        self.assertTrue(result)  # Should return True indicating it stopped successfully
        self.assertFalse(spinner_manager.is_active('test_spinner'))

        # Test non-existent spinner
        result = feedback_manager.start_spinner('nonexistent')
        self.assertFalse(result)  # Should return False as spinner doesn't exist


if __name__ == '__main__':
    unittest.main()
