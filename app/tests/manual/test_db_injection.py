#!/usr/bin/env python3
"""
Manual test to verify that DatabaseManager instance is properly injected into FolderManager.
This test should be run manually and is not part of the automated test suite.
"""

import sys
import threading
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from app.FolderManager import FolderManager
from app.DatabaseManager import DatabaseManager
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    # Create QApplication first
    app = QApplication(sys.argv)

    logger.info("Creating DatabaseManager")
    db_manager = DatabaseManager()

    logger.info(f"Initial thread count: {len(threading.enumerate())}")
    logger.info(f"Thread names: {[t.name for t in threading.enumerate()]}")

    # Create and attach the FolderManager
    logger.info("Creating FolderManager")
    folder_manager = FolderManager()

    logger.info("Attaching DatabaseManager to FolderManager")
    folder_manager.attach_db_manager(db_manager)

    # Get the instance
    logger.info("Getting FolderManager instance")
    fm_instance = FolderManager.instance(db_manager=db_manager)

    # Check threads and QThread status
    logger.info(f"Thread count after initialization: {len(threading.enumerate())}")
    logger.info(f"Thread names: {[t.name for t in threading.enumerate()]}")
    logger.info(f"DatabaseWorker thread running: {db_manager.worker.isRunning()}")

    # Make a database operation to test the worker thread
    test_results = []

    def on_query_complete(result):
        test_results.append(result)
        logger.info(f"Query completed: {result}")

        # Check results
        logger.info(f"Query results: {test_results}")

        # Check threads again
        logger.info(f"Thread count after query: {len(threading.enumerate())}")
        logger.info(f"Thread names: {[t.name for t in threading.enumerate()]}")
        logger.info(f"DatabaseWorker thread running: {db_manager.worker.isRunning()}")

        # Clean shutdown
        logger.info("Shutting down DatabaseManager")
        db_manager.shutdown()

        logger.info(f"Final thread count: {len(threading.enumerate())}")
        logger.info(f"Final thread names: {[t.name for t in threading.enumerate()]}")

        # Quit the application
        app.quit()

    logger.info("Executing test database query")
    db_manager.execute_query(
        "SELECT COUNT(*) FROM sqlite_master", callback=on_query_complete
    )

    # Set up a timeout in case the query never completes
    def timeout_handler():
        logger.error("Test timed out - query did not complete")
        app.quit()

    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(timeout_handler)
    timeout_timer.start(5000)  # 5 second timeout

    # Run the event loop
    logger.info("Starting Qt event loop")
    app.exec()

    logger.info("Test completed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
