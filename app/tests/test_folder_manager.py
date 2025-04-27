"""
Unit tests for FolderManager singleton pattern and dependency injection.

This test suite verifies the behavior of the refactored FolderManager.instance() method,
specifically focusing on:
- Singleton property (returning the same instance on multiple calls)
- Dependency attachment during initialization
- Error handling for premature calls
- Re-attachment behavior
"""

import unittest
import logging
from unittest.mock import Mock, patch
import threading

from app.FolderManager import FolderManager
from app.DatabaseManager import DatabaseManager


class TestFolderManagerSingleton(unittest.TestCase):
    """Test suite for FolderManager singleton behavior."""

    def setUp(self):
        """Set up the test environment."""
        # Create a mock db_manager for testing
        self.db_manager = Mock(spec=DatabaseManager)
        self.db_manager.execute_query = Mock()

        # Capture log messages
        self.log_capture = []
        self.log_handler = self._create_log_handler()
        self.logger = logging.getLogger("transcribrr")
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Clean up test environment."""
        # Reset the singleton state between tests
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Remove the log handler
        if self.log_handler in self.logger.handlers:
            self.logger.removeHandler(self.log_handler)
        self.log_capture.clear()

    def _create_log_handler(self):
        """Create a log handler that captures log messages."""
        log_capture = self.log_capture

        class TestLogHandler(logging.Handler):
            def emit(self, record):
                log_capture.append(record.getMessage())

        return TestLogHandler()

    def test_singleton_property(self):
        """Verify that multiple calls return the same instance."""
        # Get the first instance
        instance1 = FolderManager.instance(db_manager=self.db_manager)

        # Get a second instance
        instance2 = FolderManager.instance()

        # Verify they are the same object
        self.assertIs(
            instance1,
            instance2,
            "Multiple calls to instance() should return the same object",
        )

    def test_successful_first_attachment(self):
        """Test successful dependency attachment on first call."""
        # Get instance with dependency injection
        instance = FolderManager.instance(db_manager=self.db_manager)

        # Verify the db_manager is attached
        self.assertEqual(
            instance.db_manager,
            self.db_manager,
            "db_manager should be attached to the instance",
        )

        # Verify the _db_manager_attached flag is set
        self.assertTrue(
            FolderManager._db_manager_attached,
            "_db_manager_attached flag should be True after attachment",
        )

    def test_successful_subsequent_call(self):
        """Test successful call after attachment."""
        # First call with db_manager
        instance1 = FolderManager.instance(db_manager=self.db_manager)

        # Subsequent call without db_manager
        instance2 = FolderManager.instance()

        # Verify they are the same object
        self.assertIs(
            instance1, instance2, "Subsequent calls should return the same instance"
        )

        # Verify the db_manager is still attached
        self.assertEqual(
            instance2.db_manager, self.db_manager, "db_manager should remain attached"
        )

    def test_failure_before_attachment(self):
        """Test that calling instance() before attachment raises RuntimeError."""
        # Reset singleton state to ensure clean test
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Call instance() without db_manager should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            FolderManager.instance()

        # Verify the error message
        self.assertIn(
            "DatabaseManager",
            str(context.exception),
            "Error message should mention DatabaseManager requirement",
        )

    def test_reattachment_warning(self):
        """Test that attempting to re-attach a different db_manager logs a warning."""
        # First create and attach a db_manager
        instance1 = FolderManager.instance(db_manager=self.db_manager)

        # Create a different mock db_manager
        different_db_manager = Mock(spec=DatabaseManager)
        different_db_manager.execute_query = Mock()

        # Try to attach a different db_manager
        instance2 = FolderManager.instance(db_manager=different_db_manager)

        # Verify it's the same instance
        self.assertIs(
            instance1, instance2, "Should return the same instance regardless"
        )

        # Verify the original db_manager is still attached
        self.assertEqual(
            instance2.db_manager,
            self.db_manager,
            "Original db_manager should remain attached",
        )

        # Verify a warning was logged
        warning_logged = any(
            "Different DatabaseManager" in msg for msg in self.log_capture
        )
        self.assertTrue(
            warning_logged, "A warning should be logged when attempting to re-attach"
        )

    def test_thread_safety(self):
        """Test that the singleton initialization is thread-safe."""
        # Reset singleton state
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Shared results for thread operations
        results = {"instances": []}

        def create_instance():
            instance = FolderManager.instance(db_manager=self.db_manager)
            results["instances"].append(instance)

        # Create multiple threads that will all try to initialize the singleton
        threads = [threading.Thread(target=create_instance) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check that all threads got the same instance
        first_instance = results["instances"][0]
        for instance in results["instances"][1:]:
            self.assertIs(
                instance, first_instance, "All threads should get the same instance"
            )

    def test_direct_instantiation_prevention(self):
        """Test that direct instantiation after singleton is created raises an error."""
        # First create the singleton instance
        FolderManager.instance(db_manager=self.db_manager)

        # Now try to create a new instance directly
        with self.assertRaises(RuntimeError) as context:
            FolderManager()

        # Verify the error message
        self.assertIn(
            "singleton",
            str(context.exception).lower(),
            "Error message should mention singleton",
        )

    def test_init_database_called_on_attachment(self):
        """Test that init_database is called when db_manager is attached."""
        # Create a subclass with mocked methods for verification
        with patch.object(FolderManager, "init_database") as mock_init_db:
            with patch.object(FolderManager, "load_folders") as mock_load_folders:
                # Initialize with db_manager
                instance = FolderManager.instance(db_manager=self.db_manager)

                # Verify init_database was called
                mock_init_db.assert_called_once()

                # Verify load_folders was called
                mock_load_folders.assert_called_once()


if __name__ == "__main__":
    unittest.main()
