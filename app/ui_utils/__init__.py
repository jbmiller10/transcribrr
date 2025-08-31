"""UI utilities package.

Contains utility classes and functions for UI-related tasks.

This package is imported by both the GUI application and the test suite. The
test environment may run in headless mode without PyQt6 installed. To keep the
import lightweight and reliable, we guard imports from the legacy Qt-based
module and provide minimal fallbacks when PyQt6 is unavailable. These fallbacks
offer just enough surface for unit tests that do not require actual GUI
behaviour.
"""

from typing import Any, Dict

# Attempt to re-export from the Qt-based legacy utilities. If PyQt6 is not
# available (e.g., headless CI), provide minimal no-op shims for the few names
# referenced by tests.
try:  # pragma: no cover - exercised indirectly by tests
    from app.ui_utils_legacy import (
        SpinnerManager,
        FeedbackManager,
        show_message_box,
        show_error_message,
        safe_error,
        show_info_message,
        show_confirmation_dialog,
        create_progress_dialog,
        show_status_message,
    )
except Exception:  # PyQt6 missing or other import-time errors
    class SpinnerManager:  # type: ignore[no-redef]
        def __init__(self, parent_widget: Any = None):
            self.parent = parent_widget
            self.spinners: Dict[str, Dict[str, Any]] = {}

        def create_spinner(
            self,
            name: str,
            toolbar: Any,  # noqa: ARG002 - not used in headless mode
            action_icon: Any,  # noqa: ARG002 - not used in headless mode
            action_tooltip: str,  # noqa: ARG002 - not used in headless mode
            callback: Any,  # noqa: ARG002 - not used in headless mode
            spinner_icon: str | None = None,  # noqa: ARG002 - not used
        ) -> Any:
            # Minimal headless spinner entry
            self.spinners[name] = {
                "active": False,
            }
            return object()

        def toggle_spinner(self, name: str) -> bool:
            if name not in self.spinners:
                return False
            active = not bool(self.spinners[name].get("active", False))
            self.spinners[name]["active"] = active
            return active

        def set_spinner_state(self, name: str, active: bool) -> None:
            if name in self.spinners:
                self.spinners[name]["active"] = bool(active)

        def is_active(self, name: str) -> bool:
            return bool(self.spinners.get(name, {}).get("active", False))

        def stop_all_spinners(self) -> None:
            for key in list(self.spinners.keys()):
                self.spinners[key]["active"] = False
            return None

    class FeedbackManager:  # type: ignore[no-redef]
        def __init__(self, parent_widget: Any = None):
            self.parent = parent_widget
            self.spinner_manager = SpinnerManager(parent_widget)
            self.progress_dialogs: Dict[str, Any] = {}
            self.ui_state: Dict[Any, bool] = {}
            self.active_operations: set[str] = set()

        def start_operation(self, operation_id: str) -> None:
            first = len(self.active_operations) == 0
            self.active_operations.add(operation_id)
            if first:
                self.set_ui_busy(True)

        def finish_operation(self, operation_id: str) -> None:
            self.active_operations.discard(operation_id)
            if not self.active_operations:
                for element, state in list(self.ui_state.items()):
                    try:
                        element.setEnabled(state)
                    except Exception:
                        pass
                self.ui_state.clear()

        def start_spinner(self, spinner_name: str) -> bool:
            # Toggle headless spinner and track operation
            if spinner_name not in self.spinner_manager.spinners:
                return False
            is_active = self.spinner_manager.toggle_spinner(spinner_name)
            if is_active:
                self.start_operation(spinner_name)
            else:
                self.finish_operation(spinner_name)
            return is_active

        def stop_spinner(self, spinner_name: str) -> bool:  # noqa: ARG002
            if spinner_name not in self.spinner_manager.spinners:
                return False
            if not self.spinner_manager.is_active(spinner_name):
                return True
            self.spinner_manager.set_spinner_state(spinner_name, False)
            self.finish_operation(spinner_name)
            return True

        def start_progress(
            self,
            operation_id: str,
            title: str,  # noqa: ARG002
            message: str,  # noqa: ARG002
            maximum: int = 100,  # noqa: ARG002
            cancelable: bool = True,  # noqa: ARG002
            cancel_callback=None,  # noqa: ARG002
        ) -> Any:
            self.progress_dialogs[operation_id] = object()
            self.start_operation(operation_id)
            return self.progress_dialogs[operation_id]

        def update_progress(self, operation_id: str, value: int, message: str | None = None) -> None:  # noqa: ARG002,E501
            return None

        def finish_progress(self, operation_id: str, message: str | None = None, auto_close: bool = True, delay: int = 1000) -> None:  # noqa: ARG002,E501
            self.close_progress(operation_id)

        def close_progress(self, operation_id: str) -> None:
            self.progress_dialogs.pop(operation_id, None)
            self.finish_operation(operation_id)

        def set_ui_busy(self, busy: bool, ui_elements: list | None = None) -> None:
            if not busy:
                return
            elements = ui_elements or list(self.ui_state.keys())
            for element in elements:
                if element not in self.ui_state:
                    try:
                        self.ui_state[element] = bool(element.isEnabled())
                    except Exception:
                        self.ui_state[element] = True
                try:
                    element.setEnabled(False)
                except Exception:
                    pass

        def show_status(self, message: str, timeout: int = 3000) -> None:  # noqa: ARG002
            return None

        def stop_all_feedback(self) -> None:
            self.spinner_manager.stop_all_spinners()
            for op_id in list(self.progress_dialogs.keys()):
                self.close_progress(op_id)
            self.active_operations.clear()
            for element, state in list(self.ui_state.items()):
                try:
                    element.setEnabled(state)
                except Exception:
                    pass
            self.ui_state.clear()

    # Minimal dialog-related shims used by error handling utilities
    def show_message_box(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def show_error_message(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def safe_error(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def show_info_message(*args, **kwargs):  # type: ignore[no-redef]
        return None

    def show_confirmation_dialog(*args, **kwargs):  # type: ignore[no-redef]
        return False

    def create_progress_dialog(*args, **kwargs):  # type: ignore[no-redef]
        class _Dummy:
            def show(self):
                pass

            def setLabelText(self, *a, **k):
                pass

            def setValue(self, *a, **k):
                pass

            def close(self):
                pass

            def maximum(self):
                return 100

        return _Dummy()

    def show_status_message(*args, **kwargs):  # type: ignore[no-redef]
        return None

# Import new utilities (kept lightweight and independent of PyQt)
from app.ui_utils.busy_guard import BusyGuard

# Import error handling utilities; if PyQt6 is missing, provide safe fallbacks
try:  # pragma: no cover - exercised indirectly
    from app.ui_utils.error_handling import (
        handle_error,
        handle_external_library_error,
        get_common_error_messages,
    )
except Exception:  # Headless fallback
    def handle_error(*args, **kwargs):  # type: ignore
        # Return a simple message string if available
        return str(args[0]) if args else ""

    def handle_external_library_error(*args, **kwargs):  # type: ignore
        return str(args[0]) if args else ""

    def get_common_error_messages():  # type: ignore
        return {}
