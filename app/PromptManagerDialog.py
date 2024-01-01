from PyQt6.QtWidgets import (
    QPushButton, QTableWidgetItem, QHBoxLayout, QTableWidget, QDialog, QVBoxLayout
)
from PyQt6.QtCore import pyqtSignal
import json


class PromptManagerDialog(QDialog):
    prompts_saved = pyqtSignal()

    def __init__(self, preset_prompts, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Manage Prompts')
        self.layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Prompt Name', 'Prompt Description'])
        self.layout.addWidget(self.table)
        self.preset_prompts = preset_prompts
        self.addButton = QPushButton('Add Prompt')
        self.addButton.clicked.connect(self.add_prompt)
        self.removeButton = QPushButton('Remove Selected Prompt')
        self.removeButton.clicked.connect(self.remove_selected_prompt)
        self.saveButton = QPushButton('Save Changes')
        self.saveButton.clicked.connect(self.save_prompts)

        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(self.addButton)
        buttonLayout.addWidget(self.removeButton)
        buttonLayout.addWidget(self.saveButton)
        self.layout.addLayout(buttonLayout)

        self.load_prompts()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)


    def load_prompts(self):
        # Use self.preset_prompts instead of accessing the parent
        for name, description in self.preset_prompts.items():
            self.add_prompt_to_table(name, description)

    def add_prompt_to_table(self, name, description):
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)
        self.table.setItem(row_position, 0, QTableWidgetItem(name))
        self.table.setItem(row_position, 1, QTableWidgetItem(description))

    def add_prompt(self):
        self.add_prompt_to_table('', '')  # Add an empty row for the new prompt

    def remove_selected_prompt(self):
        selected_rows = self.table.selectionModel().selectedRows()
        for index in sorted(selected_rows, reverse=True):
            self.table.removeRow(index.row())

    def save_prompts(self):
        prompts = {}
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0).text()
            description = self.table.item(row, 1).text()
            if name:  # Ensure that the prompt name isn't empty
                prompts[name] = description
        with open('preset_prompts.json', 'w') as file:
            json.dump(prompts, file, indent=4)
        self.prompts_saved.emit()
        self.close()