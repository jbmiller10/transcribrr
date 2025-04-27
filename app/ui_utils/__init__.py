"""UI utilities package.

Contains utility classes and functions for UI-related tasks.
"""

# Re-export from legacy module (now renamed to avoid conflicts)
from app.ui_utils_legacy import (
    SpinnerManager,
    FeedbackManager,
    show_message_box,
    show_error_message,
    safe_error,
    show_info_message,
    show_confirmation_dialog,
    create_progress_dialog,
    show_status_message
)

# Import new utilities
from app.ui_utils.busy_guard import BusyGuard

# Import error handling utilities
from app.ui_utils.error_handling import (
    handle_error,
    handle_external_library_error,
    get_common_error_messages
)
