import sys
import os
from PyQt5.QtWidgets import QApplication, QStyleFactory
from app.MainWindow import MainWindow

stylesheet = '''/* Base colors */
* {
    background-color: #FFFFFF; /* White background for a clean look */
    color: #333333; /* Almost black for primary text */
    border: none;
}

/* Text edit and display areas with a subtle shadow for depth */
QTextEdit, QLineEdit {
    background-color: #F9F9F9; /* Light grey background */
    color: #333333; /* Dark text for readability */
    border: 1px solid #DDDDDD; /* Light border for definition */
    padding: 5px;
    border-radius: 4px;
}

/* Hover and focus states using a slightly darker shade */
QTextEdit:hover, QLineEdit:hover,
QTextEdit:focus, QLineEdit:focus {
    border: 1px solid #CCCCCC;
}

/* Primary buttons with a pop of color */
QPushButton {
    background-color: #5E97F6; /* Vibrant blue for primary actions */
    color: #FFFFFF; /* White text */
    padding: 6px 12px;
    border-radius: 4px;
}

QPushButton:hover {
    background-color: #507AC7; /* Slightly darker blue on hover */
}

QPushButton:disabled {
    background-color: #B0D1F8; /* Lighter blue when disabled */
    color: #FFFFFF;
}

/* Secondary buttons with a subtle appearance */
QPushButton#secondaryButton {
    background-color: #F7F7F7; /* Light grey matching the input fields */
    color: #333333; /* Dark text for contrast */
    padding: 6px 12px;
    border: 1px solid #DDDDDD;
    border-radius: 4px;
}

QPushButton#secondaryButton:hover {
    background-color: #E6E6E6;
}

/* Status bar with a slight contrast to the main window */
QStatusBar {
    background-color: #FFFFFF; /* Slightly darker grey for the status bar */
    color: #333333;
}

/* Scroll bars for a modern look */
QScrollBar:vertical {
    background: #F7F7F7;
    width: 10px;
    margin: 10px 0 10px 0;
    border: 1px solid #DDDDDD;
}

QScrollBar::handle:vertical {
    background: #B0D1F8; /* Light blue for the scroll handle */
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #5E97F6; /* The vibrant blue for hover */
}

/* Tables for consistency */
QTableWidget {
    background-color: #FFFFFF;
    color: #333333;
    gridline-color: #DDDDDD;
}

QTableWidget::item:selected {
    background-color: #5E97F6;
    color: #FFFFFF;
}

QComboBox {
    border: 1px solid silver;
    border-radius: 3px;
    padding: 1px 18px 1px 3px;
    min-width: 6em;
}
/*
QComboBox:hover {
    border-color: #5E97F6;
}*/



QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px; /* Make sure this width is enough to contain the arrow with some padding */
    border-left-width: 1px;
    border-left-color: darkgray;
    border-left-style: solid;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
}

QComboBox::down-arrow {
    image: url(icons/dropdown.svg);
    width: 18px; /* Adjust the width as needed */
    height: 18px; /* Adjust the height as needed */
}

QComboBox::item:selected
{
    background-color: #F1F1F1;
    color: rgb(0, 0, 0);
}

'''



if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet)
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec_())