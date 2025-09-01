"""Tests for BusyGuard context manager."""

import unittest

from app.ui_utils.busy_guard import BusyGuard


class DummyWidget:
    """Simple stand-in for QWidget to test enabled state."""

    def __init__(self):
        self._enabled = True

    def setEnabled(self, value: bool) -> None:
        self._enabled = value

    def isEnabled(self) -> bool:
        return self._enabled


class TestFeedbackManager:
    """Concrete test double implementing the feedback protocol with state tracking."""

    def __init__(self):
        self.busy_elements: set[DummyWidget] = set()
        self.active_spinners: set[str] = set()
        self.progress_dialogs: dict[str, dict] = {}
        self.closed_progress: set[str] = set()
        self.finished_progress: set[str] = set()
        self.status_messages: list[tuple[str, int]] = []
        self.fail_on_stop_spinner: bool = False
        self.nonexistent_spinners: set[str] = {"nonexistent"}

    def set_ui_busy(self, busy: bool, ui_elements: list | None = None) -> None:
        for w in ui_elements or []:
            # Simulate real widget enable/disable
            if isinstance(w, DummyWidget):
                w.setEnabled(not busy)
        if busy:
            self.busy_elements.update(ui_elements or [])
        else:
            self.busy_elements.difference_update(ui_elements or [])

    def start_spinner(self, spinner_name: str) -> bool:
        if spinner_name in self.nonexistent_spinners:
            return False
        self.active_spinners.add(spinner_name)
        return True

    def stop_spinner(self, spinner_name: str) -> bool:
        if self.fail_on_stop_spinner:
            raise RuntimeError("stop_spinner failure")
        self.active_spinners.discard(spinner_name)
        # Re-enable any busy UI elements when spinner stops
        for w in list(self.busy_elements):
            if isinstance(w, DummyWidget):
                w.setEnabled(True)
        self.busy_elements.clear()
        return True

    def start_progress(
        self,
        operation_id: str,
        title: str,
        message: str,
        maximum: int = 100,
        cancelable: bool = True,
        cancel_callback=None,
    ) -> None:
        self.progress_dialogs[operation_id] = {
            "title": title,
            "message": message,
            "maximum": maximum,
            "cancelable": cancelable,
            "value": 0,
            "callback": cancel_callback,
        }

    def update_progress(self, operation_id: str, value: int, message: str | None = None) -> None:
        if operation_id in self.progress_dialogs:
            self.progress_dialogs[operation_id]["value"] = value
            if message is not None:
                self.progress_dialogs[operation_id]["message"] = message

    def finish_progress(self, operation_id: str, message: str | None = None, auto_close: bool = True) -> None:
        self.finished_progress.add(operation_id)
        self.progress_dialogs.pop(operation_id, None)
        # Re-enable UI on successful finish
        for w in list(self.busy_elements):
            if isinstance(w, DummyWidget):
                w.setEnabled(True)
        self.busy_elements.clear()

    def close_progress(self, operation_id: str) -> None:
        self.closed_progress.add(operation_id)
        self.progress_dialogs.pop(operation_id, None)
        # Re-enable UI on close
        for w in list(self.busy_elements):
            if isinstance(w, DummyWidget):
                w.setEnabled(True)
        self.busy_elements.clear()

    def show_status(self, message: str, timeout: int = 3000) -> None:
        self.status_messages.append((message, timeout))


