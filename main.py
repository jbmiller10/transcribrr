import sys
import os
from PyQt6.QtWidgets import QApplication
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
    font-family: 'Roboto';
    font-size: 12pt;
}
QLabel {

font-weight: 600;
font-size: 12pt;
font-family: 'Roboto'

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
    font-family: 'Roboto';
    font-size: 12pt;
    font-weight: 900;

}

QPushButton:hover {
    background-color: #507AC7; /* Slightly darker blue on hover */
}

QPushButton:disabled {
    background-color: #B0D1F8; /* Lighter blue when disabled */
    color: #FFFFFF;
}

/* Secondary buttons with a subtle appearance */
QPushButton[isSecondary='true'] {
    background-color: #F7F7F7; /* Light grey matching the input fields */
    color: #333333; /* Dark text for contrast */
    border: 1px solid #DDDDDD;
    border-radius: 4px;
}

QPushButton[isSecondary='true']:hover {
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
    font-family: 'Roboto';
    font-size:12pt;
    font-weight: 425;

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

stylesheet_nightmode = '''/* Base colors for Night Mode */
* {
    background-color: #1e1e1e; /* Dark background for night mode */
    color: #dcdcdc; /* Light grey for text to ensure good contrast */
    border: none;
}
2
/* Text edit and display areas with a subtle shadow for depth */
QTextEdit, QLineEdit {
    background-color: #2e2e2e; /* Slightly lighter grey than the base */
    color: #dcdcdc; /* Light grey for text */
    border: 1px solid #3a3a3a; /* Dark border for definition */
    padding: 5px;
    border-radius: 4px;
    font-family: 'Roboto';
    font-size: 8pt;
}

/* Hover and focus states using a slightly lighter shade */
QTextEdit:hover, QLineEdit:hover,
QTextEdit:focus, QLineEdit:focus {
    border: 1px solid #474747;
}

/* Primary buttons with a pop of color */
QPushButton {
    background-color: #3d8ef8; /* A brighter blue for primary actions */
    color: #FFFFFF; /* White text */
    padding: 6px 12px;
    border-radius: 4px;
    font-family: 'Roboto';
    font-size: 8pt;
    font-weight: 900;
}

QPushButton:hover {
    background-color: #3577c2; /* A slightly darker blue on hover */
}

QPushButton:disabled {
    background-color: #1e1e1e; /* Same as the base background when disabled */
    color: #5a5a5a; /* Greyed out text */
}

/* Secondary buttons with a subtle appearance */
QPushButton[isSecondary='true'] {
    background-color: #2e2e2e; /* Same as text edit areas */
    color: #dcdcdc; /* Light grey text for contrast */
    border: 1px solid #3a3a3a;
}

QPushButton[isSecondary='true']:hover {
    background-color: #3a3a3a;
}

/* Status bar with a slight contrast to the main window */
QStatusBar {
    background-color: #1a1a1a; /* A bit darker than the main background */
    color: #dcdcdc;
}

/* Scroll bars for a modern look */
QScrollBar:vertical {
    background: #2e2e2e;
    width: 10px;
    margin: 10px 0 10px 0;
    border: 1px solid #3a3a3a;
}

QScrollBar::handle:vertical {
    background: #5a5a5a; /* Dark grey for the scroll handle */
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #3d8ef8; /* The bright blue for hover */
}

/* Tables for consistency */
QTableWidget {
    background-color: #1e1e1e;
    color: #dcdcdc;
    gridline-color: #3a3a3a;
}

QTableWidget::item:selected {
    background-color: #3d8ef8;
    color: #FFFFFF;
}

/* Combo Boxes styling */
QComboBox {
    border: 1px solid #3a3a3a;
    border-radius: 3px;
    padding: 1px 18px 1px 3px;
    min-width: 6em;
    font-family: 'Roboto';
    font-size: 8pt;
    font-weight: 425;
    background-color: #2e2e2e; /* Same as text edit areas */
    color: #dcdcdc; /* Light grey text */
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left-width: 1px;
    border-left-color: #3a3a3a;
    border-left-style: solid;
    border-top-right-radius: 3px;
    border-bottom-right-radius: 3px;
    font-family: "Roboto";
    font-size: 12px;
}

QComboBox::down-arrow {
    image: url(icons/dropdown_night.svg); /* Ensure this icon is visible on a dark background */
    width:18px;
    height:18px;
}

QComboBox::item:selected {
    background-color: #3d8ef8; /* Bright blue for selected item */
    color: #FFFFFF;
}
'''

try_again_stylesheet = """
        QWidget {
            color: #ffffff;
            background-color: #333333;
            font-family: 'YourFontFamily'; /* Replace with your font */
            font-size: 10pt;
        }
        /* Style for QListWidget that affects all QListWidgets */
        QListWidget {
            border: none;
            padding: 5px;
        }
        QListWidget::item {
            border-bottom: 1px solid #555;
            padding: 5px;
        }
        QListWidget::item:selected {
            background-color: #555;
        }
        /* General button style */
        QPushButton {
            border: 1px solid #444444;
            padding: 5px;
            border-radius: 4px;
        }
        QPushButton:hover {
            border-color: #666666;
        }
    """


if __name__ == "__main__":
    app = QApplication(sys.argv)
    #app.setStyleSheet(stylesheet)
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec())