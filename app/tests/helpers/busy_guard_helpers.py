"""Test helpers and stubs for BusyGuard tests."""

from __future__ import annotations

from typing import Any, Optional, Dict, Set, List
from dataclasses import dataclass

from app.ui_utils.busy_guard import BusyGuard


# Constants
DEFAULT_STATUS_TIMEOUT_MS = 3000
DEFAULT_PROGRESS_MAX = 100
TEST_OPERATION_NAME = "Test Operation"
TEST_SPINNER_NAME = "test_spinner"


class MinimalFeedback:
    """No-op feedback implementation used as a base for spies and fakes."""

    def set_ui_busy(self, busy: bool, ui_elements: list | None = None) -> None:  # noqa: D401 - test helper
        pass

    def start_spinner(self, spinner_name: str) -> bool:  # noqa: D401 - test helper
        return True

    def stop_spinner(self, spinner_name: str) -> bool:  # noqa: D401 - test helper
        return True

    def start_progress(
        self,
        operation_id: str,
        title: str,
        message: str,
        maximum: int = DEFAULT_PROGRESS_MAX,
        cancelable: bool = True,
        cancel_callback=None,
    ) -> None:  # noqa: D401 - test helper
        pass

    def update_progress(self, operation_id: str, value: int, message: Optional[str] = None) -> None:  # noqa: D401 - test helper
        pass

    def finish_progress(self, operation_id: str, message: Optional[str] = None, auto_close: bool = True) -> None:  # noqa: D401 - test helper
        pass

    def close_progress(self, operation_id: str) -> None:  # noqa: D401 - test helper
        pass

    def show_status(self, message: str, timeout: int = DEFAULT_STATUS_TIMEOUT_MS) -> None:  # noqa: D401 - test helper
        pass


class SpyFeedback(MinimalFeedback):
    """Spy that records method calls and parameters for assertions."""

    def __init__(self):
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _rec(self, name: str, **kwargs: Any) -> None:
        self.calls.append((name, kwargs))

    def set_ui_busy(self, busy: bool, ui_elements: list | None = None) -> None:  # type: ignore[override]
        self._rec("set_ui_busy", busy=busy, ui_elements=ui_elements or [])

    def start_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        self._rec("start_spinner", spinner_name=spinner_name)
        return True

    def stop_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        self._rec("stop_spinner", spinner_name=spinner_name)
        return True

    def start_progress(self, operation_id: str, title: str, message: str, maximum: int = DEFAULT_PROGRESS_MAX, cancelable: bool = True, cancel_callback=None) -> None:  # type: ignore[override]
        self._rec(
            "start_progress",
            operation_id=operation_id,
            title=title,
            message=message,
            maximum=maximum,
            cancelable=cancelable,
            cancel_callback=bool(cancel_callback),
        )

    def update_progress(self, operation_id: str, value: int, message: Optional[str] = None) -> None:  # type: ignore[override]
        self._rec("update_progress", operation_id=operation_id, value=value, message=message)

    def finish_progress(self, operation_id: str, message: Optional[str] = None, auto_close: bool = True) -> None:  # type: ignore[override]
        self._rec("finish_progress", operation_id=operation_id, message=message, auto_close=auto_close)

    def close_progress(self, operation_id: str) -> None:  # type: ignore[override]
        self._rec("close_progress", operation_id=operation_id)

    def show_status(self, message: str, timeout: int = DEFAULT_STATUS_TIMEOUT_MS) -> None:  # type: ignore[override]
        self._rec("show_status", message=message, timeout=timeout)


class FailingSpinnerFeedback(SpyFeedback):
    """Simulates spinner failures and errors to test guard robustness."""

    def start_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        # Record but return False to indicate missing spinner
        self._rec("start_spinner", spinner_name=spinner_name)
        return False

    def stop_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        self._rec("stop_spinner", spinner_name=spinner_name)
        raise RuntimeError("Spinner stop failed")


def create_test_guard(**overrides: Any) -> BusyGuard:
    """Create a BusyGuard with sensible defaults for tests."""
    defaults = {
        "operation_name": TEST_OPERATION_NAME,
        "spinner": TEST_SPINNER_NAME,
        "progress": False,
    }
    defaults.update(overrides)
    fm = overrides.get("feedback_manager") or SpyFeedback()
    return BusyGuard(fm, defaults["operation_name"], spinner=defaults["spinner"], progress=defaults["progress"], ui_elements=overrides.get("ui_elements"), progress_title=overrides.get("progress_title"), progress_message=overrides.get("progress_message"), progress_maximum=overrides.get("progress_maximum", DEFAULT_PROGRESS_MAX), progress_cancelable=overrides.get("progress_cancelable", True), cancel_callback=overrides.get("cancel_callback"), status_message=overrides.get("status_message"))


# New behavior-oriented helpers for BusyGuard tests

@dataclass
class ProgressState:
    is_open: bool
    value: int
    message: str
    maximum: int
    cancelable: bool


@dataclass
class StatusMessage:
    message: str
    timeout: int


