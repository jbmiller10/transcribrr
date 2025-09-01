import unittest
from unittest.mock import Mock, patch

from app.ui_utils import FeedbackManager


class TestFeedbackManagerUIStateManagement(unittest.TestCase):
    """UI element state handling while operations are active."""

    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)
        # Mock UI elements with Qt-like interface
        self.enabled_elem = Mock(spec=["isEnabled", "setEnabled"])
        self.enabled_elem.isEnabled.return_value = True
        self.disabled_elem = Mock(spec=["isEnabled", "setEnabled"])
        self.disabled_elem.isEnabled.return_value = False
        self.elements = [self.enabled_elem, self.disabled_elem]

    def test_disables_all_ui_elements_when_busy_mode_activated(self):
        """
        Given: UI elements with various enabled states
        When: Busy mode is activated
        Then: All elements are disabled regardless of original state
        """
        self.fm.set_ui_busy(True, self.elements)
        self.enabled_elem.setEnabled.assert_called_once_with(False)
        self.disabled_elem.setEnabled.assert_called_once_with(False)

    def test_observable_state_disable_and_restore(self):
        class SimpleElement:
            def __init__(self, enabled: bool):
                self._enabled = enabled

            def isEnabled(self):
                return self._enabled

            def setEnabled(self, v: bool):
                self._enabled = v

        e1 = SimpleElement(True)
        e2 = SimpleElement(False)
        fm = FeedbackManager(parent_widget=None)
        # Activate busy -> both disabled regardless of starting state
        fm.set_ui_busy(True, [e1, e2])
        fm.start_operation("op")
        self.assertFalse(e1.isEnabled())
        self.assertFalse(e2.isEnabled())
        # Finish -> restore original states
        fm.finish_operation("op")
        self.assertTrue(e1.isEnabled())
        self.assertFalse(e2.isEnabled())

    def test_restores_original_ui_state_when_all_operations_complete(self):
        """
        Given: UI elements disabled by busy mode
        When: All active operations complete
        Then: Elements return to original enabled/disabled states
        """
        self.fm.set_ui_busy(True, self.elements)
        self.fm.start_operation("op")
        self.fm.finish_operation("op")
        # Check last calls restore original states
        self.assertEqual(self.enabled_elem.setEnabled.call_args_list[-1], ((True,),))
        self.assertEqual(self.disabled_elem.setEnabled.call_args_list[-1], ((False,),))

    def test_preserves_disabled_elements_original_state(self):
        self.fm.set_ui_busy(True, [self.disabled_elem])
        self.fm.start_operation("x")
        self.fm.finish_operation("x")
        self.assertEqual(self.disabled_elem.setEnabled.call_args_list[-1], ((False,),))


class TestFeedbackManagerOperationTracking(unittest.TestCase):
    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)
        self.e1 = Mock(spec=["isEnabled", "setEnabled"]) ; self.e1.isEnabled.return_value = True
        self.e2 = Mock(spec=["isEnabled", "setEnabled"]) ; self.e2.isEnabled.return_value = True
        self.fm.set_ui_busy(True, [self.e1, self.e2])

    def test_maintains_busy_state_until_all_operations_finish(self):
        self.fm.start_operation("A"); self.fm.start_operation("B")
        self.fm.finish_operation("A")
        # Still busy, no restore yet
        self.assertNotIn(((True,),), [c for c in self.e1.setEnabled.call_args_list])
        self.fm.finish_operation("B")
        self.assertEqual(self.e1.setEnabled.call_args_list[-1], ((True,),))

    def test_ignores_finish_for_non_existent_operations(self):
        """
        Given: An operation that was never started
        When: finish_operation is called for it
        Then: No exception is raised and active operations remain unchanged
        """
        initial_operations = self.fm.active_operations.copy()
        
        # Calling finish on non-existent operation should not raise
        self.fm.finish_operation("not-started")
        
        # Verify active operations unchanged (discard on non-existent key is safe)
        self.assertEqual(self.fm.active_operations, initial_operations)
        
        # Verify stop_all_feedback still works normally
        self.fm.stop_all_feedback()
        self.assertEqual(self.fm.active_operations, set())


