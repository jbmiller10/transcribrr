import unittest
from unittest.mock import MagicMock, patch

# Create stubs for PyQt6
import sys
import types
sys.modules.setdefault('PyQt6', types.ModuleType('PyQt6'))
qt_widgets = types.ModuleType('PyQt6.QtWidgets')
qt_core = types.ModuleType('PyQt6.QtCore')
qt_gui = types.ModuleType('PyQt6.QtGui')

# Add stub classes


class QWidget:
    def __init__(self, *args, **kwargs): pass
    def setVisible(self, visible): pass
    def setEnabled(self, enabled): pass


class QVBoxLayout:
    def __init__(self, *args, **kwargs): pass
    def setContentsMargins(self, *args): pass
    def setSpacing(self, spacing): pass
    def addLayout(self, layout): pass
    def addWidget(self, widget, *args): pass


class QHBoxLayout:
    def __init__(self, *args, **kwargs): pass
    def setContentsMargins(self, *args): pass
    def setSpacing(self, spacing): pass
    def addWidget(self, widget, *args): pass
    def addStretch(self, *args): pass


class QComboBox:
    def __init__(self, *args, **kwargs): pass
    def addItem(self, text, data=None): pass
    def currentIndex(self): return 0
    def setCurrentIndex(self, index): pass
    def insertSeparator(self, index): pass
    def clear(self): pass
    def setSizePolicy(self, *args): pass
    def findData(self, data): return 0
    def currentData(self): return ""
    def itemData(self, index): return ""
    def blockSignals(self, block): pass
    def count(self): return 0
    def setEnabled(self, enabled): pass


class QLabel:
    def __init__(self, *args, **kwargs): pass


class QPushButton:
    def __init__(self, *args, **kwargs): pass
    def setIcon(self, icon): pass
    def setIconSize(self, size): pass
    def setFixedSize(self, size): pass
    def setToolTip(self, text): pass
    def setText(self, text): pass

    def clicked(self):
        class Signal:
            def connect(self, func): pass
            def disconnect(self): pass
        return Signal()

    def setEnabled(self, enabled): pass


class QTextEdit:
    def __init__(self, *args, **kwargs): pass
    def setPlaceholderText(self, text): pass
    def setMaximumHeight(self, height): pass
    def setFocus(self): pass
    def toPlainText(self): return ""
    def setPlainText(self, text): pass
    def clear(self): pass
    def setEnabled(self, enabled): pass


class QSplitter:
    def __init__(self, *args, **kwargs): pass


class QSizePolicy:
    class Policy:
        Fixed = 0
        Expanding = 1


class QSize:
    def __init__(self, *args, **kwargs): pass


class QMessageBox:
    def exec(self): return True


class QInputDialog:
    @staticmethod
    def getText(*args, **kwargs): return "", True
    @staticmethod
    def getItem(*args, **kwargs): return "", True


class QIcon:
    def __init__(self, *args, **kwargs): pass


class Qt:
    class Orientation:
        Vertical = 0


class QTimer:
    @staticmethod
    def singleShot(delay, func): pass


class Signal:
    def __init__(self, *args): pass
    def connect(self, func): pass
    def emit(self, *args): pass


# Assign stub classes to PyQt6 modules
for name, cls in list(locals().items()):
    if name.startswith('Q') and not name.startswith('_'):
        setattr(qt_widgets, name, cls)

# Additional QT classes
qt_core.Qt = Qt
qt_core.QTimer = QTimer
qt_core.QSize = QSize
qt_core.pyqtSignal = Signal
qt_gui.QIcon = QIcon

# Assign modules to sys.modules
sys.modules['PyQt6.QtWidgets'] = qt_widgets
sys.modules['PyQt6.QtCore'] = qt_core
sys.modules['PyQt6.QtGui'] = qt_gui

# Import the module under test with mocked dependencies
with patch('app.widgets.prompt_bar.PromptManager') as mock_prompt_manager, \
        patch('app.widgets.prompt_bar.resource_path', return_value=''), \
        patch('app.widgets.prompt_bar.show_error_message'), \
        patch('app.widgets.prompt_bar.show_info_message'), \
        patch('app.widgets.prompt_bar.show_confirmation_dialog', return_value=True):

    # Set up the mock PromptManager
    mock_instance = MagicMock()
    mock_prompt_manager.instance.return_value = mock_instance
    mock_instance.get_prompts.return_value = {
        'Test Prompt': {'text': 'Test prompt text', 'category': 'General'},
        'Another Prompt': {'text': 'Another prompt text', 'category': 'Custom'}
    }
    mock_instance.get_prompt_text.return_value = 'Test prompt text'
    mock_instance.get_prompt_category.return_value = 'General'
    mock_instance.add_prompt.return_value = True
    mock_instance.update_prompt.return_value = True
    mock_instance.prompts_changed = Signal()

    # Now import the class under test
    from app.widgets.prompt_bar import PromptBar