class StatefulFeedback(MinimalFeedback):
    """Feedback double that tracks state instead of calls.

    Designed for behavior-focused tests that assert observable outcomes.
    """

    def __init__(self, valid_spinners: Optional[Set[str]] = None):
        self.ui_busy: bool = False
        self._ui_elements: List[Any] = []
        self.active_spinners: Set[str] = set()
        # None => allow all; empty set => allow none
        self.valid_spinners: Optional[Set[str]] = (set(valid_spinners) if valid_spinners is not None else None)
        self.progress_states: Dict[str, ProgressState] = {}
        self.status_messages: List[StatusMessage] = []
        self._active_operations: Set[str] = set()

    # Protocol methods
    def set_ui_busy(self, busy: bool, ui_elements: list | None = None) -> None:  # type: ignore[override]
        # We only track the busy flag and keep the elements for potential checks
        if busy:
            self.ui_busy = True
            if ui_elements:
                self._ui_elements = list(ui_elements)
        else:
            self.ui_busy = False

    def start_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        if self.valid_spinners is not None and spinner_name not in self.valid_spinners:
            return False
        self.active_spinners.add(spinner_name)
        return True

    def stop_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        self.active_spinners.discard(spinner_name)
        return True

    def start_progress(
        self,
        operation_id: str,
        title: str,
        message: str,
        maximum: int = DEFAULT_PROGRESS_MAX,
        cancelable: bool = True,
        cancel_callback=None,  # noqa: ARG002
    ) -> None:  # type: ignore[override]
        self.progress_states[operation_id] = ProgressState(
            is_open=True,
            value=0,
            message=message,
            maximum=maximum,
            cancelable=cancelable,
        )

    def update_progress(self, operation_id: str, value: int, message: Optional[str] = None) -> None:  # type: ignore[override]
        st = self.progress_states.get(operation_id)
        if not st:
            return
        st.value = value
        if message is not None:
            st.message = message

    def finish_progress(self, operation_id: str, message: Optional[str] = None, auto_close: bool = True) -> None:  # type: ignore[override]
        st = self.progress_states.get(operation_id)
        if not st:
            return
        if message is not None:
            st.message = message
        if auto_close:
            self.close_progress(operation_id)

    def close_progress(self, operation_id: str) -> None:  # type: ignore[override]
        st = self.progress_states.get(operation_id)
        if st:
            st.is_open = False

    def show_status(self, message: str, timeout: int = DEFAULT_STATUS_TIMEOUT_MS) -> None:  # type: ignore[override]
        self.status_messages.append(StatusMessage(message=message, timeout=timeout))

    # Convenience methods for assertions
    def is_spinner_active(self, name: str) -> bool:
        return name in self.active_spinners

    def get_progress_state(self, operation_id: str) -> Optional[ProgressState]:
        return self.progress_states.get(operation_id)

    def was_status_shown(self, message: str) -> bool:
        return any(s.message == message for s in self.status_messages)

    # Optional operation tracking to emulate FeedbackManager behavior
    def start_operation(self, operation_id: str) -> None:
        self._active_operations.add(operation_id)
        # entering operation implies we're busy
        self.ui_busy = True

    def finish_operation(self, operation_id: str) -> None:
        self._active_operations.discard(operation_id)
        if not self._active_operations:
            self.ui_busy = False


class CallCountingFeedback(MinimalFeedback):
    """Feedback double that only counts method invocations by name."""

    def __init__(self):
        self.call_counts: Dict[str, int] = {}

    def _inc(self, name: str) -> None:
        self.call_counts[name] = self.call_counts.get(name, 0) + 1

    def get_call_count(self, method_name: str) -> int:
        return self.call_counts.get(method_name, 0)

    def was_called(self, method_name: str) -> bool:
        return self.get_call_count(method_name) > 0

    # Protocol methods just increment counters
    def set_ui_busy(self, busy: bool, ui_elements: list | None = None) -> None:  # type: ignore[override]
        self._inc("set_ui_busy")

    def start_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        self._inc("start_spinner")
        return True

    def stop_spinner(self, spinner_name: str) -> bool:  # type: ignore[override]
        self._inc("stop_spinner")
        return True

    def start_progress(
        self,
        operation_id: str,
        title: str,
        message: str,
        maximum: int = DEFAULT_PROGRESS_MAX,
        cancelable: bool = True,
        cancel_callback=None,
    ) -> None:  # type: ignore[override]
        self._inc("start_progress")

    def update_progress(self, operation_id: str, value: int, message: Optional[str] = None) -> None:  # type: ignore[override]
        self._inc("update_progress")

    def finish_progress(self, operation_id: str, message: Optional[str] = None, auto_close: bool = True) -> None:  # type: ignore[override]
        self._inc("finish_progress")

    def close_progress(self, operation_id: str) -> None:  # type: ignore[override]
        self._inc("close_progress")

    def show_status(self, message: str, timeout: int = DEFAULT_STATUS_TIMEOUT_MS) -> None:  # type: ignore[override]
        self._inc("show_status")
