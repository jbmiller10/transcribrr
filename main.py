import sys
import os
import logging
import json
import traceback
from typing import Tuple, Dict, Any, List, Optional
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QSplashScreen, QVBoxLayout,
    QLabel, QProgressBar, QWidget, QStyleFactory
)
from PyQt6.QtGui import QPixmap, QFont, QIcon, QColor
from PyQt6.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal, QRect
from PyQt6.QtSvg import QSvgRenderer
from app.MainWindow import MainWindow
from app.utils import resource_path, check_system_requirements, cleanup_temp_files, ConfigManager
from app.ThemeManager import ThemeManager
from app.ResponsiveUI import ResponsiveUIManager, ResponsiveEventFilter
from app.services.transcription_service import ModelManager

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
os.makedirs(os.path.join(os.getcwd(), 'database'), exist_ok=True)

# Global variable to keep reference to the startup thread
startup_thread = None


class StartupThread(QThread):
    """Background thread for startup operations to keep UI responsive during loading."""
    update_progress = pyqtSignal(int, str)
    initialization_done = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self):
        super().__init__()

    def run(self) -> None:
        """Run the initialization process."""
        try:
            # Check dependencies first
            self.update_progress.emit(10, "Checking dependencies...")
            dependencies = self.check_dependencies()

            # Check CUDA availability
            self.update_progress.emit(20, "Checking CUDA availability...")
            cuda_result = self.check_cuda_availability()

            # Clean up temporary files
            self.update_progress.emit(30, "Cleaning temporary files...")
            cleanup_temp_files()

            # Create necessary directories
            self.update_progress.emit(40, "Setting up environment...")
            os.makedirs(os.path.join(os.getcwd(), 'Recordings'), exist_ok=True)
            os.makedirs(os.path.join(os.getcwd(), 'database'), exist_ok=True)
            
            # Initialize configuration manager
            self.update_progress.emit(50, "Loading configuration...")
            config_manager = ConfigManager.instance()
            config = config_manager.get_all()
            
            # Initialize theme manager with config
            self.update_progress.emit(60, "Setting up theme...")
            theme = config.get("theme", "light")
            ThemeManager.instance().apply_theme(theme)
            
            # Pre-initialize model manager without loading models
            self.update_progress.emit(70, "Initializing model manager...")
            model_manager = ModelManager.instance()
            
            # Initialize responsive UI manager
            self.update_progress.emit(80, "Setting up UI manager...")
            responsive_manager = ResponsiveUIManager.instance()
            
            # Check system requirements
            self.update_progress.emit(90, "Checking system requirements...")
            system_info = check_system_requirements()

            # Collect all initialization results
            init_results = {
                "dependencies": dependencies,
                "cuda": cuda_result,
                "system_info": system_info,
                "config": config
            }

            # Complete initialization
            self.update_progress.emit(100, "Ready to start...")
            self.initialization_done.emit(init_results)

        except Exception as e:
            error_msg = f"Initialization error: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            self.error.emit(error_msg)

    def check_dependencies(self) -> Dict[str, bool]:
        """
        Check if required dependencies are available.
        
        Returns:
            Dictionary of dependency availability
        """
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

    def check_cuda_availability(self) -> Tuple[bool, List[str]]:
        """
        Check if CUDA is available and return GPU info.
        
        Returns:
            Tuple of (CUDA available, GPU info list)
        """
        try:
            import torch
            cuda_available = torch.cuda.is_available()

            if cuda_available:
                gpu_count = torch.cuda.device_count()
                gpu_info = []

                for i in range(gpu_count):
                    gpu_name = torch.cuda.get_device_name(i)
                    gpu_memory = torch.cuda.get_device_properties(i).total_memory / (1024 ** 3)
                    gpu_info.append(f"  • {gpu_name} ({gpu_memory:.2f} GB)")

                return True, gpu_info
            else:
                mps_available = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
                if mps_available:
                    return False, ["  • Apple MPS acceleration available"]
                return False, []
        except Exception as e:
            logger.warning(f"Error checking CUDA: {e}")
            return False, []


def toggle_theme():
    """Toggle between light and dark theme."""
    # Use the ThemeManager to toggle the theme
    ThemeManager.instance().toggle_theme()


def apply_high_dpi_scaling():
    """Configure high DPI scaling for the application."""
    # Enable high DPI scaling
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