class TestBusyGuard(unittest.TestCase):
    """Tests BusyGuard behavior using a concrete feedback stub."""

    def setUp(self):
        self.feedback_manager = TestFeedbackManager()
        self.button1 = DummyWidget()
        self.button2 = DummyWidget()
        self.cancel_called = False

        def cancel_callback():
            self.cancel_called = True

        self.cancel_callback = cancel_callback

    def test_basic_usage(self):
        """Disables UI and starts/stops spinner around the block."""
        with BusyGuard(
            self.feedback_manager,
            "Test Operation",
            ui_elements=[self.button1, self.button2],
            spinner="test_spinner",
        ):
            # During guard: widgets disabled, spinner active
            self.assertFalse(self.button1.isEnabled())
            self.assertFalse(self.button2.isEnabled())
            self.assertIn("test_spinner", self.feedback_manager.active_spinners)
        # After guard: widgets enabled, spinner stopped
        self.assertTrue(self.button1.isEnabled())
        self.assertTrue(self.button2.isEnabled())
        self.assertNotIn("test_spinner", self.feedback_manager.active_spinners)

    def test_progress_dialog(self):
        """Shows progress, updates value, and finishes on success."""
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
            # There should be exactly one progress dialog
            self.assertEqual(len(self.feedback_manager.progress_dialogs), 1)
            op_id = next(iter(self.feedback_manager.progress_dialogs.keys()))
            # Update progress
            guard.update_progress(50, "Halfway done")
            self.assertEqual(self.feedback_manager.progress_dialogs[op_id]["value"], 50)
            self.assertEqual(self.feedback_manager.progress_dialogs[op_id]["message"], "Halfway done")
        # Finished: dialog removed, finish recorded
        self.assertEqual(len(self.feedback_manager.progress_dialogs), 0)
        self.assertEqual(len(self.feedback_manager.finished_progress), 1)

    def test_exception_handling(self):
        """On exception, closes progress and stops spinner without masking error."""
        with self.assertRaises(ValueError):
            with BusyGuard(
                self.feedback_manager,
                "Test Exception",
                spinner="test_spinner",
                progress=True,
            ):
                raise ValueError("Test exception")
        # Spinner stopped and progress closed
        self.assertNotIn("test_spinner", self.feedback_manager.active_spinners)
        self.assertEqual(len(self.feedback_manager.closed_progress), 1)

    def test_cancel_callback(self):
        """Calling cancel triggers user callback and closes progress."""
        guard = BusyGuard(
            self.feedback_manager,
            "Test Cancel",
            progress=True,
            cancel_callback=self.cancel_callback,
        )
        with guard:
            guard.cancel()
        self.assertTrue(self.cancel_called)
        self.assertEqual(len(self.feedback_manager.closed_progress), 1)
        self.assertIn(("test cancel canceled", 3000), [(m.lower(), t) for m, t in self.feedback_manager.status_messages])

    def test_result_capture(self):
        """Stores operation result via set_result."""
        with BusyGuard(self.feedback_manager, "Test Result") as guard:
            result = guard.set_result("success")
        self.assertEqual(result, "success")
        self.assertEqual(guard.result, "success")

    def test_multiple_feedback_types(self):
        """Combines UI busy, spinner, progress, and status message."""
        with BusyGuard(
            self.feedback_manager,
            "Complete Test",
            ui_elements=[self.button1],
            spinner="test_spinner",
            progress=True,
            status_message="Working...",
        ):
            self.assertFalse(self.button1.isEnabled())
            self.assertIn("test_spinner", self.feedback_manager.active_spinners)
            self.assertEqual(len(self.feedback_manager.progress_dialogs), 1)
            self.assertIn(("Working...", 3000), self.feedback_manager.status_messages)

    def test_no_spinner_found(self):
        """If start_spinner returns False, do not call stop on exit."""
        with BusyGuard(
            self.feedback_manager, "Missing Spinner Test", spinner="nonexistent"
        ):
            pass
        self.assertNotIn("nonexistent", self.feedback_manager.active_spinners)
        # No errors and nothing to stop

    def test_nested_guards(self):
        """Nested guards manage independent spinner states."""
        with BusyGuard(
            self.feedback_manager, "Outer Operation", spinner="outer_spinner"
        ):
            self.assertIn("outer_spinner", self.feedback_manager.active_spinners)
            with BusyGuard(
                self.feedback_manager, "Inner Operation", spinner="inner_spinner"
            ):
                self.assertIn("inner_spinner", self.feedback_manager.active_spinners)
            self.assertNotIn("inner_spinner", self.feedback_manager.active_spinners)
        self.assertNotIn("outer_spinner", self.feedback_manager.active_spinners)

    def test_cleanup_exception_does_not_mask_original(self):
        """Cleanup errors (e.g., stop_spinner) don't mask original exception."""
        self.feedback_manager.fail_on_stop_spinner = True
        with self.assertRaises(ValueError) as cm:
            with BusyGuard(self.feedback_manager, "Test", spinner="test_spinner"):
                self.assertIn("test_spinner", self.feedback_manager.active_spinners)
                raise ValueError("Original error")
        self.assertEqual(str(cm.exception), "Original error")


if __name__ == "__main__":
    unittest.main()
