import sys
import os
import logging
import json
import traceback
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QSplashScreen, QVBoxLayout,
    QLabel, QProgressBar, QWidget, QStyleFactory
)
from PyQt6.QtGui import QPixmap, QFont, QIcon
from PyQt6.QtCore import Qt, QTimer, QSize
from app.MainWindow import MainWindow
from app.utils import resource_path, check_system_requirements, cleanup_temp_files

# Configure logging
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_dir = os.path.join(os.getcwd(), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'transcribrr.log')

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)

logger = logging.getLogger('transcribrr')

# Create Recordings directory if it doesn't exist
os.makedirs(os.path.join(os.getcwd(), 'Recordings'), exist_ok=True)

# Global variables for stylesheet handling
APP_STYLE = None
APP_STYLESHEET = None


def load_stylesheet(style_name='light'):
    """Load application stylesheet."""
    global APP_STYLE, APP_STYLESHEET

    APP_STYLE = style_name.lower()

    # Base stylesheet variables
    base_variables = {
        # Common colors
        'primary': '#3366CC',
        'secondary': '#6699CC',
        'accent': '#FF9900',
        'error': '#FF5252',
        'success': '#4CAF50',
        'warning': '#FFC107',
        'info': '#2196F3',

        # Font settings
        'font-family': 'Arial, Helvetica, sans-serif',
        'font-size-small': '10px',
        'font-size-normal': '12px',
        'font-size-large': '14px',
        'font-size-xlarge': '16px',

        # Spacing
        'spacing-small': '5px',
        'spacing-normal': '10px',
        'spacing-large': '15px',

        # Borders
        'border-radius': '4px',
        'border-width': '1px',
    }

    # Light theme variables
    light_variables = {
        'background': '#FFFFFF',
        'background-secondary': '#F5F5F5',
        'background-tertiary': '#EEEEEE',
        'foreground': '#202020',
        'foreground-secondary': '#505050',
        'border': '#DDDDDD',
        'inactive': '#AAAAAA',
    }

    # Dark theme variables
    dark_variables = {
        'background': '#2B2B2B',
        'background-secondary': '#333333',
        'background-tertiary': '#3A3A3A',
        'foreground': '#EEEEEE',
        'foreground-secondary': '#BBBBBB',
        'border': '#555555',
        'inactive': '#777777',
    }

    # Select theme variables
    variables = {**base_variables}
    if style_name.lower() == 'dark':
        variables.update(dark_variables)
    else:
        variables.update(light_variables)

    # Common stylesheet for all themes
    common_css = f"""
        /* Global styles */
        QWidget {{
            font-family: {variables['font-family']};
            font-size: {variables['font-size-normal']};
            color: {variables['foreground']};
        }}

        QMainWindow {{
            background-color: {variables['background']};
        }}

        /* Toolbars */
        QToolBar {{
            border: none;
            background-color: {variables['background-secondary']};
            spacing: {variables['spacing-normal']};
            padding: {variables['spacing-small']};
        }}

        /* Headers */
        QLabel#RecentRecordingHeader {{
            color: {variables['foreground']};
            font-family: {variables['font-family']};
            font-size: {variables['font-size-xlarge']};
            font-weight: bold;
        }}

        /* Labels */
        QLabel {{
            color: {variables['foreground']};
            font-family: {variables['font-family']};
            font-weight: normal;
            font-size: {variables['font-size-normal']};
        }}

        /* Buttons */
        QPushButton {{
            background-color: {variables['background-secondary']};
            color: {variables['foreground']};
            border: {variables['border-width']} solid {variables['border']};
            border-radius: {variables['border-radius']};
            padding: {variables['spacing-small']};
            min-height: 25px;
        }}

        QPushButton:hover {{
            background-color: {variables['background-tertiary']};
            border: {variables['border-width']} solid {variables['primary']};
        }}

        QPushButton:pressed {{
            background-color: {variables['primary']};
            color: {'white' if style_name == 'dark' else 'white'};
        }}

        QPushButton:disabled {{
            background-color: {variables['background-secondary']};
            color: {variables['inactive']};
            border: {variables['border-width']} solid {variables['border']};
        }}

        /* Dropdowns */
        QComboBox {{
            background-color: {variables['background-secondary']};
            color: {variables['foreground']};
            border: {variables['border-width']} solid {variables['border']};
            border-radius: {variables['border-radius']};
            padding: {variables['spacing-small']};
            min-height: 25px;
        }}

        QComboBox::drop-down {{
            width: 20px;
            border: none;
        }}

        QComboBox QAbstractItemView {{
            background-color: {variables['background']};
            color: {variables['foreground']};
            border: {variables['border-width']} solid {variables['border']};
            selection-background-color: {variables['primary']};
            selection-color: {'white' if style_name == 'dark' else 'white'};
        }}

        /* Sliders */
        QSlider::groove:horizontal {{
            border: {variables['border-width']} solid {variables['border']};
            height: 8px;
            background: {variables['background-tertiary']};
            margin: 2px 0;
            border-radius: 4px;
        }}

        QSlider::handle:horizontal {{
            background: {variables['primary']};
            border: {variables['border-width']} solid {variables['primary']};
            width: 18px;
            height: 18px;
            margin: -5px 0;
            border-radius: 9px;
        }}

        /* Text Editor */
        QTextEdit {{
            background-color: {variables['background']};
            color: {variables['foreground']};
            border: {variables['border-width']} solid {variables['border']};
            selection-background-color: {variables['primary']};
            selection-color: {'white' if style_name == 'dark' else 'white'};
            padding: {variables['spacing-small']};
        }}

        /* List Widget */
        QListWidget {{
            background-color: {variables['background']};
            color: {variables['foreground']};
            border: none;
            outline: none;
        }}

        QListWidget::item {{
            background-color: {variables['background']};
            color: {variables['foreground']};
            border-bottom: 1px solid {variables['border']};
            padding: {variables['spacing-small']};
        }}

        QListWidget::item:selected {{
            background-color: {variables['background-tertiary']};
            color: {variables['foreground']};
        }}

        QListWidget::item:hover {{
            background-color: {variables['background-secondary']};
        }}

        /* Scroll bars */
        QScrollBar:vertical {{
            background: {variables['background']};
            width: 10px;
            margin: 10px 0px 10px 0px;
            border: 1px solid {variables['border']};
        }}

        QScrollBar::handle:vertical {{
            background-color: {variables['background-tertiary']};
            min-height: 20px;
            border-radius: 5px;
        }}

        QScrollBar::handle:vertical:hover {{
            background-color: {variables['primary']};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}

        QScrollBar:horizontal {{
            background: {variables['background']};
            height: 10px;
            margin: 0px 10px 0px 10px;
            border: 1px solid {variables['border']};
        }}

        QScrollBar::handle:horizontal {{
            background-color: {variables['background-tertiary']};
            min-width: 20px;
            border-radius: 5px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background-color: {variables['primary']};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}

        /* Tab Widget */
        QTabWidget::pane {{
            border: 1px solid {variables['border']};
        }}

        QTabBar::tab {{
            background-color: {variables['background-secondary']};
            color: {variables['foreground']};
            padding: 8px 12px;
            border: 1px solid {variables['border']};
            border-bottom-color: {'transparent' if style_name == 'dark' else variables['border']};
            border-top-left-radius: {variables['border-radius']};
            border-top-right-radius: {variables['border-radius']};
        }}

        QTabBar::tab:selected {{
            background-color: {variables['background']};
            border-bottom-color: transparent;
        }}

        QTabBar::tab:!selected {{
            margin-top: 2px;
        }}

        /* Dialog buttons */
        QDialogButtonBox > QPushButton {{
            min-width: 80px;
        }}
    """

    # Set the global stylesheet
    APP_STYLESHEET = common_css
    return APP_STYLESHEET


