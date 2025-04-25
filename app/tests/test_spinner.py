#!/usr/bin/env python3
"""Test for SpinnerManager and FeedbackManager spinner functionality."""

import sys
import os
import logging
from PyQt6.QtWidgets import QApplication, QMainWindow, QToolBar, QPushButton
from PyQt6.QtCore import QTimer

# Add parent directory to path to find modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ui_utils import SpinnerManager, FeedbackManager

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
logger = logging.getLogger('spinner_test')

class SpinnerTestWindow(QMainWindow):
    """Test window for spinner functionality."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spinner Test")
        self.setGeometry(100, 100, 600, 400)
        
        # Create toolbar
        self.toolbar = QToolBar()
        self.addToolBar(self.toolbar)
        
        # Create spinner manager
        self.spinner_manager = SpinnerManager(self)
        
        # Create feedback manager
        self.feedback_manager = FeedbackManager(self)
        
        # Define callback
        def button_action():
            logger.info("Button clicked")
            
        # Register spinners
        logger.info("Registering spinners...")
        
        self.spinner_manager.create_spinner(
            name='spinner1',
            toolbar=self.toolbar,
            action_icon='./icons/transcribe.svg',
            action_tooltip='Test Spinner 1',
            callback=button_action
        )
        
        self.spinner_manager.create_spinner(
            name='spinner2',
            toolbar=self.toolbar,
            action_icon='./icons/magic_wand.svg',
            action_tooltip='Test Spinner 2',
            callback=button_action
        )
        
        # Add test buttons
        logger.info("Adding test buttons...")
        
        start_button1 = QPushButton("Start Spinner 1")
        start_button1.clicked.connect(lambda: self.test_spinner('spinner1', True))
        self.toolbar.addWidget(start_button1)
        
        stop_button1 = QPushButton("Stop Spinner 1")
        stop_button1.clicked.connect(lambda: self.test_spinner('spinner1', False))
        self.toolbar.addWidget(stop_button1)
        
        start_button2 = QPushButton("Start Spinner 2")
        start_button2.clicked.connect(lambda: self.test_spinner('spinner2', True))
        self.toolbar.addWidget(start_button2)
        
        stop_button2 = QPushButton("Stop Spinner 2")
        stop_button2.clicked.connect(lambda: self.test_spinner('spinner2', False))
        self.toolbar.addWidget(stop_button2)
        
        # Setup auto test
        self.auto_test_timer = QTimer(self)
        self.auto_test_timer.timeout.connect(self.run_auto_test)
        self.auto_test_timer.setSingleShot(True)
        self.auto_test_timer.start(1000)  # Start test after 1 second
        
        self.test_step = 0
        
    def test_spinner(self, name, start):
        """Test starting/stopping a spinner using the FeedbackManager."""
        if start:
            result = self.feedback_manager.start_spinner(name)
            logger.info(f"Started spinner '{name}': {result}")
        else:
            result = self.feedback_manager.stop_spinner(name)
            logger.info(f"Stopped spinner '{name}': {result}")
            
    def run_auto_test(self):
        """Run automatic test sequence."""
        if self.test_step == 0:
            logger.info("=== STARTING AUTOMATIC TEST SEQUENCE ===")
            logger.info("Test 1: Starting spinner1")
            result = self.feedback_manager.start_spinner('spinner1')
            logger.info(f"Result: {result}")
            self.test_step += 1
            self.auto_test_timer.start(1500)
            
        elif self.test_step == 1:
            logger.info("Test 2: Starting spinner2")
            result = self.feedback_manager.start_spinner('spinner2')
            logger.info(f"Result: {result}")
            self.test_step += 1
            self.auto_test_timer.start(1500)
            
        elif self.test_step == 2:
            logger.info("Test 3: Stopping spinner1")
            result = self.feedback_manager.stop_spinner('spinner1')
            logger.info(f"Result: {result}")
            self.test_step += 1
            self.auto_test_timer.start(1500)
            
        elif self.test_step == 3:
            logger.info("Test 4: Starting non-existent spinner")
            result = self.feedback_manager.start_spinner('nonexistent')
            logger.info(f"Result: {result}")
            self.test_step += 1
            self.auto_test_timer.start(1500)
            
        elif self.test_step == 4:
            logger.info("Test 5: Stopping spinner2")
            result = self.feedback_manager.stop_spinner('spinner2')
            logger.info(f"Result: {result}")
            logger.info("=== TEST SEQUENCE COMPLETE ===")
            

def main():
    """Main function to run the spinner test."""
    app = QApplication(sys.argv)
    window = SpinnerTestWindow()
    window.show()
    sys.exit(app.exec())
    
if __name__ == "__main__":
    main()