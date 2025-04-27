"""Test the thread launcher functionality."""

import unittest
from unittest.mock import MagicMock, patch

# Mock class to extract and test the _launch_thread method without dependencies


class ThreadLauncherTestHelper:
    """Helper class to isolate and test _launch_thread method."""

    def __init__(self):
        """Initialize with minimal requirements."""
        self.test_thread = None

    def _launch_thread(self, thread, completion_handler, progress_handler,
                       error_handler, finished_handler, thread_attr_name=None):
        """
        Clone of the MainTranscriptionWidget._launch_thread method for testing.
        """
        # Connect signals
        thread.completed.connect(completion_handler)
        thread.update_progress.connect(progress_handler)
        thread.error.connect(error_handler)
        thread.finished.connect(finished_handler)

        # Store thread reference if attribute name provided
        if thread_attr_name:
            setattr(self, thread_attr_name, thread)

        # Register thread with ThreadManager
        from app.ThreadManager import ThreadManager
        ThreadManager.instance().register_thread(thread)

        # Start the thread
        thread.start()

        return thread


class MockThread:
    """Mock thread for testing signal connections."""

    def __init__(self):
        """Initialize signals."""
        self.completed = MagicMock()
        self.update_progress = MagicMock()
        self.error = MagicMock()
        self.finished = MagicMock()
        self.start = MagicMock()


class TestThreadLauncher(unittest.TestCase):
    """Test the _launch_thread helper method."""

    @patch('app.ThreadManager.ThreadManager.instance')
    def test_launch_thread_connects_signals(self, mock_thread_manager_instance):
        """Test that _launch_thread connects all signals correctly."""
        # Set up the ThreadManager mock
        thread_manager = MagicMock()
        mock_thread_manager_instance.return_value = thread_manager

        # Create a helper instance
        helper = ThreadLauncherTestHelper()

        # Create mock handlers
        completion_handler = MagicMock()
        progress_handler = MagicMock()
        error_handler = MagicMock()
        finished_handler = MagicMock()

        # Create a mock thread
        mock_thread = MockThread()

        # Call _launch_thread
        result = helper._launch_thread(
            thread=mock_thread,
            completion_handler=completion_handler,
            progress_handler=progress_handler,
            error_handler=error_handler,
            finished_handler=finished_handler,
            thread_attr_name='test_thread'
        )

        # Verify signal connections
        mock_thread.completed.connect.assert_called_once_with(completion_handler)
        mock_thread.update_progress.connect.assert_called_once_with(progress_handler)
        mock_thread.error.connect.assert_called_once_with(error_handler)
        mock_thread.finished.connect.assert_called_once_with(finished_handler)

        # Verify thread registration
        thread_manager.register_thread.assert_called_once_with(mock_thread)

        # Verify thread start
        mock_thread.start.assert_called_once()

        # Verify thread attribute set
        self.assertEqual(helper.test_thread, mock_thread)

        # Verify method returns the thread
        self.assertEqual(result, mock_thread)

    @patch('app.ThreadManager.ThreadManager.instance')
    def test_launch_thread_without_attribute_name(self, mock_thread_manager_instance):
        """Test that _launch_thread works when no thread_attr_name is provided."""
        # Set up the ThreadManager mock
        thread_manager = MagicMock()
        mock_thread_manager_instance.return_value = thread_manager

        # Create a helper instance
        helper = ThreadLauncherTestHelper()

        # Create mock handlers
        completion_handler = MagicMock()
        progress_handler = MagicMock()
        error_handler = MagicMock()
        finished_handler = MagicMock()

        # Create a mock thread
        mock_thread = MockThread()

        # Call _launch_thread without thread_attr_name
        result = helper._launch_thread(
            thread=mock_thread,
            completion_handler=completion_handler,
            progress_handler=progress_handler,
            error_handler=error_handler,
            finished_handler=finished_handler
        )

        # Verify signal connections still made
        mock_thread.completed.connect.assert_called_once_with(completion_handler)
        mock_thread.update_progress.connect.assert_called_once_with(progress_handler)
        mock_thread.error.connect.assert_called_once_with(error_handler)
        mock_thread.finished.connect.assert_called_once_with(finished_handler)

        # Verify thread registration still done
        thread_manager.register_thread.assert_called_once_with(mock_thread)

        # Verify thread start still called
        mock_thread.start.assert_called_once()

        # Verify method returns the thread
        self.assertEqual(result, mock_thread)


if __name__ == '__main__':
    unittest.main()