def toggle_theme():
    """Toggle between light and dark theme."""
    global APP_STYLE

    if APP_STYLE == 'light':
        new_style = 'dark'
    else:
        new_style = 'light'

    # Save preference to config
    save_theme_preference(new_style)

    # Apply new stylesheet
    stylesheet = load_stylesheet(new_style)
    QApplication.instance().setStyleSheet(stylesheet)


def save_theme_preference(theme):
    """Save theme preference to config file."""
    config_path = resource_path('config.json')

    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
        else:
            config = {}

        config['theme'] = theme

        with open(config_path, 'w') as config_file:
            json.dump(config, config_file, indent=4)

    except Exception as e:
        logger.error(f"Error saving theme preference: {e}")


def get_theme_preference():
    """Get theme preference from config file."""
    config_path = resource_path('config.json')

    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as config_file:
                config = json.load(config_file)
                return config.get('theme', 'light')
    except Exception as e:
        logger.error(f"Error reading theme preference: {e}")

    return 'light'  # Default theme


def apply_high_dpi_scaling():
    """Configure high DPI scaling for the application."""
    # Enable high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def check_dependencies():
    """Check if required dependencies are available."""
    # Check FFmpeg availability
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        ffmpeg_available = result.returncode == 0
    except:
        ffmpeg_available = False

    # Check PyAudio
    try:
        import pyaudio
        pyaudio_available = True
    except ImportError:
        pyaudio_available = False

    return {
        'ffmpeg': ffmpeg_available,
        'pyaudio': pyaudio_available
    }


def check_cuda_availability():
    """Check if CUDA is available and return GPU info."""
    try:
        import torch
        cuda_available = torch.cuda.is_available()

        if cuda_available:
            gpu_count = torch.cuda.device_count()
            gpu_info = []

            for i in range(gpu_count):
                gpu_name = torch.cuda.get_device_name(i)
                gpu_info.append(f"  • {gpu_name}")

            return True, gpu_info
        else:
            return False, []
    except:
        return False, []


