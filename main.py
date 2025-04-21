import sys
import os
import logging
import json
import traceback
import warnings
from typing import Tuple, Dict, Any, List, Optional

# Filter urllib3 LibreSSL warning
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+, currently the 'ssl' module is compiled with")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QMessageBox, QSplashScreen, QVBoxLayout,
    QLabel, QProgressBar, QWidget, QStyleFactory
)
from PyQt6.QtGui import QPixmap, QFont, QIcon, QColor
from PyQt6.QtCore import Qt, QTimer, QSize, QThread, pyqtSignal, pyqtSlot, QRect
from PyQt6.QtSvg import QSvgRenderer
from app.MainWindow import MainWindow
from app.path_utils import resource_path
from app.utils import check_system_requirements, cleanup_temp_files, ConfigManager, ensure_ffmpeg_available
from app.ThemeManager import ThemeManager
from app.ResponsiveUI import ResponsiveUIManager, ResponsiveEventFilter
from app.services.transcription_service import ModelManager
from app.ThreadManager import ThreadManager

# Import constants for paths
from app.constants import LOG_FORMAT, LOG_DIR, LOG_FILE, RECORDINGS_DIR, DATABASE_DIR, APP_NAME, USER_DATA_DIR

# Configure logging - now all paths come from constants
# Root logging may have been configured by app.utils already (imported by
# many modules).  Add handlers only if not present to avoid duplicate log
# lines.

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE),
        ],
    )

# Now get the application‑level logger
logger = logging.getLogger(APP_NAME)
logger.info(f"Application starting. User data directory: {USER_DATA_DIR}")

# Directories are already created in constants.py, no need to recreate them here

# Global variable to keep reference to the startup thread
startup_thread = None


class StartupThread(QThread):
    """Background thread for startup operations to keep UI responsive during loading."""
    update_progress = pyqtSignal(int, str)
    initialization_done = pyqtSignal(dict)
    error = pyqtSignal(str)
    apply_theme = pyqtSignal(str)
    apply_responsive_ui = pyqtSignal(dict)

    def __init__(self):
        super().__init__()

    def run(self) -> None:
        """Run the initialization process."""
        try:
            self.update_progress.emit(10, "Checking dependencies...")
            dependencies = self.check_dependencies()

            self.update_progress.emit(20, "Checking CUDA availability...")
            cuda_result = self.check_cuda_availability()

            self.update_progress.emit(30, "Cleaning temporary files...")
            cleanup_temp_files()

            self.update_progress.emit(40, "Verifying environment...")
            # Log directory locations
            from app.constants import RESOURCE_DIR, USER_DATA_DIR, RECORDINGS_DIR, DATABASE_DIR, LOG_DIR
            logger.info(f"Resource directory: {os.path.join(RESOURCE_DIR)}")
            logger.info(f"User data directory: {os.path.join(USER_DATA_DIR)}")
            logger.info(f"Recordings directory: {os.path.join(RECORDINGS_DIR)}")
            logger.info(f"Database directory: {os.path.join(DATABASE_DIR)}")
            logger.info(f"Log directory: {os.path.join(LOG_DIR)}") 
            # Directories are already created in constants.py
            
            # Initialize configuration manager
            self.update_progress.emit(50, "Loading configuration...")
            config_manager = ConfigManager.instance()
            config = config_manager.get_all()
            
            # Signal to initialize theme manager with config (don't call directly from thread)
            self.update_progress.emit(60, "Setting up theme...")
            theme = config.get("theme", "light")
            # Emit signal for GUI thread to apply theme
            self.apply_theme.emit(theme)
            
            # Pre-initialize model manager without loading models
            self.update_progress.emit(70, "Initializing model manager...")
            model_manager = ModelManager.instance()
            
            # Initialize responsive UI manager via signal
            self.update_progress.emit(80, "Setting up UI manager...")
            # Don't create the responsive manager in the worker thread
            # Just send a signal with the parameters for the main thread to handle
            # We'll emit with dummy size values first - real ones will be set in on_initialization_done
            self.apply_responsive_ui.emit({"width": 1024, "height": 768})
            
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
        # Check FFmpeg availability using our enhanced function
        ffmpeg_available, ffmpeg_message = ensure_ffmpeg_available()
        logger.info(f"FFmpeg check: {ffmpeg_message}")

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
    
    logger.debug(f"Splash SVG path: {svg_path}")
    logger.debug(f"Splash PNG path: {png_path}")
    
    try:
        if os.path.exists(svg_path):
            # Render SVG to pixmap
            logger.debug("Creating splash screen from SVG")
            renderer = QSvgRenderer(svg_path)
            splash_pixmap = QPixmap(480, 320)
            splash_pixmap.fill(Qt.GlobalColor.transparent)
            # Create a painter on the pixmap
            from PyQt6.QtGui import QPainter
            painter = QPainter(splash_pixmap)
            renderer.render(painter)
            painter.end()
        elif os.path.exists(png_path):
            logger.debug("Creating splash screen from PNG")
            splash_pixmap = QPixmap(png_path)
        else:
            # Create a default splash screen if image not found
            logger.warning("Splash image not found, using default")
            splash_pixmap = QPixmap(480, 320)
            splash_pixmap.fill(Qt.GlobalColor.white)
    except Exception as e:
        logger.error(f"Error creating splash pixmap: {e}")
        # Fallback to a plain splash screen
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


@pyqtSlot(str)
def apply_theme_main_thread(theme):
    """Apply theme on the main thread"""
    logger.info(f"Applying theme on main thread: {theme}")
    ThemeManager.instance().apply_theme(theme)

