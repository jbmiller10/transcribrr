"""BusyGuard context manager for UI operations.

A context manager to handle showing/hiding spinners, progress dialogs, and 
disabling/enabling UI elements during long-running operations.
"""

import logging
import uuid
from typing import List, Optional, Callable, Any, Dict, TypeVar, Generic

from PyQt6.QtWidgets import QWidget
from app.ui_utils_legacy import FeedbackManager

logger = logging.getLogger('transcribrr')

# Generic type for operation result
T = TypeVar('T')

class BusyGuard(Generic[T]):
    """Context manager to handle UI state during long operations.
    
    This manager coordinates:
    - UI element disabling/enabling
    - Spinner animations
    - Progress dialog display and updates
    - Status message updates
    - Cancellation handling
    
    Example:
        ```python
        # Simple usage
        with BusyGuard(feedback_manager, "Operation", ui_elements=[button1, button2], 
                       spinner="my_spinner"):
            # Do long-running operation...
            
        # With progress dialog
        with BusyGuard(feedback_manager, "Operation", progress=True, 
                      progress_title="Processing Data") as guard:
            # Update progress during operation
            guard.update_progress(50, "Halfway done...")
            # Complete the operation
        ```
    """
    
    def __init__(
        self, 
        feedback_manager: FeedbackManager,
        operation_name: str,
        ui_elements: Optional[List[QWidget]] = None,
        spinner: Optional[str] = None,
        progress: bool = False,
        progress_title: Optional[str] = None,
        progress_message: Optional[str] = None,
        progress_maximum: int = 100,
        progress_cancelable: bool = True,
        cancel_callback: Optional[Callable[[], Any]] = None,
        status_message: Optional[str] = None,
    ):
        """Initialize BusyGuard with operation parameters.
        
        Args:
            feedback_manager: The feedback manager to use
            operation_name: Name of the operation (used in logs and IDs)
            ui_elements: List of UI elements to disable during operation
            spinner: Name of spinner to show, if any
            progress: Whether to show a progress dialog
            progress_title: Title for progress dialog
            progress_message: Initial message for progress dialog
            progress_maximum: Maximum progress value (0 for indeterminate)
            progress_cancelable: Whether progress dialog can be canceled
            cancel_callback: Function to call if user cancels operation
            status_message: Optional status message to show
        """
        self.feedback_manager = feedback_manager
        self.operation_name = operation_name
        self.ui_elements = ui_elements or []
        self.spinner_name = spinner
        self.show_progress = progress
        self.progress_title = progress_title or f"{operation_name}"
        self.progress_message = progress_message or f"Starting {operation_name.lower()}..."
        self.progress_maximum = progress_maximum
        self.progress_cancelable = progress_cancelable
        self.cancel_callback = cancel_callback
        self.status_message = status_message or f"Starting {operation_name.lower()}..."
        
        # Create unique operation ID to track this specific operation
        self.operation_id = f"{operation_name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}"
        
        # Track started components for proper cleanup
        self.spinner_started = False
        self.progress_started = False
        self.ui_busy = False
        self.result = None  # Will hold operation result if any
        
    def __enter__(self) -> 'BusyGuard[T]':
        """Start the feedback indicators when entering context.
        
        Returns:
            Self for fluent usage
        """
        try:
            # Disable UI elements
            if self.ui_elements:
                self.feedback_manager.set_ui_busy(True, self.ui_elements)
                self.ui_busy = True
            
            # Start spinner if requested
            if self.spinner_name:
                self.spinner_started = self.feedback_manager.start_spinner(self.spinner_name)
                if not self.spinner_started:
                    logger.warning(f"Spinner '{self.spinner_name}' not found or couldn't be started")
            
            # Show progress dialog if requested
            if self.show_progress:
                self.feedback_manager.start_progress(
                    self.operation_id,
                    self.progress_title,
                    self.progress_message,
                    maximum=self.progress_maximum,
                    cancelable=self.progress_cancelable,
                    cancel_callback=self.cancel_callback
                )
                self.progress_started = True
            
            # Show status message
            if self.status_message:
                self.feedback_manager.show_status(self.status_message)
                
            logger.debug(f"BusyGuard started for operation: {self.operation_name}")
                
        except Exception as e:
            logger.error(f"Error in BusyGuard setup: {e}", exc_info=True)
            # Clean up partial setup if there was an error
            self.__exit__(type(e), e, e.__traceback__)
            raise
            
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up all feedback indicators when leaving context."""
        try:
            # Stop spinner if it was started
            if self.spinner_started and self.spinner_name:
                self.feedback_manager.stop_spinner(self.spinner_name)
                
            # Close progress dialog if it was started
            if self.progress_started:
                if exc_type:
                    # Operation ended with exception
                    self.feedback_manager.close_progress(self.operation_id)
                else:
                    # Successful completion
                    self.feedback_manager.finish_progress(
                        self.operation_id,
                        message=f"{self.operation_name} completed successfully.",
                        auto_close=True
                    )
                    
            # The feedback_manager will automatically re-enable UI when operations complete
                
            logger.debug(f"BusyGuard completed for operation: {self.operation_name}")
                
        except Exception as e:
            logger.error(f"Error in BusyGuard cleanup: {e}", exc_info=True)
            # Don't re-raise here to avoid masking the original exception
            
        return False  # Don't suppress exceptions
        
    def update_progress(self, value: int, message: Optional[str] = None) -> None:
        """Update progress dialog if it's being shown.
        
        Args:
            value: Current progress value
            message: Optional new progress message
        """
        if self.progress_started:
            self.feedback_manager.update_progress(self.operation_id, value, message)
            
    def cancel(self) -> None:
        """Cancel the operation and clean up UI state."""
        # Call user's cancel callback if provided
        if self.cancel_callback:
            try:
                self.cancel_callback()
            except Exception as e:
                logger.error(f"Error in cancel callback: {e}", exc_info=True)
                
        # Close the progress dialog immediately
        if self.progress_started:
            self.feedback_manager.close_progress(self.operation_id)
            
        # Update status to show cancellation
        self.feedback_manager.show_status(f"{self.operation_name} canceled")
        
    def set_result(self, result: T) -> T:
        """Store operation result and return it.
        
        This allows capturing the result in the context manager
        while still returning it to the caller.
        
        Args:
            result: The operation result to store
            
        Returns:
            The same result value (for fluent usage)
        """
        self.result = result
        return result