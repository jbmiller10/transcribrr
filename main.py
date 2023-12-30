import sys
import os
from PyQt6.QtWidgets import QApplication
from app.MainWindow import MainWindow

stylesheet = '''/* Main window background */
QMainWindow {
    background-color: #FFFFFF;  
}

QToolBar {
    border: none;
    background-color: #E1E1E1;
    spacing: 5px;
}
QLabel#RecentRecordingHeader {
color:black;
font-family: Helvetica;
font-size:22pt;

}

QLabel {
color:white;
font-family: Helvetica;
font-size:16pt;

}
QPushButton {
    background-color: transparent;
    color: #000000; /* Black*/
    border: 1px solid transparent;
    border-radius: 1px;
    padding: 1px;
    margin: 0 1px;
}

QPushButton:hover {
    background-color: #F0F0F0; /* Light grey background on hover */
    color: #005A9C; /* Blue text on hover */
    border: 1px solid #005A9C; /* Blue border on hover */
    padding: 1px;
    margin: 0 2px;
}

QPushButton:checked {
    background-color: rgba(0, 0, 0, 0.05); /* Slightly darker transparent overlay*/
    color: #000000;
    border: 2px solid transparent;
    border-radius: 1px;
    padding: 1px;
    margin: 0 1px;
}

QPushButton:pressed {
    background-color: rgba(0, 0, 0, 0.1); 
}

/* Toolbar button styling */
QToolButton {
    background-color: #E1E1E1;
    color: #000000;
    border-radius: 4px; /* Rounded corners */
    padding: 4px;
    margin: 0 2px;
}

QToolButton:checked, QToolButton:hover {
    background-color: #D0D0D0; 
}

QComboBox {
    background-color: #E1E1E1;
    color: #000000;
    border-radius: 4px;
    font-weight: medium;
    padding: 1px 15px 1px 5px; 
    margin-right: 5px;
}

QComboBox::drop-down {
    width: 15px; 
    border: none;
}

QComboBox::down-arrow {
    image: url(icons/dropdown_arrow.svg); 
    height: 17;
    width: 17;
}

QSlider::groove:horizontal {
    border: 1px solid #999999;
    height: 8px; 
    background: #E1E1E1;
    margin: 2px 0;
}

QSlider::handle:horizontal {
    background: #000000;
    border: 1px solid #5c5c5c;
    width: 18px; 
    margin: -2px 0; 
    border-radius: 3px;
}

/* TextEdit where the transcription is displayed */
QTextEdit {
    background-color: #FFFFFF;
    color: #000000; /* Black text for visibility */
    border: 1px solid #CCCCCC; /* Light visible border */
    padding: 5px;
    font-family: 'Helvetica'; 
}

/* ListWidget styling for the recordings list */
QListWidget {
    background-color: #F7F7F7;
    border: none;
    color: #000000;
    padding: 10px; 
}

QListWidget::item {
    background-color: #F7F7F7;
    color: #000000;
    border-bottom: 1px solid #CCCCCC; 
    padding: 5px;
}

QListWidget::item:selected {
    background-color: #E1E1E1;
    color: #000000;
}

/* Scroll bars for a modern look */
QScrollBar:vertical {
    background: #FFFFFF;
    width: 10px; 
    margin: 10px 0px 10px 0px;
    border: 1px solid #CCCCCC;
}

QScrollBar::handle:vertical {
    background-color: #D0D0D0; 
    min-height: 10px; 
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #C0C0C0;
}
'''

stylesheet_night = '''/* Main window background */
QMainWindow {
    background-color: #2B2B2B; 
}

/* Toolbar styling */
QToolBar {
    border: none;
    background-color: #333333; /* Dark grey background */
    spacing: 5px; 
}

QPushButton {
    background-color: transparent;
    color: #FFFFFF;
    border: 1px solid transparent;
    border-radius: 1px;
    padding: 1px;
    margin: 0 1px;
}

QPushButton:hover {
    background-color: transparent;
    color: #214223;
    border: 1px solid blue; /* Blue border on hover */
    /*border-radius: 1px;*/
    padding: 1px;
    margin: 0 2px;
}

QPushButton:checked {
    background-color: rgba(0, 0, 0, 0.1); /* Slightly darker transparent overlay */
    color: #111111;
    border: 2px solid transparent;
    border-radius: 1px;
    padding: 1px;
    margin: 0 1px;
}

QPushButton:pressed {
    background-color: rgba(0, 0, 0, 0.2); /* dark for the pressed state */
}
QLabel#RecentRecordingHeader {
color:white;
font-family: Helvetica;
font-size:22pt;

}


/* Toolbar button styling */
QToolButton {
    background-color: #333333;
    color: #FFFFFF;
    border-radius: 4px; /* Rounded corners */
    padding: 4px;
    margin: 0 2px; 
}

QToolButton:checked, QToolButton:hover {
    background-color: #3A3A3A; /* slightly lighter shade of grey */
}

QComboBox {
    background-color: #333333;
    color: grey;
    border-radius: 4px;
    font-weight: medium;
    padding: 1px 15px 1px 5px;
    margin-right: 5px; 
}

QComboBox::drop-down {
    width: 15px; /* Adjust as needed */
    border: none;
}

QComboBox::down-arrow {
    image: url(icons/dropdown_arrow.svg); 
    height: 17;
    width: 17;
}

QSlider::groove:horizontal {
    border: 1px solid #999999;
    height: 8px; /* Adjust to match your design */
    background: #333333;
    margin: 2px 0;
}

QSlider::handle:horizontal {
    background: #FFFFFF;
    border: 1px solid #5c5c5c;
    width: 18px; /* Adjust to match your design */
    margin: -2px 0; 
    border-radius: 3px;
}

QTextEdit {
    background-color: #2B2B2B;
    color: #FFFFFF; /* White*/
    border: 1px solid #444;
    padding: 5px;
    font-family: 'Helvetica'; 
}

/* ListWidget styling for the recordings list */
QListWidget {
    background-color: #1E1E1E;
    border: none;
    color: #FFFFFF;
    padding: 10px; 
}

QListWidget::item {
    background-color: #1E1E1E;
    color: #FFFFFF;
    border-bottom: 1px solid #333; 
    padding: 5px;
}

QListWidget::item:selected {
    background-color: #333333;
    color: #FFFFFF;
}

/* Scroll bars*/
QScrollBar:vertical {
    background: #2B2B2B;
    width: 10px; 
    margin: 10px 0px 10px 0px;
    border: 1px solid #333333;
}

QScrollBar::handle:vertical {
    background-color: #555555; 
    min-height: 10px; 
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #666666; /* Adjust color as needed */
}
'''

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(stylesheet_night)
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec())