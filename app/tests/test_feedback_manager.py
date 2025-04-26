import sys
import types
import unittest
# Stub PyQt6 modules for headless testing
sys.modules.setdefault('PyQt6', types.ModuleType('PyQt6'))
qt_widgets = types.ModuleType('PyQt6.QtWidgets')
# Stub QWidget classes and QMessageBox with StandardButton
class QMessageBox:
    class Icon:
        Information = Critical = Question = Ok = None
    class StandardButton:
        Ok = 0
        NoButton = 0
        Yes = 0
        No = 0

setattr(qt_widgets, 'QMessageBox', QMessageBox)
for name in ['QProgressDialog', 'QLabel', 'QWidget', 'QWidgetAction',
             'QToolBar', 'QPushButton', 'QSizePolicy', 'QStatusBar']:
    setattr(qt_widgets, name, type(name, (object,), {}))
sys.modules['PyQt6.QtWidgets'] = qt_widgets
qt_core = types.ModuleType('PyQt6.QtCore')
# Dummy Qt and QTimer
class Qt:
    class WindowModality:
        WindowModal = None
    class AlignmentFlag:
        AlignCenter = None
    class Orientation:
        Vertical = None
qt_core.Qt = Qt
class QTimer:
    @staticmethod
    def singleShot(delay, func):
        # Immediately call for tests
        func()
qt_core.QTimer = QTimer
qt_core.pyqtSignal = lambda *args, **kwargs: None
qt_core.QSize = lambda *args, **kwargs: None
sys.modules['PyQt6.QtCore'] = qt_core
qt_gui = types.ModuleType('PyQt6.QtGui')
class QMovie:
    def __init__(self, *args, **kwargs): pass
    def isValid(self): return False
    def setScaledSize(self, size): pass
    def start(self): pass
    def stop(self): pass
qt_gui.QMovie = QMovie
qt_gui.QIcon = lambda *args, **kwargs: None
qt_gui.QAction = type('QAction', (object,), {'__init__': lambda self, *args, **kwargs: None})
sys.modules['PyQt6.QtGui'] = qt_gui
from app.ui_utils import FeedbackManager


class DummyElement:
    """Dummy UI element with setEnabled/isEnabled methods."""
    def __init__(self, enabled=True):
        self._enabled = enabled
        self.history = []

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, state):
        # Record calls for assertion
        self.history.append(state)
        self._enabled = state


class TestFeedbackManager(unittest.TestCase):
    def setUp(self):
        # Parent widget is unused for unit tests
        self.fm = FeedbackManager(parent_widget=None)
        # Create dummy UI elements
        self.elem1 = DummyElement(enabled=True)
        self.elem2 = DummyElement(enabled=False)
        self.elements = [self.elem1, self.elem2]

    def test_set_ui_busy_and_restore(self):
        # Disable elements
        self.fm.set_ui_busy(True, self.elements)
        # Elements should be disabled
        self.assertFalse(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())
        # Internal state saved
        self.assertIn(self.elem1, self.fm.ui_state)
        self.assertIn(self.elem2, self.fm.ui_state)
        self.assertEqual(self.fm.ui_state[self.elem1], True)
        self.assertEqual(self.fm.ui_state[self.elem2], False)

        # No operations active yet
        self.assertEqual(len(self.fm.active_operations), 0)

    def test_start_and_finish_operation_restores(self):
        # Disable UI first
        self.fm.set_ui_busy(True, self.elements)
        # Start two operations
        self.fm.start_operation('op1')
        self.assertIn('op1', self.fm.active_operations)
        self.fm.start_operation('op2')
        self.assertEqual(self.fm.active_operations, {'op1', 'op2'})

        # Finish first operation: UI should remain disabled
        self.fm.finish_operation('op1')
        self.assertIn(self.elem1, self.fm.ui_state)
        self.assertFalse(self.elem1.isEnabled())

        # Finish second operation: UI should be restored
        self.fm.finish_operation('op2')
        # ui_state should be cleared
        self.assertFalse(self.fm.ui_state)
        # Elements restored to original states
        self.assertTrue(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

    def test_concurrent_overlap(self):
        # Disable UI
        self.fm.set_ui_busy(True, self.elements)
        # Start and finish in interleaved order
        self.fm.start_operation('A')
        self.fm.start_operation('B')
        # Finish B first
        self.fm.finish_operation('B')
        # UI still disabled
        self.assertFalse(self.elem1.isEnabled())
        # Finish A
        self.fm.finish_operation('A')
        # Now UI enabled
        self.assertTrue(self.elem1.isEnabled())

    def test_stop_all_feedback(self):
        # Disable and start operations
        self.fm.set_ui_busy(True, self.elements)
        self.fm.start_operation('X')
        self.fm.start_operation('Y')
        # Call stop_all_feedback
        self.fm.stop_all_feedback()
        # active_operations cleared
        self.assertFalse(self.fm.active_operations)
        # ui_state cleared and elements restored
        self.assertFalse(self.fm.ui_state)
        self.assertTrue(self.elem1.isEnabled())
        self.assertFalse(self.elem2.isEnabled())

    def test_finish_operation_idempotent(self):
        # Finish without starting should not error
        self.fm.finish_operation('nonexistent')
        # Still no active_operations
        self.assertFalse(self.fm.active_operations)


if __name__ == '__main__':
    unittest.main()