class TestFeedbackManagerProgressDialogs(unittest.TestCase):
    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)

    def test_creates_and_updates_progress_dialog(self):
        dlg = self.fm.start_progress("op", "Title", "Start")
        self.assertIsNotNone(dlg)
        # update should not raise even if message is None
        self.fm.update_progress("op", 50, None)
        # finish with auto_close triggers close_progress
        with patch.object(self.fm, "close_progress") as cp:
            self.fm.finish_progress("op", "Done", auto_close=True)
            cp.assert_called_once_with("op")

    def test_manual_close_removes_dialog(self):
        """
        Given: An active progress dialog
        When: close_progress is called
        Then: Dialog is removed from tracking and operation is finished
        """
        # Start a progress dialog
        dlg = self.fm.start_progress("op2", "T", "M")
        self.assertIn("op2", self.fm.progress_dialogs)
        self.assertIn("op2", self.fm.active_operations)
        
        # Close the progress dialog
        self.fm.close_progress("op2")
        
        # Verify dialog removed and operation finished
        self.assertNotIn("op2", self.fm.progress_dialogs)
        self.assertNotIn("op2", self.fm.active_operations)


class TestFeedbackManagerSpinnerIntegration(unittest.TestCase):
    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)
        # Create a headless spinner entry
        self.fm.spinner_manager.create_spinner("spin", None, None, "", None)

    def test_starting_spinner_begins_and_stopping_completes_operation(self):
        started = self.fm.start_spinner("spin")
        self.assertTrue(started)
        self.assertTrue(self.fm.spinner_manager.is_active("spin"))
        stopped = self.fm.stop_spinner("spin")
        self.assertTrue(stopped)
        self.assertFalse(self.fm.spinner_manager.is_active("spin"))

    def test_starting_nonexistent_spinner_returns_false(self):
        self.assertFalse(self.fm.start_spinner("nope"))
        self.assertNotIn("nope", self.fm.active_operations)

    def test_stop_spinner_idempotent_when_inactive(self):
        # Not active yet -> True and no change
        self.assertTrue(self.fm.stop_spinner("spin"))
        self.assertFalse(self.fm.spinner_manager.is_active("spin"))


class TestFeedbackManagerErrorHandling(unittest.TestCase):
    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)

    def test_continues_when_element_lacks_isEnabled(self):
        """
        Given: A UI element without isEnabled method
        When: set_ui_busy is called with this element
        Then: Operation continues, element is disabled, and state defaults to True
        """
        class BadElement:
            def __init__(self):
                self.enabled_state = True  # Track state manually
                
            def setEnabled(self, value):
                self.enabled_state = value
        
        bad_elem = BadElement()
        self.fm.set_ui_busy(True, [bad_elem])
        
        # Element should be disabled despite lacking isEnabled
        self.assertFalse(bad_elem.enabled_state)
        
        # Element should be tracked with default True state
        self.assertIn(bad_elem, self.fm.ui_state)
        self.assertTrue(self.fm.ui_state[bad_elem])
        
        # Restore should set back to default True state
        self.fm.stop_all_feedback()
        self.assertTrue(bad_elem.enabled_state)

    def test_recovers_from_setEnabled_exceptions(self):
        """
        Given: UI element that throws exception on setEnabled
        When: set_ui_busy and stop_all_feedback are called
        Then: Exceptions are caught, state is tracked, and other operations continue
        """
        good = Mock(spec=["isEnabled", "setEnabled"])
        good.isEnabled.return_value = True
        
        bad = Mock(spec=["isEnabled", "setEnabled"])
        bad.isEnabled.return_value = True
        bad.setEnabled.side_effect = RuntimeError("boom")
        
        # Should swallow exceptions and continue with good element
        self.fm.set_ui_busy(True, [bad, good])
        
        # Verify state was tracked for both elements
        self.assertIn(bad, self.fm.ui_state)
        self.assertIn(good, self.fm.ui_state)
        self.assertTrue(self.fm.ui_state[bad])
        self.assertTrue(self.fm.ui_state[good])
        
        # Good element should have been disabled
        good.setEnabled.assert_called_with(False)
        
        # Stop all feedback should attempt restore on both (exception swallowed for bad)
        self.fm.stop_all_feedback()
        
        # Verify cleanup completed despite exception
        self.assertEqual(self.fm.ui_state, {})

    def test_set_ui_busy_none_uses_existing_tracked_elements(self):
        e = Mock(spec=["isEnabled", "setEnabled"]) ; e.isEnabled.return_value = True
        self.fm.set_ui_busy(True, [e])
        # Call again with None should use tracked element and attempt to disable again
        self.fm.set_ui_busy(True, None)
        calls = [c for c in e.setEnabled.call_args_list if c == ((False,),)]
        self.assertGreaterEqual(len(calls), 2)

    def test_set_ui_busy_false_is_noop(self):
        e = Mock(spec=["isEnabled", "setEnabled"]) ; e.isEnabled.return_value = True
        self.fm.set_ui_busy(False, [e])
        e.setEnabled.assert_not_called()

    def test_show_status_accepts_message_and_timeout(self):
        """
        Given: A feedback manager instance
        When: show_status is called with message and timeout
        Then: Method completes without error (no-op in headless mode)
        """
        # In headless mode, show_status is a no-op that returns None
        # This test verifies the method accepts expected parameters without error
        result = self.fm.show_status("Status message")
        self.assertIsNone(result)
        
        result_with_timeout = self.fm.show_status("Another message", timeout=5000)
        self.assertIsNone(result_with_timeout)


