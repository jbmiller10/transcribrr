import os
import unittest
from app.ui_utils import FeedbackManager


class DummyElement:
    """Dummy UI element with setEnabled/isEnabled methods."""

    def __init__(self, enabled=True):
        self._enabled = enabled
        self.history = []

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, state):
        # Record calls for assertion
        self.history.append(state)
        self._enabled = state


class TestFeedbackManager(unittest.TestCase):
    def setUp(self):
        # Parent widget is unused for unit tests
        self.fm = FeedbackManager(parent_widget=None)
        # Create dummy UI elements
        self.elem1 = DummyElement(enabled=True)
        self.elem2 = DummyElement(enabled=False)
        self.elements = [self.elem1, self.elem2]

    def test_set_ui_busy_and_restore(self):
        # Disable elements via busy state
        self.fm.set_ui_busy(True, self.elements)
        self.assertFalse(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

        # Starting and finishing an operation should ultimately restore
        self.fm.start_operation("op")
        self.fm.finish_operation("op")
        self.assertTrue(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

    def test_start_and_finish_operation_restores(self):
        # Disable UI first
        self.fm.set_ui_busy(True, self.elements)
        # Start two operations
        self.fm.start_operation("op1")
        self.fm.start_operation("op2")

        # Finish first operation: UI should remain disabled
        self.fm.finish_operation("op1")
        self.assertFalse(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

        # Finish second operation: UI should be restored to original states
        self.fm.finish_operation("op2")
        self.assertTrue(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

    def test_concurrent_overlap(self):
        # Disable UI
        self.fm.set_ui_busy(True, self.elements)
        # Start and finish in interleaved order
        self.fm.start_operation("A")
        self.fm.start_operation("B")
        # Finish B first
        self.fm.finish_operation("B")
        # UI still disabled
        self.assertFalse(self.elem1.isEnabled())
        # Finish A
        self.fm.finish_operation("A")
        # Now UI enabled per original state
        self.assertTrue(self.elem1.isEnabled())
        
    def test_stop_all_feedback(self):
        # Disable and start operations
        self.fm.set_ui_busy(True, self.elements)
        self.fm.start_operation("X")
        self.fm.start_operation("Y")
        # Call stop_all_feedback
        self.fm.stop_all_feedback()
        # Elements restored to original states
        self.assertTrue(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

    def test_finish_operation_idempotent(self):
        # Finish without starting should not error
        self.fm.finish_operation("nonexistent")
        # Should not raise and state stays consistent
        self.fm.stop_all_feedback()

    def test_progress_dialog_headless(self):
        # If PyQt6 is present, ensure a QApplication exists for dialog creation
        app = None
        try:  # Create a minimal app if needed; otherwise rely on headless shims
            from PyQt6.QtWidgets import QApplication  # type: ignore

            app = QApplication.instance() or QApplication([])
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        except Exception:
            pass

        try:
            dlg = self.fm.start_progress("download", "Downloading", "...")
            self.assertIsNotNone(dlg)
            self.fm.update_progress("download", 50, "Half")
            # Finish should not raise and should allow closing repeatedly
            self.fm.finish_progress("download", "Done", auto_close=False)
            self.fm.close_progress("download")
        finally:
            if app is not None:
                app.quit()



if __name__ == "__main__":
    unittest.main()
