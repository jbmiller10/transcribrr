"""Tests for BusyGuard context manager."""

import unittest
from unittest.mock import Mock, patch, MagicMock, call

from app.ui_utils.busy_guard import BusyGuard


class TestBusyGuard(unittest.TestCase):
    """Test BusyGuard context manager functionality."""

    def setUp(self):
        """Set up common test fixtures."""
        # Create mock feedback manager
        self.feedback_manager = Mock()
        self.feedback_manager.start_spinner.return_value = True

        # Create mock UI elements
        self.button1 = Mock()
        self.button2 = Mock()

        # Default cancel callback for testing
        self.cancel_called = False

        def cancel_callback():
            self.cancel_called = True

        self.cancel_callback = cancel_callback

    def test_basic_usage(self):
        """Test basic usage with spinner and UI elements."""
        with BusyGuard(
            self.feedback_manager,
            "Test Operation",
            ui_elements=[self.button1, self.button2],
            spinner="test_spinner",
        ):
            # Verify setup actions were performed
            self.feedback_manager.set_ui_busy.assert_called_once_with(
                True, [self.button1, self.button2]
            )
            self.feedback_manager.start_spinner.assert_called_once_with("test_spinner")

        # Verify cleanup actions after context
        self.feedback_manager.stop_spinner.assert_called_once_with("test_spinner")

    def test_progress_dialog(self):
        """Test with progress dialog."""
        with BusyGuard(
            self.feedback_manager,
            "Test Progress",
            progress=True,
            progress_title="Processing",
            progress_message="Starting...",
            progress_maximum=100,
            progress_cancelable=True,
            cancel_callback=self.cancel_callback,
        ) as guard:
            # Verify progress dialog was created
            self.feedback_manager.start_progress.assert_called_once()

            # Test progress update
            guard.update_progress(50, "Halfway done")
            self.feedback_manager.update_progress.assert_called_once()

        # Verify finishing actions
        self.feedback_manager.finish_progress.assert_called_once()

    def test_exception_handling(self):
        """Test proper cleanup when exception occurs in context."""
        try:
            with BusyGuard(
                self.feedback_manager,
                "Test Exception",
                spinner="test_spinner",
                progress=True,
            ):
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected exception

        # Verify cleanup still occurred
        self.feedback_manager.stop_spinner.assert_called_once_with("test_spinner")
        self.feedback_manager.close_progress.assert_called_once()

    def test_cancel_callback(self):
        """Test cancel callback is called."""
        guard = BusyGuard(
            self.feedback_manager,
            "Test Cancel",
            progress=True,
            cancel_callback=self.cancel_callback,
        )

        with guard:
            guard.cancel()

        # Verify cancel callback was called
        self.assertTrue(self.cancel_called)
        self.feedback_manager.close_progress.assert_called_once()

    def test_result_capture(self):
        """Test result capture functionality."""
        with BusyGuard(self.feedback_manager, "Test Result") as guard:
            result = guard.set_result("success")

        # Verify result is stored and returned
        self.assertEqual(result, "success")
        self.assertEqual(guard.result, "success")

    def test_multiple_feedback_types(self):
        """Test using all feedback types together."""
        with BusyGuard(
            self.feedback_manager,
            "Complete Test",
            ui_elements=[self.button1],
            spinner="test_spinner",
            progress=True,
            status_message="Working...",
        ):
            # Verify all feedback types were started
            self.feedback_manager.set_ui_busy.assert_called_once()
            self.feedback_manager.start_spinner.assert_called_once()
            self.feedback_manager.start_progress.assert_called_once()
            self.feedback_manager.show_status.assert_called_once_with("Working...")

    def test_no_spinner_found(self):
        """Test graceful handling when spinner not found."""
        # Set up feedback manager to fail spinner start
        self.feedback_manager.start_spinner.return_value = False

        with BusyGuard(
            self.feedback_manager, "Missing Spinner Test", spinner="nonexistent"
        ):
            pass

        # Verify stop_spinner isn't called when start failed
        self.feedback_manager.stop_spinner.assert_not_called()

    def test_nested_guards(self):
        """Test nested BusyGuard instances work properly."""
        with BusyGuard(
            self.feedback_manager, "Outer Operation", spinner="outer_spinner"
        ):
            # Verify outer guard setup
            self.feedback_manager.start_spinner.assert_called_with("outer_spinner")

            with BusyGuard(
                self.feedback_manager, "Inner Operation", spinner="inner_spinner"
            ):
                # Verify inner guard setup
                self.feedback_manager.start_spinner.assert_called_with("inner_spinner")

            # Verify inner guard cleanup
            self.feedback_manager.stop_spinner.assert_called_with("inner_spinner")

        # Verify outer guard cleanup
        self.feedback_manager.stop_spinner.assert_called_with("outer_spinner")


if __name__ == "__main__":
    unittest.main()