class TestFeedbackManagerComprehensiveCleanup(unittest.TestCase):
    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)
        self.e = Mock(spec=["isEnabled", "setEnabled"]) ; self.e.isEnabled.return_value = True
        self.fm.set_ui_busy(True, [self.e])
        # Spinner
        self.fm.spinner_manager.create_spinner("s1", None, None, "", None)
        self.fm.start_spinner("s1")
        # Progress
        self.fm.start_progress("op", "T", "M")

    def test_stop_all_feedback_clears_everything(self):
        self.fm.stop_all_feedback()
        # All cleared and restored
        self.assertEqual(self.fm.active_operations, set())
        self.assertEqual(self.fm.progress_dialogs, {})
        self.assertFalse(self.fm.spinner_manager.is_active("s1"))
        # Last call restores to True
        self.assertEqual(self.e.setEnabled.call_args_list[-1], ((True,),))

    def test_stop_all_feedback_observable_state(self):
        class SimpleElement:
            def __init__(self, enabled: bool):
                self._enabled = enabled

            def isEnabled(self):
                return self._enabled

            def setEnabled(self, v: bool):
                self._enabled = v

        e = SimpleElement(True)
        fm = FeedbackManager(parent_widget=None)
        fm.set_ui_busy(True, [e])
        fm.start_operation("op")
        self.assertFalse(e.isEnabled())
        fm.stop_all_feedback()
        self.assertTrue(e.isEnabled())


class TestFeedbackManagerOperationStartBehavior(unittest.TestCase):
    def setUp(self):
        self.fm = FeedbackManager(parent_widget=None)
        self.e = Mock(spec=["isEnabled", "setEnabled"]) ; self.e.isEnabled.return_value = True
        self.fm.set_ui_busy(True, [self.e])

    def test_first_start_triggers_disable_only_once(self):
        # First start should not add extra disable calls beyond initial set_ui_busy
        before = len([c for c in self.e.setEnabled.call_args_list if c == ((False,),)])
        self.fm.start_operation("op1")
        self.fm.start_operation("op2")
        after = len([c for c in self.e.setEnabled.call_args_list if c == ((False,),)])
        # One additional disable for the first start, none for the second
        self.assertEqual(after, before + 1)

    def test_spinner_toggle_deactivates_and_finishes_operation(self):
        self.fm.spinner_manager.create_spinner("ts", None, None, "", None)
        self.assertTrue(self.fm.start_spinner("ts"))
        self.assertFalse(self.fm.start_spinner("ts"))  # toggles off
        self.assertNotIn("ts", self.fm.active_operations)


if __name__ == "__main__":
    unittest.main()