class TestPromptBar(unittest.TestCase):
    """Test cases for the PromptBar widget."""

    def setUp(self):
        # Create a fresh instance for each test
        self.prompt_bar = PromptBar()
        # Mock the signals
        self.prompt_bar.instruction_changed = MagicMock()
        self.prompt_bar.edit_requested = MagicMock()

    def test_initialization(self):
        """Test that PromptBar initializes correctly."""
        # Check that prompt manager is retrieved properly
        self.assertIsNotNone(self.prompt_bar.prompt_manager)
        # Check that prompts are loaded to dropdown
        self.prompt_bar.prompt_dropdown.addItem.assert_called()

    def test_load_prompts_to_dropdown(self):
        """Test loading prompts into the dropdown."""
        # Reset mock calls
        self.prompt_bar.prompt_dropdown.clear.reset_mock()
        self.prompt_bar.prompt_dropdown.addItem.reset_mock()

        # Call the method
        self.prompt_bar.load_prompts_to_dropdown()

        # Verify dropdown was cleared and items were added
        self.prompt_bar.prompt_dropdown.clear.assert_called_once()
        self.prompt_bar.prompt_dropdown.addItem.assert_called()

    def test_current_prompt_text(self):
        """Test getting the current prompt text."""
        # Mock current index and data
        self.prompt_bar.prompt_dropdown.currentIndex.return_value = 0
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'Test Prompt'

        # Call the method
        result = self.prompt_bar.current_prompt_text()

        # Verify result
        self.assertEqual(result, 'Test prompt text')

        # Test with custom prompt
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'CUSTOM'
        self.prompt_bar.custom_prompt_input.toPlainText.return_value = 'Custom text'
        result = self.prompt_bar.current_prompt_text()
        self.assertEqual(result, 'Custom text')

    def test_on_prompt_selection_changed(self):
        """Test handling prompt selection changes."""
        # Test selecting a predefined prompt
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'Test Prompt'
        self.prompt_bar.on_prompt_selection_changed(0)

        # Prompt widget should be hidden and edit button visible
        self.prompt_bar.hide_custom_prompt_input = MagicMock()
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'Test Prompt'
        self.prompt_bar.on_prompt_selection_changed(0)
        self.prompt_bar.hide_custom_prompt_input.assert_called_once()

        # Signal should be emitted
        self.prompt_bar.instruction_changed.emit.assert_called()

        # Test selecting custom prompt
        self.prompt_bar.show_custom_prompt_input = MagicMock()
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'CUSTOM'
        self.prompt_bar.on_prompt_selection_changed(1)
        self.prompt_bar.show_custom_prompt_input.assert_called_once()

    def test_on_edit_button_clicked(self):
        """Test handling edit button clicks."""
        # Setup for editing a prompt
        self.prompt_bar.is_editing_existing_prompt = False
        self.prompt_bar.prompt_dropdown.currentIndex.return_value = 0
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'Test Prompt'
        self.prompt_bar.show_custom_prompt_input = MagicMock()

        # Call the method
        self.prompt_bar.on_edit_button_clicked()

        # Verify edit mode is entered
        self.assertTrue(self.prompt_bar.is_editing_existing_prompt)
        self.prompt_bar.show_custom_prompt_input.assert_called_once()
        self.prompt_bar.custom_prompt_input.setPlainText.assert_called_with('Test prompt text')

        # Test canceling edit mode
        self.prompt_bar.is_editing_existing_prompt = True
        self.prompt_bar.hide_custom_prompt_input = MagicMock()

        # Call the method again
        self.prompt_bar.on_edit_button_clicked()

        # Verify edit mode is exited
        self.assertFalse(self.prompt_bar.is_editing_existing_prompt)
        self.prompt_bar.hide_custom_prompt_input.assert_called_once()

    def test_save_custom_prompt_as_template(self):
        """Test saving a custom prompt as a template."""
        # Setup
        self.prompt_bar.custom_prompt_input.toPlainText.return_value = 'New custom prompt text'

        # Mocking QInputDialog.getText to return prompt name
        with patch('app.widgets.prompt_bar.QInputDialog.getText',
                   return_value=('New Prompt', True)):
            # Mocking QInputDialog.getItem to return category
            with patch('app.widgets.prompt_bar.QInputDialog.getItem',
                       return_value=('Custom', True)):
                # Call the method
                self.prompt_bar.save_custom_prompt_as_template()

        # Verify prompt manager was called correctly
        self.prompt_bar.prompt_manager.add_prompt.assert_called_with(
            'New Prompt', 'New custom prompt text', 'Custom')

    def test_save_edited_prompt(self):
        """Test saving changes to an edited prompt."""
        # Setup
        self.prompt_bar.custom_prompt_input.toPlainText.return_value = 'Updated prompt text'
        self.prompt_bar.is_editing_existing_prompt = True
        self.prompt_bar.prompt_dropdown.currentIndex.return_value = 0
        self.prompt_bar.prompt_dropdown.itemData.return_value = 'Test Prompt'
        self.prompt_bar.hide_custom_prompt_input = MagicMock()

        # Call the method
        self.prompt_bar.save_edited_prompt()

        # Verify prompt manager was called correctly
        self.prompt_bar.prompt_manager.update_prompt.assert_called_with(
            'Test Prompt', 'Updated prompt text', 'General')
        self.prompt_bar.hide_custom_prompt_input.assert_called_once()
        self.assertFalse(self.prompt_bar.is_editing_existing_prompt)

    def test_set_enabled(self):
        """Test enabling and disabling the widget."""
        # Call the method
        self.prompt_bar.set_enabled(False)

        # Verify components are disabled
        self.prompt_bar.prompt_dropdown.setEnabled.assert_called_with(False)
        self.prompt_bar.edit_button.setEnabled.assert_called_with(False)
        self.prompt_bar.custom_prompt_input.setEnabled.assert_called_with(False)
        self.prompt_bar.save_button.setEnabled.assert_called_with(False)

        # Test enabling
        self.prompt_bar.set_enabled(True)
        self.prompt_bar.prompt_dropdown.setEnabled.assert_called_with(True)


if __name__ == '__main__':
    unittest.main()
