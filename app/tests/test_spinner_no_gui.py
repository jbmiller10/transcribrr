"""Headless tests for SpinnerManager and FeedbackManager (no PyQt6)."""

import unittest

from app.ui_utils import SpinnerManager, FeedbackManager


class TestSpinnerFunctionality(unittest.TestCase):
    def test_spinner_lifecycle(self):
        sm = SpinnerManager(None)
        sm.create_spinner("s1", toolbar=object(), action_icon=None, action_tooltip="t", callback=lambda: None)
        self.assertFalse(sm.is_active("s1"))
        self.assertTrue(sm.toggle_spinner("s1"))
        self.assertTrue(sm.is_active("s1"))
        self.assertFalse(sm.toggle_spinner("s1"))
        self.assertFalse(sm.is_active("s1"))

    def test_nonexistent_spinner_operations(self):
        sm = SpinnerManager(None)
        self.assertFalse(sm.toggle_spinner("missing"))
        self.assertFalse(sm.is_active("missing"))
        # set state on missing is a no-op
        sm.set_spinner_state("missing", True)
        self.assertFalse(sm.is_active("missing"))

    def test_stop_all_spinners(self):
        sm = SpinnerManager(None)
        sm.create_spinner("a", object(), None, "", lambda: None)
        sm.create_spinner("b", object(), None, "", lambda: None)
        sm.toggle_spinner("a")
        sm.toggle_spinner("b")
        self.assertTrue(sm.is_active("a"))
        self.assertTrue(sm.is_active("b"))
        sm.stop_all_spinners()
        self.assertFalse(sm.is_active("a"))
        self.assertFalse(sm.is_active("b"))

    def test_feedback_manager_integration(self):
        fm = FeedbackManager(None)
        fm.spinner_manager.create_spinner("s", object(), None, "", lambda: None)
        self.assertTrue(fm.start_spinner("s"))
        self.assertTrue(fm.spinner_manager.is_active("s"))
        self.assertTrue(fm.stop_spinner("s"))
        self.assertFalse(fm.spinner_manager.is_active("s"))
        self.assertFalse(fm.start_spinner("missing"))


if __name__ == "__main__":
    unittest.main()
