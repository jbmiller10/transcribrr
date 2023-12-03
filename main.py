import sys
import os
from PyQt5.QtWidgets import QApplication, QStyleFactory
from MainWindow import MainWindow

stylesheet = '''/* Base color definitions */
* {
    background-color: #FFFFFF; /* White background for crispness and clarity */
    color: #353535; /* A slightly softer shade of black for text */
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; /* Modern, sans-serif font */
    border: none; /* Remove default borders */
}

/* Text areas */
QTextEdit, QLineEdit {
    background-color: #F7F7F7; /* Light gray for input fields to differentiate from the rest */
    color: #353535; /* Consistent text color */
    border: 1px solid #C4C4C4; /* Subtle border color */
    border-radius: 3px; /* Rounded corners for a modern feel */
    padding: 5px;
    font-size: 14px; /* Readable text size */
}

/* Buttons */
QPushButton {
    background-color: #4C8BF5; /* Pleasant blue for buttons */
    color: #FFFFFF; /* White text on buttons for contrast */
    border-radius: 3px; /* Slightly rounded corners for buttons */
    padding: 8px 15px; /* Sufficient padding for clickable area */
    font-size: 14px; /* Sufficient text size for readability */
    text-transform: none; /* Keeping the case as is for readability */
    border: 1px solid #4C8BF5; /* Border color to match the background for a solid look */
}

QPushButton:hover {
    background-color: #3578E5; /* A shade darker on hover for interactivity */
}

QPushButton:disabled {
    background-color: #A0B9F5; /* Lighter blue for disabled state */
    color: #D6D6D6; /* Greyed out text for disabled buttons */
}

/* Settings button styling */
QPushButton#settingsButton {
    background-color: transparent; /* Clear background for an icon-only button */
    color: #4C8BF5; /* Same blue as other buttons for consistency */
    font-size: 16px; /* Larger size for icon buttons */
    border: none; /* No border for a cleaner look */
}

QPushButton#settingsButton:hover {
    color: #3578E5; /* Darker blue on hover */
}

/* Status bar improvements */
QStatusBar {
    background-color: #E8E8E8; /* Lighter shade for a less intrusive status bar */
    color: #353535; /* Keeping the text color consistent with the rest of the app */
    font-size: 14px; /* Standard font size for status messages */
    border-top: 1px solid #C4C4C4; /* Slightly darker border on the top for definition */
}

/* Scrollbar styling for a more modern appearance */
QScrollBar:vertical {
    background: #E8E8E8; /* Background to match the status bar */
    width: 8px; /* Slim for a refined look */
    border: none; /* Remove borders for scrollbars */
}

QScrollBar::handle:vertical {
    background: #C4C4C4; /* Visible but not distracting */
    border-radius: 4px; /* Rounded for smooth appearance */
    min-height: 25px; /* Minimum height for easy interaction */
}

QScrollBar::handle:vertical:hover {
    background: #A6A6A6; /* A bit darker on hover to indicate interactivity */
}

/* Table styling for clarity and consistency */
QTableWidget {
    background-color: #FFFFFF; /* White background for tables */
    color: #353535; /* Text color consistent with the app's palette */
    gridline-color: #C4C4C4; /* Subtle grid lines for non-intrusive separation */
    font-size: 14px; /* Size for readability */
}

QTableWidget::item:selected {
    background-color: #E1E1E1; /* Soft highlight color for selected items */
    color: #353535; /* Text color stays consistent even on selection */
}

/* ComboBox styling for a modern look */
QComboBox {
    background-color: #F7F7F7;
    border: 1px solid #C4C4C4;
    border-radius: 3px;
    padding: 5px;
    font-size: 14px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 15px;
    border-left-width: 0px; /* Align with the combo box border */
}

QComboBox::down-arrow {
    image: url("path/to/your/down-arrow-icon.png"); /* Replace with your icon path */
}

/* Define look for hovered, pressed and focused buttons */
QPushButton:hover {
    background-color: #3578E5; /* Slightly darker blue on hover */
}

QPushButton:pressed {
    background-color: #1E50A2; /* Even darker when pressed */
}

QPushButton:focus {
    border: 1px solid #3578E5; /* Blue border to highlight focus */
}
'''

if __name__ == "__main__":
    app = QApplication(sys.argv)
    #if os.name == 'Darwin':
        #app.setStyle(QStyleFactory.create("Fusion"))
    #else:
    #    app.setStyle(QStyleFactory.create("Fusion"))
    app.setStyleSheet(stylesheet)
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec_())