def create_splash_screen():
    """Create a splash screen with progress bar."""
    splash_pixmap = QPixmap(resource_path('./icons/splash.png'))
    if splash_pixmap.isNull():
        # Create a default splash screen if image not found
        splash_pixmap = QPixmap(400, 300)
        splash_pixmap.fill(Qt.GlobalColor.white)

    splash = QSplashScreen(splash_pixmap, Qt.WindowType.WindowStaysOnTopHint)

    # Create a widget to overlay on the splash screen
    overlay = QWidget(splash)
    layout = QVBoxLayout(overlay)

    # Add app name
    app_name = QLabel("Transcribrr")
    app_name.setStyleSheet("font-size: 22px; font-weight: bold; color: #333;")
    app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(app_name)

    # Add version
    version = QLabel("v1.0.0")
    version.setStyleSheet("font-size: 12px; color: #666;")
    version.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(version)

    # Add progress bar
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setTextVisible(False)
    progress.setFixedHeight(10)
    layout.addWidget(progress)

    # Add status label
    status = QLabel("Initializing...")
    status.setStyleSheet("font-size: 10px; color: #666;")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(status)

    # Position the overlay
    overlay.setGeometry(10, splash_pixmap.height() - 120, splash_pixmap.width() - 20, 100)

    return splash, progress, status


def initialize_app():
    """Initialize the application with proper error handling."""
    try:
        # Enable high DPI scaling
        apply_high_dpi_scaling()

        # Create application
        app = QApplication(sys.argv)
        app.setApplicationName("Transcribrr")
        app.setApplicationVersion("1.0.0")
        app.setWindowIcon(QIcon(resource_path('./icons/app_icon.png')))

        # Create splash screen
        splash, progress_bar, status_label = create_splash_screen()
        splash.show()

        # Update splash screen
        def update_splash(value, message):
            status_label.setText(message)
            progress_bar.setValue(value)
            app.processEvents()

        # Process events to show splash screen
        app.processEvents()

        # Initialization steps
        update_splash(10, "Checking dependencies...")
        dependencies = check_dependencies()

        update_splash(20, "Checking CUDA availability...")
        cuda_available, gpu_info = check_cuda_availability()

        update_splash(30, "Cleaning temporary files...")
        cleanup_temp_files()

        update_splash(40, "Creating necessary directories...")
        os.makedirs(os.path.join(os.getcwd(), 'Recordings'), exist_ok=True)

        update_splash(50, "Loading configuration...")
        theme = get_theme_preference()
        stylesheet = load_stylesheet(theme)
        app.setStyleSheet(stylesheet)

        update_splash(70, "Initializing main window...")
        main_window = MainWindow()

        # Check for critical dependencies
        if not dependencies['ffmpeg']:
            QMessageBox.warning(main_window, "Missing Dependency",
                                "FFmpeg is not installed or not in PATH. Some features may not work properly.")

        if not dependencies['pyaudio']:
            QMessageBox.warning(main_window, "Missing Dependency",
                                "PyAudio is not properly installed. Recording functionality may not work.")

        # Log system information
        logger.info(f"Application started")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"CUDA available: {cuda_available}")
        if gpu_info:
            logger.info("GPU Information:")
            for gpu in gpu_info:
                logger.info(gpu)

        update_splash(90, "Ready to start...")

        # Add delay for splash screen to be visible
        QTimer.singleShot(1500, lambda: (
            update_splash(100, "Starting application..."),
            QTimer.singleShot(500, lambda: (
                main_window.show(),
                splash.finish(main_window)
            ))
        ))

        return app, main_window

    except Exception as e:
        # Show error message in case of critical failure
        error_message = f"Failed to initialize application: {str(e)}\n\n{traceback.format_exc()}"
        logger.critical(error_message)

        # Try to show error dialog, fallback to print if QApplication not initialized
        try:
            if QApplication.instance():
                QMessageBox.critical(None, "Critical Error", error_message)
            else:
                app = QApplication(sys.argv)
                QMessageBox.critical(None, "Critical Error", error_message)
        except:
            print(error_message)

        sys.exit(1)


def main():
    try:
        # Initialize application
        app, main_window = initialize_app()

        # Run application main loop
        return app.exec()

    except Exception as e:
        # Handle any uncaught exceptions
        error_message = f"Unhandled exception: {str(e)}\n\n{traceback.format_exc()}"
        logger.critical(error_message)

        # Try to show error dialog
        try:
            if QApplication.instance():
                QMessageBox.critical(None, "Unhandled Error", error_message)
        except:
            print(error_message)

        return 1


if __name__ == "__main__":
    sys.exit(main())