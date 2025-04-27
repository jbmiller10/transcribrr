"""Prompt Bar widget for managing prompt selection and editing."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QTextEdit,
    QLabel,
    QSizePolicy,
    QInputDialog,
    QMessageBox,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QIcon
from typing import Dict, List, Any

from app.path_utils import resource_path
from app.utils import PromptManager
from app.ui_utils import show_error_message, show_info_message, show_confirmation_dialog


class PromptBar(QWidget):
    """Widget for managing prompt selection and editing."""

    # Signals
    # Emitted when the prompt text changes
    instruction_changed = pyqtSignal(str)
    # Emitted when user requests to edit a prompt
    edit_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.prompt_manager = PromptManager.instance()
        self.is_editing_existing_prompt = False

        # Create main widget layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5)

        # Create toolbar for dropdown and edit button
        self.toolbar = QHBoxLayout()
        self.toolbar.setContentsMargins(0, 0, 0, 0)
        self.toolbar.setSpacing(5)

        # Create prompt dropdown
        self.prompt_label = QLabel("Prompt:")
        self.prompt_dropdown = QComboBox()
        self.prompt_dropdown.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        # Create edit button
        self.edit_button = QPushButton("Edit")
        self.edit_button.setToolTip("Edit selected prompt template")
        self.edit_button.setIcon(QIcon(resource_path("icons/edit.svg")))
        self.edit_button.setIconSize(QSize(16, 16))
        self.edit_button.setFixedSize(QSize(60, 28))

        # Add widgets to toolbar
        self.toolbar.addWidget(self.prompt_label)
        self.toolbar.addWidget(self.prompt_dropdown, 1)
        self.toolbar.addWidget(self.edit_button)

        # Add toolbar to main layout
        self.main_layout.addLayout(self.toolbar)

        # Create a splitter for custom prompt area
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # Create custom prompt widget
        self.prompt_widget = QWidget()
        self.prompt_layout = QVBoxLayout(self.prompt_widget)
        self.prompt_layout.setContentsMargins(0, 5, 0, 5)
        self.prompt_layout.setSpacing(5)

        # Create custom prompt input
        self.custom_prompt_input = QTextEdit()
        self.custom_prompt_input.setPlaceholderText(
            "Enter your custom prompt instructions here..."
        )
        self.custom_prompt_input.setMaximumHeight(120)
        self.prompt_layout.addWidget(self.custom_prompt_input)

        # Create button area
        self.button_widget = QWidget()
        self.button_layout = QHBoxLayout(self.button_widget)
        self.button_layout.setContentsMargins(0, 0, 0, 0)

        # Create save button
        self.save_button = QPushButton("Save as Template")
        self.button_layout.addWidget(self.save_button)
        self.button_layout.addStretch()

        self.prompt_layout.addWidget(self.button_widget)

        # Add prompt widget to main layout
        self.main_layout.addWidget(self.prompt_widget)

        # Initialize state
        # Hide custom prompt area initially
        self.prompt_widget.setVisible(False)

        # Connect signals
        self.prompt_dropdown.currentIndexChanged.connect(
            self.on_prompt_selection_changed
        )
        self.edit_button.clicked.connect(self.on_edit_button_clicked)
        self.save_button.clicked.connect(self.save_custom_prompt_as_template)

        # Connect to PromptManager signals
        self.prompt_manager.prompts_changed.connect(
            self.load_prompts_to_dropdown)

        # Initial load
        self.load_prompts_to_dropdown()

    def load_prompts_to_dropdown(self):
        """Load prompts from PromptManager into the dropdown."""
        prompts = self.prompt_manager.get_prompts()
        current_selection = self.prompt_dropdown.currentData()

        self.prompt_dropdown.blockSignals(True)
        self.prompt_dropdown.clear()

        # Group by category
        categorized_prompts: Dict[str, list[str]] = {}
        for name, data in prompts.items():
            category = data.get("category", "General")
            if category not in categorized_prompts:
                categorized_prompts[category] = []
            categorized_prompts[category].append(name)

        # Add items sorted by category, then name
        for category in sorted(categorized_prompts.keys()):
            prompt_names_in_category = sorted(categorized_prompts[category])
            if category != "General":  # Add separator for non-general categories
                self.prompt_dropdown.insertSeparator(
                    self.prompt_dropdown.count())
            for name in prompt_names_in_category:
                # Display as "Name (Category)" for clarity, except for General
                display_name = f"{name} ({category})" if category != "General" else name
                self.prompt_dropdown.addItem(
                    display_name, name
                )  # Store real name as user data

        # Add Custom Prompt option
        self.prompt_dropdown.insertSeparator(self.prompt_dropdown.count())
        self.prompt_dropdown.addItem(
            "Custom Prompt", "CUSTOM")  # Use unique user data

        # Restore selection if possible
        index = self.prompt_dropdown.findData(
            current_selection)  # Find by real name
        if index == -1 and current_selection == "Custom Prompt":
            index = self.prompt_dropdown.findData("CUSTOM")

        self.prompt_dropdown.setCurrentIndex(index if index != -1 else 0)
        self.prompt_dropdown.blockSignals(False)

        # Trigger update manually to ensure UI state is correct
        self.on_prompt_selection_changed(self.prompt_dropdown.currentIndex())

    def on_prompt_selection_changed(self, index):
        """Handle changes in prompt selection."""
        selected_data = self.prompt_dropdown.itemData(index)

        if selected_data == "CUSTOM":
            self.is_editing_existing_prompt = False
            self.show_custom_prompt_input()
            self.custom_prompt_input.clear()
            self.save_button.setText("Save as Template")

            try:
                self.save_button.clicked.disconnect()
            except TypeError:
                pass  # No connections to disconnect

            self.save_button.clicked.connect(
                self.save_custom_prompt_as_template)
            # Cannot edit the "Custom" option itself
            self.edit_button.setVisible(False)
        else:
            # A predefined prompt is selected
            self.hide_custom_prompt_input()
            self.edit_button.setVisible(True)
            self.is_editing_existing_prompt = False
            self.edit_button.setText("Edit")
            self.edit_button.setToolTip("Edit selected prompt template")

        # Emit signal with current prompt text
        self.instruction_changed.emit(self.current_prompt_text())

    def show_custom_prompt_input(self):
        """Show the custom prompt input area."""
        self.prompt_widget.setVisible(True)
        QTimer.singleShot(
            0, lambda: self.custom_prompt_input.setFocus()
        )  # Set focus after visible

    def hide_custom_prompt_input(self):
        """Hide the custom prompt input area."""
        self.prompt_widget.setVisible(False)

    def on_edit_button_clicked(self):
        """Handle clicks on the edit prompt button."""
        if self.is_editing_existing_prompt:
            # Cancel editing
            self.hide_custom_prompt_input()
            self.edit_button.setText("Edit")
            self.edit_button.setToolTip("Edit selected prompt template")
            self.is_editing_existing_prompt = False
        else:
            # Start editing
            current_index = self.prompt_dropdown.currentIndex()
            selected_prompt_name = self.prompt_dropdown.itemData(current_index)

            if selected_prompt_name != "CUSTOM":
                prompt_text = self.prompt_manager.get_prompt_text(
                    selected_prompt_name)
                if prompt_text is not None:
                    self.is_editing_existing_prompt = True
                    self.custom_prompt_input.setPlainText(prompt_text)
                    self.show_custom_prompt_input()
                    self.edit_button.setText("Cancel")
                    self.edit_button.setToolTip("Cancel editing")
                    self.save_button.setText("Save Changes")

                    try:
                        self.save_button.clicked.disconnect()
                    except TypeError:
                        pass  # No connections to disconnect

                    self.save_button.clicked.connect(self.save_edited_prompt)
                else:
                    show_error_message(
                        self,
                        "Error",
                        f"Could not find prompt '{selected_prompt_name}'.",
                    )
            else:
                show_info_message(
                    self, "Edit Prompt", "Select a saved prompt template to edit it."
                )

    def save_custom_prompt_as_template(self):
        """Save the custom prompt as a new template via PromptManager."""
        prompt_text = self.custom_prompt_input.toPlainText().strip()
        if not prompt_text:
            show_error_message(self, "Empty Prompt",
                               "Cannot save an empty prompt.")
            return

        prompt_name, ok = QInputDialog.getText(
            self, "Save New Prompt", "Enter a name for this new prompt template:"
        )
        if ok and prompt_name:
            if self.prompt_manager.get_prompt_text(prompt_name) is not None:
                if not show_confirmation_dialog(
                    self,
                    "Overwrite Prompt?",
                    f"A prompt named '{prompt_name}' already exists. Overwrite it?",
                ):
                    return

            # Ask for category (optional)
            categories = sorted(
                list(
                    set(
                        p.get("category", "General")
                        for p in self.prompt_manager.get_prompts().values()
                    )
                )
            )
            if "Custom" not in categories:
                categories.append("Custom")

            category, ok_cat = QInputDialog.getItem(
                self,
                "Select Category",
                "Choose a category (or type a new one):",
                categories,
                0,
                True,
            )

            if ok_cat and category:
                if self.prompt_manager.add_prompt(prompt_name, prompt_text, category):
                    show_info_message(
                        self, "Prompt Saved", f"Prompt '{prompt_name}' saved."
                    )

                    # Reload dropdown and select the newly added prompt
                    self.load_prompts_to_dropdown()
                    new_index = self.prompt_dropdown.findData(prompt_name)
                    if new_index != -1:
                        self.prompt_dropdown.setCurrentIndex(new_index)
                    else:
                        self.hide_custom_prompt_input()  # Hide on success anyway

                    self.is_editing_existing_prompt = False  # Reset state
                else:
                    show_error_message(
                        self, "Error", f"Failed to save prompt '{prompt_name}'."
                    )
            else:
                show_info_message(self, "Save Cancelled",
                                  "Prompt save cancelled.")

    def save_edited_prompt(self):
        """Save the edited prompt via PromptManager."""
        edited_text = self.custom_prompt_input.toPlainText().strip()
        if not edited_text:
            show_error_message(self, "Empty Prompt",
                               "Prompt text cannot be empty.")
            return

        current_index = self.prompt_dropdown.currentIndex()
        selected_prompt_name = self.prompt_dropdown.itemData(current_index)

        if selected_prompt_name != "CUSTOM":
            # Keep existing category unless user changes it (optional enhancement)
            current_category = (
                self.prompt_manager.get_prompt_category(selected_prompt_name)
                or "General"
            )
            if self.prompt_manager.update_prompt(
                selected_prompt_name, edited_text, current_category
            ):
                show_info_message(
                    self, "Prompt Updated", f"Prompt '{selected_prompt_name}' updated."
                )
                self.hide_custom_prompt_input()
                self.edit_button.setText("Edit")
                self.edit_button.setToolTip("Edit selected prompt template")
                self.is_editing_existing_prompt = False

                # Reload dropdown to reflect changes
                self.load_prompts_to_dropdown()

                # Re-select the edited prompt
                new_index = self.prompt_dropdown.findData(selected_prompt_name)
                if new_index != -1:
                    self.prompt_dropdown.setCurrentIndex(new_index)
            else:
                show_error_message(
                    self, "Error", f"Failed to update prompt '{selected_prompt_name}'."
                )
        else:
            show_error_message(
                self, "Error", "Cannot save changes to the 'Custom Prompt' option."
            )

    def current_prompt_name(self):
        """Get the name of the currently selected prompt."""
        current_index = self.prompt_dropdown.currentIndex()
        return self.prompt_dropdown.itemData(current_index)

    def current_prompt_text(self):
        """Get the text of the currently selected prompt."""
        current_index = self.prompt_dropdown.currentIndex()
        selected_data = self.prompt_dropdown.itemData(current_index)

        if selected_data == "CUSTOM":
            return self.custom_prompt_input.toPlainText()
        else:
            # Retrieve using the real prompt name stored in UserData
            prompt_name = selected_data
            return self.prompt_manager.get_prompt_text(prompt_name) or ""

    def set_enabled(self, enabled):
        """Enable or disable the prompt bar."""
        self.prompt_dropdown.setEnabled(enabled)
        self.edit_button.setEnabled(
            enabled
            and self.prompt_dropdown.itemData(self.prompt_dropdown.currentIndex())
            != "CUSTOM"
        )
        self.custom_prompt_input.setEnabled(enabled)
        self.save_button.setEnabled(enabled)

    def set_edit_mode(self, editing):
        """Set whether the component is in edit mode."""
        if editing:
            self.show_custom_prompt_input()
        else:
            self.hide_custom_prompt_input()
            # If we were editing an existing prompt, reset the state
            if self.is_editing_existing_prompt:
                self.is_editing_existing_prompt = False
                self.edit_button.setText("Edit")
                self.edit_button.setToolTip("Edit selected prompt template")
