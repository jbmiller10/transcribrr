import os
import logging
from typing import Optional, Union, Callable, Dict, Any
from PyQt6.QtWidgets import (
    QMessageBox, QProgressDialog, QLabel, QWidget, QWidgetAction, QToolBar,
    QPushButton, QSizePolicy, QStatusBar
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QMovie, QIcon, QAction
from app.utils import resource_path

# Configure logging (use app name)
logger = logging.getLogger('transcribrr') # Ensure logger name consistency

class SpinnerManager:
    """Centralized manager for spinner animations and button toggling in the UI."""
    def __init__(self, parent_widget: QWidget):
        self.parent = parent_widget
        self.spinners: Dict[str, Dict[str, Any]] = {}

    def create_spinner(self, name: str, toolbar: QToolBar, action_icon: str,
                     action_tooltip: str, callback: Callable,
                     spinner_icon: str = './icons/spinner.gif') -> QAction:
        """Create a spinner associated with a toolbar action/button."""
        action_icon_path = resource_path(action_icon)
        spinner_icon_path = resource_path(spinner_icon)

        # Action for logic/shortcuts
        action = QAction(QIcon(action_icon_path), action_tooltip, self.parent)
        action.setCheckable(False)
        if callable(callback):
            action.triggered.connect(callback)

        # Visible Button Widget
        button = QPushButton()
        if os.path.exists(action_icon_path):
            button.setIcon(QIcon(action_icon_path))
        else:
            logger.warning(f"Action icon not found: {action_icon_path}. Using text.")
            button.setText(action_tooltip.split()[0]) # Fallback text
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(28, 28)
        button.setToolTip(action_tooltip)
        button.clicked.connect(callback)
        action_widget = QWidgetAction(toolbar)
        action_widget.setDefaultWidget(button)
        toolbar.addAction(action_widget)

        # Spinner Widget (initially hidden)
        spinner_movie = QMovie(spinner_icon_path)
        if spinner_movie.isValid():
            spinner_movie.setScaledSize(QSize(24, 24))
        else:
             logger.error(f"Spinner GIF is not valid or not found: {spinner_icon_path}")
        spinner_label = QLabel()
        spinner_label.setMovie(spinner_movie)
        spinner_label.setFixedSize(QSize(28, 28))
        spinner_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_action = QWidgetAction(toolbar)
        spinner_action.setDefaultWidget(spinner_label)
        toolbar.addAction(spinner_action)
        spinner_action.setVisible(False)

        self.spinners[name] = {
            'action': action, # The logical action
            'button_widget': action_widget, # The visible button wrapper
            'movie': spinner_movie,
            'spinner_action': spinner_action, # The spinner wrapper
            'active': False
        }
        return action

    def toggle_spinner(self, name: str) -> bool:
        """Toggle spinner visibility, returns new active state."""
        if name not in self.spinners:
            logger.error(f"Spinner '{name}' not found")
            return False

        spinner_data = self.spinners[name]
        button_widget = spinner_data['button_widget']
        spinner_action = spinner_data['spinner_action']
        spinner_movie = spinner_data['movie']

        is_active = not spinner_data['active']
        spinner_data['active'] = is_active

        if is_active:
            button_widget.setVisible(False)
            spinner_action.setVisible(True)
            if spinner_movie.isValid(): spinner_movie.start()
            logger.debug(f"Spinner '{name}' started.")
        else:
            if spinner_movie.isValid(): spinner_movie.stop()
            spinner_action.setVisible(False)
            button_widget.setVisible(True)
            logger.debug(f"Spinner '{name}' stopped.")

        # Update the logical action's enabled state
        spinner_data['action'].setEnabled(not is_active)

        return is_active

    def set_spinner_state(self, name: str, active: bool):
         """Explicitly set spinner state."""
         if name in self.spinners and self.spinners[name]['active'] != active:
              self.toggle_spinner(name)

    def is_active(self, name: str) -> bool:
        return self.spinners.get(name, {}).get('active', False)

    def stop_all_spinners(self):
        for name in list(self.spinners.keys()): # Iterate over keys copy
            if self.is_active(name):
                self.toggle_spinner(name)


def show_message_box(parent: Optional[QWidget], icon: QMessageBox.Icon, title: str, message: str,
                   buttons=QMessageBox.StandardButton.Ok, default_button=QMessageBox.StandardButton.NoButton):
    """Generic message box function."""
    msg_box = QMessageBox(parent)
    msg_box.setIcon(icon)
    msg_box.setWindowTitle(title)
    msg_box.setText(message)
    # msg_box.setInformativeText("Optional informative text here.") # If needed
    msg_box.setStandardButtons(buttons)
    if default_button != QMessageBox.StandardButton.NoButton:
         msg_box.setDefaultButton(default_button)
    return msg_box.exec()


def show_error_message(parent: Optional[QWidget], title: str, message: str):
    """Show a standardized error message dialog."""
    logger.error(f"{title}: {message}") # Log the error
    show_message_box(parent, QMessageBox.Icon.Critical, title, message)


def show_info_message(parent: Optional[QWidget], title: str, message: str):
    """Show a standardized information message dialog."""
    logger.info(f"{title}: {message}") # Log the info
    show_message_box(parent, QMessageBox.Icon.Information, title, message)


def show_confirmation_dialog(parent: Optional[QWidget], title: str, message: str,
                           default_button: QMessageBox.StandardButton = QMessageBox.StandardButton.No) -> bool:
    """Show a confirmation dialog (Yes/No) and return user choice."""
    logger.debug(f"Confirmation requested: {title} - {message}")
    result = show_message_box(parent, QMessageBox.Icon.Question, title, message,
                              QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                              default_button)
    return result == QMessageBox.StandardButton.Yes


def create_progress_dialog(parent: QWidget, title: str, message: str,
                          cancelable: bool = True, maximum: int = 100,
                          autoclose: bool = True, autoreset: bool = True) -> QProgressDialog:
    """Create a standardized progress dialog.
    
    Args:
        parent: Parent widget
        title: Title of the progress dialog
        message: Initial message in the dialog
        cancelable: Whether dialog is cancelable by the user
        maximum: Maximum progress value (use 0 for indeterminate)
        autoclose: Whether dialog should auto-close on completion
        autoreset: Whether dialog should auto-reset on completion
        
    Returns:
        Configured QProgressDialog instance
    """
    progress = QProgressDialog(message, "Cancel" if cancelable else None, 0, maximum, parent)
    progress.setWindowTitle(title)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(500) # Only show if operation takes time
    progress.setAutoClose(autoclose)
    progress.setAutoReset(autoreset)
    return progress


def show_status_message(parent: QWidget, message: str, timeout: int = 3000):
    """Show a temporary status message in the status bar if available."""
    status_bar = None
    if hasattr(parent, 'statusBar') and callable(parent.statusBar):
        status_bar = parent.statusBar()
    elif isinstance(parent, QStatusBar):
        status_bar = parent
    # Could search parent hierarchy for a status bar if needed

    if status_bar:
        status_bar.showMessage(message, timeout)
        logger.debug(f"Status message: {message}")
    else:
        logger.warning(f"Cannot show status message - no statusBar found on parent: {parent}")


class FeedbackManager:
    """Manages consistent UI feedback for long operations.
    
    Provides a standardized approach to handle visual feedback for time-consuming
    operations including spinners, progress bars, UI disablement, and status updates.
    """
    def __init__(self, parent_widget: QWidget):
        self.parent = parent_widget
        self.spinner_manager = SpinnerManager(parent_widget)
        self.progress_dialogs = {}  # Store references to active progress dialogs
        self.ui_state = {} # Track UI elements disabled state
        self.operation_count = 0 # Count of active operations
        
    def start_spinner(self, spinner_name: str) -> bool:
        """Start a spinner for indeterminate operations."""
        return self.spinner_manager.toggle_spinner(spinner_name)
        
    def stop_spinner(self, spinner_name: str):
        """Stop a specific spinner."""
        self.spinner_manager.set_spinner_state(spinner_name, False)
        
    def start_progress(self, operation_id: str, title: str, message: str, 
                      maximum: int = 100, cancelable: bool = True,
                      cancel_callback = None) -> QProgressDialog:
        """Create and show a progress dialog for determinate operations.
        
        Args:
            operation_id: Unique identifier for this operation
            title: Progress dialog title
            message: Initial progress message
            maximum: Maximum progress value (0 for indeterminate)
            cancelable: Whether user can cancel the operation
            cancel_callback: Function to call if user cancels
            
        Returns:
            The created progress dialog
        """
        # Clean up any existing dialog with same ID
        if operation_id in self.progress_dialogs:
            try:
                self.progress_dialogs[operation_id].close()
            except: pass
            
        progress = create_progress_dialog(
            self.parent, title, message, cancelable, maximum,
            autoclose=False, autoreset=False
        )
        
        if cancelable and cancel_callback:
            progress.canceled.connect(cancel_callback)
            
        self.progress_dialogs[operation_id] = progress
        progress.show()
        
        # Increment operation count
        self.operation_count += 1
        
        return progress
        
    def update_progress(self, operation_id: str, value: int, message: str = None):
        """Update progress for a specific operation."""
        if operation_id in self.progress_dialogs:
            progress = self.progress_dialogs[operation_id]
            if message:
                progress.setLabelText(message)
            progress.setValue(value)
            
    def finish_progress(self, operation_id: str, message: str = None, auto_close: bool = True, delay: int = 1000):
        """Complete a progress operation."""
        if operation_id in self.progress_dialogs:
            progress = self.progress_dialogs[operation_id]
            if message:
                progress.setLabelText(message)
            progress.setValue(progress.maximum())
            
            if auto_close:
                # Use a timer to auto-close after showing completion
                QTimer.singleShot(delay, lambda: self.close_progress(operation_id))
            
    def close_progress(self, operation_id: str):
        """Close and remove a progress dialog."""
        if operation_id in self.progress_dialogs:
            try:
                self.progress_dialogs[operation_id].close()
            except: pass
            self.progress_dialogs.pop(operation_id)
            
            # Decrement operation count
            self.operation_count -= 1
            
            # Re-enable UI if no more operations
            if self.operation_count <= 0:
                self.set_ui_busy(False)
                
    def set_ui_busy(self, busy: bool, ui_elements: list = None):
        """Enable/disable UI elements during long operations.
        
        Args:
            busy: Whether UI should be in busy state
            ui_elements: Specific UI elements to disable, or None for tracked elements
        """
        elements = ui_elements or list(self.ui_state.keys())
        
        if busy:
            # Save current state and disable elements
            for element in elements:
                if element not in self.ui_state:
                    self.ui_state[element] = element.isEnabled()
                element.setEnabled(False)
                
            # Track that we have active operations
            self.operation_count = max(1, self.operation_count)
        else:
            # Only restore if no operations are active
            if self.operation_count <= 0:
                # Restore saved states
                for element in elements:
                    if element in self.ui_state:
                        element.setEnabled(self.ui_state[element])
                # Clear saved states
                self.ui_state = {}
                
    def show_status(self, message: str, timeout: int = 3000):
        """Show a status message."""
        show_status_message(self.parent, message, timeout)
        
    def stop_all_feedback(self):
        """Stop all active feedback indicators."""
        # Stop all spinners
        self.spinner_manager.stop_all_spinners()
        
        # Close all progress dialogs
        for operation_id in list(self.progress_dialogs.keys()):
            self.close_progress(operation_id)
            
        # Reset operation count and re-enable UI
        self.operation_count = 0
        self.set_ui_busy(False)