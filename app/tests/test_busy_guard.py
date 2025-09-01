"""Behavior-focused tests for BusyGuard context manager."""

import unittest
from unittest.mock import patch

from app.ui_utils.busy_guard import BusyGuard
from app.tests.helpers.busy_guard_helpers import (
    DEFAULT_PROGRESS_MAX,
    DEFAULT_STATUS_TIMEOUT_MS,
    TEST_OPERATION_NAME,
    TEST_SPINNER_NAME,
    SpyFeedback,
    CallCountingFeedback,
    StatefulFeedback,
    ProgressState,
)


class TestBusyGuardUIStateManagement(unittest.TestCase):
    def test_disables_ui_elements_during_operation(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        dummy_elem = object()
        with BusyGuard(
            feedback,
            TEST_OPERATION_NAME,
            ui_elements=[dummy_elem],
            spinner=TEST_SPINNER_NAME,
        ):
            self.assertTrue(feedback.ui_busy)
        # After exit, UI busy cleared via operation finish
        self.assertFalse(feedback.ui_busy)

    def test_handles_empty_ui_element_list(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with BusyGuard(feedback, TEST_OPERATION_NAME, ui_elements=[], spinner=TEST_SPINNER_NAME):
            # Even without explicit elements, operation start sets busy state
            self.assertTrue(feedback.ui_busy)
        # After exit, busy state is restored
        self.assertFalse(feedback.ui_busy)

    def test_ui_state_restored_after_exception(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with self.assertRaises(ValueError):
            with BusyGuard(feedback, TEST_OPERATION_NAME, ui_elements=[object()], spinner=TEST_SPINNER_NAME):
                self.assertTrue(feedback.ui_busy)
                raise ValueError("boom")
        self.assertFalse(feedback.ui_busy)


class TestBusyGuardVisualFeedback(unittest.TestCase):
    def test_spinner_shows_during_operation(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with BusyGuard(feedback, TEST_OPERATION_NAME, spinner=TEST_SPINNER_NAME):
            self.assertTrue(feedback.is_spinner_active(TEST_SPINNER_NAME))
        self.assertFalse(feedback.is_spinner_active(TEST_SPINNER_NAME))

    def test_handles_missing_spinner_gracefully(self):
        feedback = StatefulFeedback(valid_spinners=set())  # No valid spinner registered
        with patch("app.ui_utils.busy_guard.logger") as mock_logger:
            with BusyGuard(feedback, TEST_OPERATION_NAME, spinner=TEST_SPINNER_NAME):
                # Operation continues even if spinner missing
                self.assertFalse(feedback.is_spinner_active(TEST_SPINNER_NAME))
            # Warning logged
            self.assertTrue(mock_logger.warning.called)

    def test_progress_dialog_shows_updates(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with BusyGuard(
            feedback,
            TEST_OPERATION_NAME,
            progress=True,
            progress_title="Processing",
            progress_message="Starting...",
        ) as guard:
            guard.update_progress(50, "Halfway done")

        st = feedback.get_progress_state(guard.operation_id)
        # It may be closed automatically; ensure the final values were set
        self.assertIsNotNone(st)
        self.assertEqual(st.value, 50)
        # After successful completion, BusyGuard sets a final success message
        self.assertIn("completed successfully", st.message)

    def test_indeterminate_progress(self):
        feedback = StatefulFeedback()
        with BusyGuard(
            feedback,
            TEST_OPERATION_NAME,
            progress=True,
            progress_message="Working...",
            progress_maximum=0,
        ) as guard:
            pass
        st = feedback.get_progress_state(guard.operation_id)
        self.assertIsNotNone(st)
        self.assertEqual(st.maximum, 0)

    def test_status_message_display(self):
        feedback = StatefulFeedback()
        with BusyGuard(feedback, TEST_OPERATION_NAME, status_message="Starting test..."):
            pass
        self.assertTrue(any(sm.message == "Starting test..." for sm in feedback.status_messages))

    def test_update_progress_noop_when_not_started(self):
        feedback = CallCountingFeedback()
        with BusyGuard(feedback, TEST_OPERATION_NAME, progress=False) as guard:
            guard.update_progress(10, "msg")
        # update_progress should not be called on feedback if progress not started
        self.assertFalse(feedback.was_called("update_progress"))


class TestBusyGuardCancellation(unittest.TestCase):
    def test_cancel_invokes_callback(self):
        feedback = StatefulFeedback()
        calls = {"count": 0}

        def cb():
            calls["count"] += 1

        with BusyGuard(feedback, TEST_OPERATION_NAME, progress=True, cancel_callback=cb) as guard:
            guard.cancel()
        self.assertEqual(calls["count"], 1)

    def test_cancel_without_callback(self):
        feedback = StatefulFeedback()
        with BusyGuard(feedback, TEST_OPERATION_NAME, progress=True) as guard:
            guard.cancel()
        # No exceptions and a cancellation status message shown
        self.assertTrue(any("canceled" in sm.message.lower() for sm in feedback.status_messages))

    def test_cancel_idempotency(self):
        feedback = StatefulFeedback()
        calls = {"count": 0}

        def cb():
            calls["count"] += 1

        with BusyGuard(feedback, TEST_OPERATION_NAME, progress=True, cancel_callback=cb) as guard:
            guard.cancel()
            guard.cancel()  # Should be safe and not call callback again
        self.assertEqual(calls["count"], 1)

    def test_cancel_callback_error_handling(self):
        feedback = StatefulFeedback()

        def bad_cb():
            raise RuntimeError("boom")

        with BusyGuard(feedback, TEST_OPERATION_NAME, progress=True, cancel_callback=bad_cb) as guard:
            with patch("app.ui_utils.busy_guard.logger") as mock_logger:
                guard.cancel()
                self.assertTrue(mock_logger.error.called)

    def test_progress_cancelable_flag_respected(self):
        fb = SpyFeedback()
        with BusyGuard(
            fb,
            TEST_OPERATION_NAME,
            progress=True,
            progress_title="T",
            progress_message="M",
            progress_cancelable=False,
        ):
            pass
        # Find the recorded start_progress call and assert cancelable False
        start_calls = [c for (name, c) in fb.calls if name == "start_progress"]
        self.assertTrue(start_calls and start_calls[0]["cancelable"] is False)


class TestBusyGuardErrorHandling(unittest.TestCase):
    def test_exception_triggers_cleanup(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with self.assertRaises(ValueError):
            with BusyGuard(
                feedback,
                TEST_OPERATION_NAME,
                spinner=TEST_SPINNER_NAME,
                progress=True,
            ):
                raise ValueError("err")
        # Spinner closed and progress closed (final state reflects no active spinner)
        self.assertFalse(feedback.is_spinner_active(TEST_SPINNER_NAME))
        # Progress state should be closed
        # We can't know the operation id after with, so assert no open states exist
        self.assertTrue(all(not st.is_open for st in feedback.progress_states.values()))

    def test_partial_setup_failure_cleanup(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        # Simulate failure during start_progress via monkeypatch on feedback instance
        def raising_start_progress(*args, **kwargs):
            raise RuntimeError("fail setup")

        with patch.object(feedback, "start_progress", side_effect=raising_start_progress):
            with self.assertRaises(RuntimeError):
                with BusyGuard(
                    feedback,
                    TEST_OPERATION_NAME,
                    spinner=TEST_SPINNER_NAME,
                    progress=True,
                ):
                    pass
        # Spinner should not remain active
        self.assertFalse(feedback.is_spinner_active(TEST_SPINNER_NAME))

    def test_cleanup_error_doesnt_mask_exception(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})

        def bad_stop(spinner_name: str) -> bool:  # noqa: ARG001
            raise RuntimeError("stop failed")

        with patch.object(feedback, "stop_spinner", side_effect=bad_stop):
            with self.assertRaises(ValueError):
                with BusyGuard(feedback, TEST_OPERATION_NAME, spinner=TEST_SPINNER_NAME):
                    raise ValueError("boom")

    def test_feedback_manager_errors_handled(self):
        class NoisyFeedback(StatefulFeedback):
            def show_status(self, *a, **k):  # type: ignore[override]
                raise RuntimeError("status broken")

        feedback = NoisyFeedback()
        # Guard should log and continue setup/cleanup best-effort
        with patch("app.ui_utils.busy_guard.logger") as mock_logger:
            with BusyGuard(feedback, TEST_OPERATION_NAME):
                pass
            self.assertTrue(mock_logger.error.called or mock_logger.debug.called)


class TestBusyGuardResultCapture(unittest.TestCase):
    def test_result_storage_and_retrieval(self):
        feedback = StatefulFeedback()
        with BusyGuard(feedback, TEST_OPERATION_NAME) as guard:
            val = guard.set_result({"a": 1})
            self.assertEqual(val, {"a": 1})
        self.assertEqual(guard.result, {"a": 1})

    def test_result_none_by_default(self):
        feedback = StatefulFeedback()
        with BusyGuard(feedback, TEST_OPERATION_NAME) as guard:
            pass
        self.assertIsNone(guard.result)

    def test_result_survives_exception(self):
        feedback = StatefulFeedback()
        with self.assertRaises(ValueError):
            with BusyGuard(feedback, TEST_OPERATION_NAME) as guard:
                guard.set_result(123)
                raise ValueError("boom")
        self.assertEqual(guard.result, 123)


class TestBusyGuardOperationTrackingAndIds(unittest.TestCase):
    def test_operation_id_format_uses_uuid_and_name(self):
        feedback = StatefulFeedback()
        with patch("uuid.uuid4") as m:
            class _U:
                hex = "deadbeefcafebabe"
            m.return_value = _U()
            g = BusyGuard(feedback, "My Operation")
            self.assertTrue(g.operation_id.startswith("my_operation_"))
            self.assertTrue(g.operation_id.endswith("deadbeef"))

    def test_keyboardinterrupt_cleanup_and_propagation(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with self.assertRaises(KeyboardInterrupt):
            with BusyGuard(feedback, TEST_OPERATION_NAME, spinner=TEST_SPINNER_NAME):
                raise KeyboardInterrupt
        self.assertFalse(feedback.is_spinner_active(TEST_SPINNER_NAME))

    def test_systemexit_cleanup_and_propagation(self):
        feedback = StatefulFeedback(valid_spinners={TEST_SPINNER_NAME})
        with self.assertRaises(SystemExit):
            with BusyGuard(feedback, TEST_OPERATION_NAME, spinner=TEST_SPINNER_NAME):
                raise SystemExit
        self.assertFalse(feedback.is_spinner_active(TEST_SPINNER_NAME))


if __name__ == "__main__":
    unittest.main()
