from PyQt6.QtWidgets import QApplication, QMainWindow, QSlider, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

class ToggleSwitch(QSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFixedSize(100, 30)
        self.setMinimum(0)
        self.setMaximum(1)
        self.setValue(0)
        self.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 20px;
                width: 80px;
                margin: 0px;
                border-radius: 10px;
            }
            QSlider::handle:horizontal {
                border: 1px solid #5c5c5c;
                background: gray;
                width: 40px;
                height: 20px;
                border-radius: 10px; 
                position: relative;
            }
            QSlider::handle:horizontal:hover {
            /* */
            }
            QSlider::sub-page:horizontal {
                border-radius: 10px;
            }
        """)
        self.setTickPosition(QSlider.TickPosition.NoTicks)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Determine the value to set based on the mouse position
            if event.position().x() < self.width() / 2:
                self.setValue(0)
            else:
                self.setValue(1)
            event.accept()

    def toggle(self):
        self.setValue(0 if self.value() == 1 else 1)

    def setValue(self, value):
        if value != self.value():
            super().setValue(value)
            self.valueChanged.emit(value)