def create_splash_screen():
    """Create a splash screen with progress bar."""
    # Try to use the SVG splash image if available
    svg_path = resource_path('./icons/app/splash.svg')
    png_path = resource_path('./icons/app/splash.png')
    
    if os.path.exists(svg_path):
        # Render SVG to pixmap
        renderer = QSvgRenderer(svg_path)
        splash_pixmap = QPixmap(480, 320)
        splash_pixmap.fill(Qt.GlobalColor.transparent)
        # Create a painter on the pixmap
        from PyQt6.QtGui import QPainter
        painter = QPainter(splash_pixmap)
        renderer.render(painter)
        painter.end()
    elif os.path.exists(png_path):
        splash_pixmap = QPixmap(png_path)
    else:
        # Create a default splash screen if image not found
        splash_pixmap = QPixmap(480, 320)
        splash_pixmap.fill(Qt.GlobalColor.white)

    splash = QSplashScreen(splash_pixmap, Qt.WindowType.WindowStaysOnTopHint)

    # Create a widget to overlay on the splash screen
    overlay = QWidget(splash)
    layout = QVBoxLayout(overlay)

    # Add app name
    app_name = QLabel("Transcribrr")
    app_name.setStyleSheet("font-size: 24px; font-weight: bold; color: #3366CC;")
    app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(app_name)

    # Add version
    version = QLabel("v1.0.0")
    version.setStyleSheet("font-size: 14px; color: #555;")
    version.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(version)

    # Add progress bar
    progress = QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(0)
    progress.setTextVisible(False)
    progress.setFixedHeight(10)
    progress.setStyleSheet("""
        QProgressBar {
            border: 1px solid #AAA;
            border-radius: 5px;
            background-color: #F5F5F5;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #3366CC;
            border-radius: 4px;
        }
    """)
    layout.addWidget(progress)

    # Add status label
    status = QLabel("Initializing...")
    status.setStyleSheet("font-size: 12px; color: #555;")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(status)

    # Position the overlay
    overlay.setGeometry(QRect(40, 200, 400, 120))

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
        app.setWindowIcon(QIcon(resource_path('./icons/app/app_icon.svg')))

        # Initialize and apply theme using ThemeManager
        theme_manager = ThemeManager.instance()

        # Initialize the responsive UI manager
        responsive_manager = ResponsiveUIManager.instance()
        
        # Create an event filter to handle window resize events
        responsive_event_filter = ResponsiveEventFilter()
        app.installEventFilter(responsive_event_filter)

        # Create splash screen
        splash, progress_bar, status_label = create_splash_screen()
        splash.show()

        # Function to update splash screen
        def update_splash(value, message):
            if not splash.isVisible():
                return
            status_label.setText(message)
            progress_bar.setValue(value)
            app.processEvents()

        # Process events to show splash screen
        app.processEvents()

        # Create main window instance (but don't show it yet)
        main_window = MainWindow()
        
        # Set initial size for responsive UI manager
        responsive_manager.update_size(main_window.width(), main_window.height())

        # Initialize background startup thread
        global startup_thread
        startup_thread = StartupThread()
        startup_thread.update_progress.connect(update_splash)
        startup_thread.initialization_done.connect(lambda results: on_initialization_done(results, main_window, splash))
        startup_thread.error.connect(lambda msg: on_initialization_error(msg, main_window, splash))
        startup_thread.start()

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


def on_initialization_done(results: Dict[str, Any], main_window: MainWindow, splash: QSplashScreen) -> None:
    """
    Handle successful initialization.
    
    Args:
        results: Initialization results
        main_window: Main application window
        splash: Splash screen
    """
    # Check for critical dependencies
    if not results["dependencies"]["ffmpeg"]:
        QMessageBox.warning(main_window, "Missing Dependency",
                          "FFmpeg is not installed or not in PATH. Some features may not work properly.")

    if not results["dependencies"]["pyaudio"]:
        QMessageBox.warning(main_window, "Missing Dependency",
                          "PyAudio is not properly installed. Recording functionality may not work.")

    # Set application theme from config
    if "config" in results:
        theme = results["config"].get("theme", "light")
        ThemeManager.instance().apply_theme(theme)
        
        # Log configuration information
        logger.info(f"Loaded configuration with {len(results['config'])} settings")
        logger.info(f"Theme: {theme}")
        logger.info(f"Transcription model: {results['config'].get('transcription_quality', 'Not set')}")
        logger.info(f"Transcription method: {results['config'].get('transcription_method', 'local')}")

    # Log system information
    logger.info(f"Application started")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"CUDA available: {results['cuda'][0]}")
    if results['cuda'][1]:
        logger.info("GPU Information:")
        for gpu in results['cuda'][1]:
            logger.info(gpu)

    # Show the main window and close the splash screen
    QTimer.singleShot(800, lambda: (
        main_window.show(),
        splash.finish(main_window)
    ))


def on_initialization_error(error_message, main_window, splash):
    """Handle initialization errors."""
    # Close splash screen
    splash.close()
    
    # Show error message
    QMessageBox.critical(main_window, "Initialization Error", 
                        f"There was a problem initializing the application:\n\n{error_message}")
    
    # Show main window anyway
    main_window.show()


def main():
    # Keep a reference to the startup thread to prevent early destruction
    global startup_thread
    
    try:
        # Initialize application
        app, main_window = initialize_app()
        
        # Register cleanup for application exit
        app.aboutToQuit.connect(cleanup_application)
        
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

        # Make sure to clean up threads
        cleanup_application()
        
        return 1

def cleanup_application():
    """Clean up any resources before application exit."""
    logger.info("Cleaning up application resources...")
    
    # Release model resources
    try:
        ModelManager.instance().release_memory()
        logger.info("Released model resources")
    except Exception as e:
        logger.error(f"Error releasing model resources: {e}")
    
    # Wait for the startup thread to finish if it's still running
    global startup_thread
    if startup_thread and startup_thread.isRunning():
        logger.info("Waiting for startup thread to finish...")
        startup_thread.wait(2000)  # Wait up to 2 seconds
        
        # Force quit if still running
        if startup_thread.isRunning():
            logger.warning("Terminating startup thread...")
            startup_thread.terminate()
            startup_thread.wait(1000)
            
    # Save any pending configuration changes
    try:
        config = ConfigManager.instance().get_all()
        logger.info(f"Saved configuration with {len(config)} settings")
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")


if __name__ == "__main__":
    sys.exit(main())