import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from main import initialize_app

def test_startup():
    # Initialize the app
    app, main_window = initialize_app()
    
    # Set a timer to exit after 2 seconds
    QTimer.singleShot(2000, app.quit)
    
    # Run the application
    return app.exec()

if __name__ == "__main__":
    sys.exit(test_startup())