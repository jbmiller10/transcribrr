from PyQt6.QtWidgets import (
    QPushButton,
    QTableWidget,
    QTextEdit,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidgetItem,
    QLineEdit,
    QLabel,
    QComboBox,
    QTabWidget,
    QWidget,
    QFileDialog,
    QMessageBox,
    QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from app.path_utils import resource_path
from app.utils import PromptManager
from app.ui_utils import show_error_message, show_info_message, show_confirmation_dialog


class PromptEditorWidget(QWidget):
    """Prompt edit widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.name_layout = QHBoxLayout()
        self.name_label = QLabel("Prompt Name:")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(
            "Enter a concise, descriptive name...")
        self.category_label = QLabel("Category:")
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.addItems(
            [
                "General",
                "Transcription",
                "Summarization",
                "Formatting",
                "Translation",
                "Custom",
            ]
        )
        self.name_layout.addWidget(self.name_label)
        self.name_layout.addWidget(self.name_input, 1)
        self.name_layout.addWidget(self.category_label)
        self.name_layout.addWidget(self.category_combo)
        self.layout.addLayout(self.name_layout)

        self.text_label = QLabel("Prompt Template:")
        self.layout.addWidget(self.text_label)
        self.prompt_text = QTextEdit()
        self.prompt_text.setPlaceholderText(
            "Enter the prompt template text here. Use {transcript} for the input text."
        )
        self.layout.addWidget(self.prompt_text, 1)

        self.variables_hint = QLabel(
            "Variable: {transcript} - will be replaced by the recording's transcript."
        )
        self.variables_hint.setStyleSheet("color: gray; font-style: italic;")
        self.layout.addWidget(self.variables_hint)

    def set_prompt(self, name, text, category="General"):
        self.name_input.setText(name)
        self.prompt_text.setText(text)
        index = self.category_combo.findText(
            category, Qt.MatchFlag.MatchFixedString | Qt.MatchFlag.MatchCaseSensitive
        )
        if index >= 0:
            self.category_combo.setCurrentIndex(index)
        else:
            self.category_combo.addItem(category)
            self.category_combo.setCurrentText(category)

    def get_prompt_data(self):
        return {
            "name": self.name_input.text().strip(),
            "text": self.prompt_text.toPlainText().strip(),
            "category": self.category_combo.currentText().strip(),
        }

    def clear(self):
        self.name_input.clear()
        self.prompt_text.clear()
        self.category_combo.setCurrentIndex(
            self.category_combo.findText("General")
        )  # Default to General


class PromptManagerDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Prompt Template Manager")
        self.resize(800, 600)
        self.prompt_manager = PromptManager.instance()  # Get singleton

        # Initialize prompt state
        self.categorized_prompts = {}
        self._load_and_organize_prompts()  # Load from manager

        self.layout = QVBoxLayout(self)
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        self.create_browse_tab()
        self.create_edit_tab()

        self.button_layout = QHBoxLayout()
        self.import_button = QPushButton("Import")
        self.import_button.setIcon(QIcon(resource_path("icons/import.svg")))
        self.import_button.clicked.connect(self.import_prompts)
        self.export_button = QPushButton("Export")
        self.export_button.setIcon(QIcon(resource_path("icons/export.svg")))
        self.export_button.clicked.connect(self.export_prompts)
        self.cancel_button = QPushButton("Close")
        self.cancel_button.clicked.connect(self.reject)  # Close dialog

        self.button_layout.addWidget(self.import_button)
        self.button_layout.addWidget(self.export_button)
        self.button_layout.addStretch()
        self.button_layout.addWidget(self.cancel_button)

        self.layout.addLayout(self.button_layout)

    def _load_and_organize_prompts(self):
        """Load prompts for UI."""
        all_prompts = self.prompt_manager.get_prompts()
        self.categorized_prompts = {}
        for name, data in all_prompts.items():
            category = data.get("category", "General")
            if category not in self.categorized_prompts:
                self.categorized_prompts[category] = []
            # Store the full data dict for easier access
            self.categorized_prompts[category].append({"name": name, **data})
        # Update UI elements if they exist
        if hasattr(self, "prompt_table"):
            self.populate_prompt_table()
        if hasattr(self, "category_filter"):
            self._update_category_filter()

    def _update_category_filter(self):
        """Update category filter."""
        current_text = self.category_filter.currentText()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem("All Categories")
        for category in sorted(self.categorized_prompts.keys()):
            self.category_filter.addItem(category)
        index = self.category_filter.findText(current_text)
        self.category_filter.setCurrentIndex(index if index >= 0 else 0)
        self.category_filter.blockSignals(False)

    def create_browse_tab(self):
        browse_tab = QWidget()
        browse_layout = QVBoxLayout(browse_tab)
        filter_layout = QHBoxLayout()
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText(
            "Search prompts by name or text...")
        self.filter_input.textChanged.connect(self.apply_filter)
        self.category_filter = QComboBox()
        self._update_category_filter()  # Populate categories
        self.category_filter.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(QLabel("Filter:"))
        filter_layout.addWidget(self.filter_input)
        filter_layout.addWidget(QLabel("Category:"))
        filter_layout.addWidget(self.category_filter)
        browse_layout.addLayout(filter_layout)

        self.prompt_table = QTableWidget(0, 3)
        self.prompt_table.setHorizontalHeaderLabels(
            ["Name", "Category", "Prompt Text"])
        self.prompt_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.prompt_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.prompt_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self.prompt_table.itemSelectionChanged.connect(
            self.on_prompt_selection_changed)
        self.prompt_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )  # Not editable here
        browse_layout.addWidget(self.prompt_table)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add New")
        self.add_button.setIcon(QIcon(resource_path("icons/add.svg")))
        self.add_button.clicked.connect(self.add_new_prompt)
        self.edit_button = QPushButton("Edit")
        self.edit_button.setIcon(QIcon(resource_path("icons/edit.svg")))
        self.edit_button.clicked.connect(self.edit_selected_prompt)
        self.edit_button.setEnabled(False)
        self.remove_button = QPushButton("Remove")
        self.remove_button.setIcon(QIcon(resource_path("icons/delete.svg")))
        self.remove_button.clicked.connect(self.remove_selected_prompt)
        self.remove_button.setEnabled(False)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addStretch()
        browse_layout.addLayout(button_layout)

        self.tab_widget.addTab(browse_tab, "Manage Prompts")
        self.populate_prompt_table()

    def create_edit_tab(self):
        edit_tab = QWidget()
        edit_layout = QVBoxLayout(edit_tab)
        self.prompt_editor = PromptEditorWidget()
        edit_layout.addWidget(self.prompt_editor)

        button_layout = QHBoxLayout()
        self.clear_button = QPushButton("Clear Fields")
        self.clear_button.clicked.connect(self.clear_editor)
        # Changed button text - action depends on context (add vs update)
        self.save_edit_button = QPushButton("Save Prompt")
        self.save_edit_button.setIcon(QIcon(resource_path("icons/save.svg")))
        self.save_edit_button.clicked.connect(self.save_edited_prompt_from_tab)
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        button_layout.addWidget(self.save_edit_button)
        edit_layout.addLayout(button_layout)

        self.tab_widget.addTab(edit_tab, "Create / Edit")
        # Keep track if we are editing an existing prompt
        self._editing_prompt_name = None

    def populate_prompt_table(self):
        self.prompt_table.setRowCount(0)
        selected_category = self.category_filter.currentText()
        show_all = selected_category == "All Categories"
        search_text = self.filter_input.text().lower()
        row = 0

        # Iterate through the organized prompts
        for category, prompts in sorted(self.categorized_prompts.items()):
            if show_all or category == selected_category:
                # Sort prompts by name within category
                for prompt_data in sorted(prompts, key=lambda p: p["name"]):
                    name = prompt_data["name"]
                    text = prompt_data["text"]
                    # Filter logic
                    if (
                        search_text
                        and search_text not in name.lower()
                        and search_text not in text.lower()
                    ):
                        continue

                    self.prompt_table.insertRow(row)
                    self.prompt_table.setItem(row, 0, QTableWidgetItem(name))
                    self.prompt_table.setItem(
                        row, 1, QTableWidgetItem(category))
                    display_text = text[:100] + \
                        "..." if len(text) > 100 else text
                    table_item = QTableWidgetItem(display_text)
                    table_item.setData(
                        Qt.ItemDataRole.UserRole, prompt_data
                    )  # Store full data
                    self.prompt_table.setItem(row, 2, table_item)
                    row += 1

        self.prompt_table.resizeColumnsToContents()
        self.prompt_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.on_prompt_selection_changed()  # Update button states

    def apply_filter(self):
        self.populate_prompt_table()

    def on_prompt_selection_changed(self):
        has_selection = bool(self.prompt_table.selectedItems())
        self.edit_button.setEnabled(has_selection)
        self.remove_button.setEnabled(has_selection)

    def add_new_prompt(self):
        self._editing_prompt_name = None  # Ensure we are adding, not editing
        self.clear_editor()
        self.tab_widget.setCurrentIndex(1)  # Switch to edit tab
        self.prompt_editor.name_input.setFocus()

    def edit_selected_prompt(self):
        selected_rows = self.prompt_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        prompt_data = self.prompt_table.item(
            row, 2).data(Qt.ItemDataRole.UserRole)

        # Store name being edited
        self._editing_prompt_name = prompt_data["name"]
        self.prompt_editor.set_prompt(
            prompt_data["name"], prompt_data["text"], prompt_data["category"]
        )
        self.tab_widget.setCurrentIndex(1)  # Switch to edit tab

    def remove_selected_prompt(self):
        selected_rows = self.prompt_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        prompt_data = self.prompt_table.item(
            row, 2).data(Qt.ItemDataRole.UserRole)
        name = prompt_data["name"]

        if show_confirmation_dialog(
            self, "Confirm Deletion", f"Delete the prompt '{name}'?"
        ):
            if self.prompt_manager.delete_prompt(name):
                show_info_message(self, "Prompt Deleted",
                                  f"Prompt '{name}' deleted.")
                self._load_and_organize_prompts()  # Reload internal state and update UI
            else:
                show_error_message(
                    self, "Error", f"Failed to delete prompt '{name}'.")

    def clear_editor(self):
        self._editing_prompt_name = None  # Clear editing state
        self.prompt_editor.clear()

    def save_edited_prompt_from_tab(self):
        """Save prompt."""
        data = self.prompt_editor.get_prompt_data()
        if not data["name"]:
            show_error_message(self, "Missing Name",
                               "Prompt name cannot be empty.")
            return
        if not data["text"]:
            show_error_message(self, "Missing Text",
                               "Prompt text cannot be empty.")
            return
        if not data["category"]:
            data["category"] = "General"  # Ensure category is set

        existing_prompt = self.prompt_manager.get_prompt_text(data["name"])
        is_update = (
            self._editing_prompt_name is not None
            and self._editing_prompt_name == data["name"]
        )
        is_new_name_conflict = existing_prompt is not None and not is_update

        if is_new_name_conflict:
            if not show_confirmation_dialog(
                self,
                "Overwrite Prompt?",
                f"A prompt named '{data['name']}' already exists. Overwrite it?",
            ):
                return

        # Use PromptManager to add or update
        success = False
        if is_update:
            success = self.prompt_manager.update_prompt(
                data["name"], data["text"], data["category"]
            )
        else:  # Add new or overwrite existing with confirmation
            success = self.prompt_manager.add_prompt(
                data["name"], data["text"], data["category"]
            )

        if success:
            action = "updated" if is_update else "saved"
            show_info_message(
                self, "Success", f"Prompt '{data['name']}' {action}.")
            self._load_and_organize_prompts()  # Reload internal state and update UI
            self.clear_editor()
            self.tab_widget.setCurrentIndex(0)  # Switch back to browse tab
        else:
            show_error_message(
                self, "Error", f"Failed to save prompt '{data['name']}'."
            )

    def import_prompts(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Prompts", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        # Ask merge/replace
        merge = show_confirmation_dialog(
            self,
            "Import Option",
            "Merge imported prompts with existing ones? (No will replace all)",
            default_button=QMessageBox.StandardButton.Yes,
        )

        success, message = self.prompt_manager.import_prompts_from_file(
            file_path, merge=merge
        )
        if success:
            show_info_message(self, "Import Successful", message)
            self._load_and_organize_prompts()  # Reload internal state and update UI
        else:
            show_error_message(self, "Import Failed", message)

    def export_prompts(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Prompts", "transcribrr_prompts.json", "JSON Files (*.json)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".json"):
            file_path += ".json"

        success, message = self.prompt_manager.export_prompts_to_file(
            file_path)
        if success:
            show_info_message(self, "Export Successful", message)
        else:
            show_error_message(self, "Export Failed", message)