@pyqtSlot(dict)
def apply_responsive_ui_main_thread(ui_params):
    """Apply responsive UI settings on the main thread"""
    width = ui_params.get("width", 1024)
    height = ui_params.get("height", 768)
    logger.info(f"Applying responsive UI on main thread: {width}x{height}")
    # Fetch the singleton in the main thread
    responsive_manager = ResponsiveUIManager.instance()
    responsive_manager.update_size(width, height)

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

        # Initialize theme manager (defer applying theme until we're signaled)
        theme_manager = ThemeManager.instance()

        # Initialize the responsive UI manager (defer applying until we're signaled)
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

        # Initialize background startup thread
        global startup_thread
        startup_thread = StartupThread()
        
        # Connect signals to main thread handlers
        startup_thread.update_progress.connect(update_splash)
        startup_thread.initialization_done.connect(lambda results: on_initialization_done(results, main_window, splash))
        startup_thread.error.connect(lambda msg: on_initialization_error(msg, main_window, splash))
        startup_thread.apply_theme.connect(apply_theme_main_thread)
        startup_thread.apply_responsive_ui.connect(apply_responsive_ui_main_thread)
        
        # Register with ThreadManager before starting
        ThreadManager.instance().register_thread(startup_thread)
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


@pyqtSlot(dict)
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

    # Log configuration information
    if "config" in results:
        logger.info(f"Loaded configuration with {len(results['config'])} settings")
        logger.info(f"Theme: {results['config'].get('theme', 'light')}")
        logger.info(f"Transcription model: {results['config'].get('transcription_quality', 'Not set')}")
        logger.info(f"Transcription method: {results['config'].get('transcription_method', 'local')}")

    # Apply responsive UI sizing on the main thread
    if main_window:
        # Apply responsive UI scaling based on main window dimensions
        responsive_manager = ResponsiveUIManager.instance()
        responsive_manager.update_size(main_window.width(), main_window.height())

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


@pyqtSlot(str)
def on_initialization_error(error_message, main_window, splash):
    """Handle initialization errors."""
    # Close splash screen
    splash.close()
    
    # Show error message
    QMessageBox.critical(main_window, "Initialization Error", 
                        f"There was a problem initializing the application:\n\n{error_message}")
    
    # Show main window anyway
    main_window.show()


def copy_initial_data_files():
    """Copy default configuration and preset files to user data directory on first run"""
    from app.constants import USER_DATA_DIR, RESOURCE_DIR, CONFIG_PATH, PROMPTS_PATH
    from app.path_utils import resource_path
    import shutil
    
    # Check if running in a bundled app
    is_frozen = getattr(sys, 'frozen', False)
    
    if is_frozen:
        # Use resource_path to get the correct resource directory
        resource_dir = resource_path()
            
        # Copy config.json if it doesn't exist in user data directory
        if not os.path.exists(CONFIG_PATH):
            source_config = os.path.join(resource_dir, 'config.json')
            if os.path.exists(source_config):
                logger.info(f"Copying default config.json to {CONFIG_PATH}")
                shutil.copy2(source_config, CONFIG_PATH)
            else:
                logger.warning(f"Default config.json not found at {source_config}")
                
        # Copy preset_prompts.json if it doesn't exist in user data directory
        if not os.path.exists(PROMPTS_PATH):
            source_prompts = os.path.join(resource_dir, 'preset_prompts.json')
            if os.path.exists(source_prompts):
                logger.info(f"Copying default preset_prompts.json to {PROMPTS_PATH}")
                shutil.copy2(source_prompts, PROMPTS_PATH)
            else:
                logger.warning(f"Default preset_prompts.json not found at {source_prompts}")


def main():
    # Keep a reference to the startup thread to prevent early destruction
    global startup_thread
    
    try:
        # Log startup information
        is_frozen = getattr(sys, 'frozen', False)
        is_pyinstaller = hasattr(sys, '_MEIPASS')
        is_py2app = is_frozen and 'MacOS' in sys.executable
        
        logger.info(f"Starting application: Frozen = {is_frozen}, PyInstaller = {is_pyinstaller}, py2app = {is_py2app}")
        logger.info(f"Working directory: {os.getcwd()}")
        # Import constants directly instead of through app
        from app.constants import USER_DATA_DIR, RESOURCE_DIR
        logger.info(f"User data directory: {USER_DATA_DIR}")
        logger.info(f"Resource directory: {RESOURCE_DIR}")
        
        # Copy default configuration files on first run
        copy_initial_data_files()
        
        # Check if critical files exist after potential copying
        # Use constants directly
        from app.constants import CONFIG_PATH, PROMPTS_PATH
        config_exists = os.path.exists(CONFIG_PATH)
        prompts_exists = os.path.exists(PROMPTS_PATH)
        logger.info(f"Config file exists in user data dir: {config_exists}")
        logger.info(f"Prompts file exists in user data dir: {prompts_exists}")
        
        # Initialize application
        app, main_window = initialize_app()
        
        # Register cleanup for application exit
        app.aboutToQuit.connect(cleanup_application)
        
        # Run application main loop
        logger.info("Starting application main loop")
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
    
    # Use ThreadManager to cancel all active threads
    thread_manager = ThreadManager.instance()
    thread_manager.cancel_all_threads(wait_timeout=1000)
    
    # Get any threads that didn't respond to cancellation
    threads_to_terminate = []
    for thread in thread_manager.get_active_threads():
        if thread.isRunning():
            threads_to_terminate.append(thread)
    
    # Force terminate any threads that didn't respond to cancellation
    for thread in threads_to_terminate:
        try:
            logger.warning(f"Terminating thread {thread.__class__.__name__} that didn't respond to cancellation...")
            thread.terminate()
            thread.wait(500)  # Brief wait after terminate
        except Exception as e:
            logger.error(f"Error terminating thread {thread.__class__.__name__}: {e}")
    
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