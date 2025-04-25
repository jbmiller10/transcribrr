"""
Unit tests for DatabaseManager and DatabaseWorker classes.
"""

import os
import sys
import unittest
import tempfile
import sqlite3
from unittest.mock import Mock, patch, MagicMock, call
from PyQt6.QtCore import QApplication, QEventLoop, QTimer, QObject, pyqtSignal, QThread

# Import the modules to be tested
from app.DatabaseManager import DatabaseManager, DatabaseWorker
import app.constants
from app.db_utils import (
    get_connection, create_recordings_table, create_folders_table,
    create_recording_folders_table
)

class TestDatabaseWorker(unittest.TestCase):
    """Test suite for the DatabaseWorker class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # Create a temporary file for the test database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='.sqlite')
        
        # Save the original database path
        cls.original_db_path = app.constants.DATABASE_PATH
        # Override the database path for testing
        app.constants.DATABASE_PATH = cls.temp_db_path
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment after all tests."""
        # Restore the original database path
        app.constants.DATABASE_PATH = cls.original_db_path
        
        # Close and remove the temporary database file
        os.close(cls.temp_db_fd)
        if os.path.exists(cls.temp_db_path):
            os.unlink(cls.temp_db_path)
    
    def setUp(self):
        """Set up before each test."""
        # Create a new worker for each test
        self.worker = DatabaseWorker()
        
        # Create test database tables
        self.conn = get_connection()
        create_recordings_table(self.conn)
        create_folders_table(self.conn)
        create_recording_folders_table(self.conn)
    
    def tearDown(self):
        """Clean up after each test."""
        # Stop the worker
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            
        # Close connection
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
            
        # Clean up database for next test
        if os.path.exists(self.temp_db_path):
            # We'll recreate tables in setUp, no need to delete the file
            pass
    
    def wait_for_worker_operations(self, timeout=1000):
        """Helper to wait for worker operations to complete."""
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout)  # 1 second timeout
        
        # Check if the queue is empty periodically
        def check_queue():
            if self.worker.operations_queue.empty():
                loop.quit()
        
        check_timer = QTimer()
        check_timer.timeout.connect(check_queue)
        check_timer.start(50)  # Check every 50ms
        
        loop.exec()
        check_timer.stop()
        timer.stop()
    
    def test_worker_starts_and_stops_cleanly(self):
        """Test that the worker thread starts and can be stopped via shutdown()."""
        # Start the worker
        self.worker.start()
        self.assertTrue(self.worker.isRunning(), "Worker thread should be running after start()")
        self.assertTrue(self.worker.running, "Worker running flag should be True after start()")
        
        # Stop the worker
        self.worker.stop()
        self.worker.wait(1000)  # Wait up to 1 second for the thread to stop
        self.assertFalse(self.worker.isRunning(), "Worker thread should not be running after stop()")
        self.assertFalse(self.worker.running, "Worker running flag should be False after stop()")
    
    def test_worker_processes_queued_operations(self):
        """Test that the worker processes operations from the queue."""
        # Mock the operation_complete signal
        self.worker.operation_complete = Mock()
        
        # Start the worker
        self.worker.start()
        
        # Add an operation to the queue
        op_id = "test_op"
        self.worker.add_operation('execute_query', op_id, "SELECT 1", [])
        
        # Wait for the operation to be processed
        self.wait_for_worker_operations()
        
        # Check that the operation_complete signal was emitted with the correct result
        self.worker.operation_complete.emit.assert_called_with({
            'id': op_id,
            'type': 'execute_query',
            'result': [(1,)]
        })
        
        # Clean up
        self.worker.stop()
        self.worker.wait()
    
    def test_worker_handles_empty_queue(self):
        """Test that the worker handles periods with no operations gracefully."""
        # Start the worker
        self.worker.start()
        
        # Wait a bit to ensure the worker is idle
        QThread.msleep(200)
        
        # Add an operation after the idle period
        self.worker.operation_complete = Mock()
        op_id = "test_op_after_idle"
        self.worker.add_operation('execute_query', op_id, "SELECT 1", [])
        
        # Wait for the operation to be processed
        self.wait_for_worker_operations()
        
        # Check that the operation was processed correctly
        self.worker.operation_complete.emit.assert_called_with({
            'id': op_id,
            'type': 'execute_query',
            'result': [(1,)]
        })
        
        # Clean up
        self.worker.stop()
        self.worker.wait()
    
    def test_worker_emits_operation_complete(self):
        """Test that the worker emits the operation_complete signal with the correct ID and result."""
        # Create a signal spy
        result_data = []
        
        def on_operation_complete(result):
            result_data.append(result)
        
        # Connect the signal
        self.worker.operation_complete.connect(on_operation_complete)
        
        # Start the worker
        self.worker.start()
        
        # Add an operation
        op_id = "test_emit_complete"
        self.worker.add_operation('execute_query', op_id, "SELECT 1", [])
        
        # Wait for the operation to complete
        self.wait_for_worker_operations()
        
        # Check the result
        self.assertEqual(len(result_data), 1, "Should have received one result")
        self.assertEqual(result_data[0]['id'], op_id, "Operation ID should match")
        self.assertEqual(result_data[0]['type'], 'execute_query', "Operation type should match")
        self.assertEqual(result_data[0]['result'], [(1,)], "Operation result should match")
        
        # Clean up
        self.worker.operation_complete.disconnect(on_operation_complete)
        self.worker.stop()
        self.worker.wait()
    
    def test_worker_emits_error_occurred(self):
        """Test that the worker emits the error_occurred signal when an operation fails."""
        # Create a signal spy
        error_data = []
        
        def on_error_occurred(op_type, error_msg):
            error_data.append((op_type, error_msg))
        
        # Connect the signal
        self.worker.error_occurred.connect(on_error_occurred)
        
        # Start the worker
        self.worker.start()
        
        # Add an operation that will fail (invalid SQL)
        self.worker.add_operation('execute_query', "test_error", "SELECT * FROM nonexistent_table", [])
        
        # Wait for the operation to complete
        self.wait_for_worker_operations()
        
        # Check the error
        self.assertEqual(len(error_data), 1, "Should have received one error")
        self.assertEqual(error_data[0][0], 'execute_query', "Operation type should match")
        self.assertTrue('no such table: nonexistent_table' in error_data[0][1].lower(), 
                      f"Error message should mention nonexistent table, got: {error_data[0][1]}")
        
        # Clean up
        self.worker.error_occurred.disconnect(on_error_occurred)
        self.worker.stop()
        self.worker.wait()
    
    def test_worker_emits_data_changed_on_write(self):
        """Test that the worker emits the dataChanged signal after successful write operations."""
        # Create a signal spy
        data_changed_count = 0
        
        def on_data_changed():
            nonlocal data_changed_count
            data_changed_count += 1
        
        # Connect the signal
        self.worker.dataChanged.connect(on_data_changed)
        
        # Start the worker
        self.worker.start()
        
        # Add a read operation (should not emit dataChanged)
        self.worker.add_operation('execute_query', "test_read", "SELECT 1", [])
        
        # Add a write operation (should emit dataChanged)
        self.worker.add_operation('execute_query', "test_write", 
                                 "CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)", [])
        
        # Wait for operations to complete
        self.wait_for_worker_operations()
        
        # Check that dataChanged was emitted only once (for the write operation)
        self.assertEqual(data_changed_count, 1, "dataChanged should have been emitted once")
        
        # Clean up
        self.worker.dataChanged.disconnect(on_data_changed)
        self.worker.stop()
        self.worker.wait()
    
    def test_worker_uses_transactions_for_writes(self):
        """Test that the worker uses transactions for write operations."""
        # Use a real database to test transactions
        self.worker.start()
        
        # Add a write operation that should be wrapped in a transaction
        test_data = "test_transaction_data"
        create_table_query = "CREATE TABLE IF NOT EXISTS test_transactions (id INTEGER PRIMARY KEY, data TEXT)"
        insert_query = "INSERT INTO test_transactions (data) VALUES (?)"
        
        # Create the table
        self.worker.add_operation('execute_query', "create_table", create_table_query, [])
        # Insert data
        self.worker.add_operation('execute_query', "insert_data", insert_query, [test_data])
        
        # Wait for operations to complete
        self.wait_for_worker_operations()
        
        # Check that the data was committed (transaction was successful)
        cursor = self.conn.cursor()
        cursor.execute("SELECT data FROM test_transactions")
        result = cursor.fetchone()
        self.assertIsNotNone(result, "Data should have been committed to the database")
        self.assertEqual(result[0], test_data, "Committed data should match inserted data")
        
        # Clean up
        self.worker.stop()
        self.worker.wait()
    
    def test_worker_handles_last_row_id(self):
        """Test that execute_query with return_last_row_id=True returns the last inserted ID."""
        # Create a signal spy
        result_data = []
        
        def on_operation_complete(result):
            result_data.append(result)
        
        # Connect the signal
        self.worker.operation_complete.connect(on_operation_complete)
        
        # Start the worker
        self.worker.start()
        
        # Create a test table and insert a row
        create_table_query = "CREATE TABLE IF NOT EXISTS test_last_id (id INTEGER PRIMARY KEY, data TEXT)"
        insert_query = "INSERT INTO test_last_id (data) VALUES (?)"
        
        # Create the table
        self.worker.add_operation('execute_query', "create_table", create_table_query, [])
        # Insert data with return_last_row_id=True
        self.worker.add_operation('execute_query', "insert_with_id", insert_query, ["test_data"], return_last_row_id=True)
        
        # Wait for operations to complete
        self.wait_for_worker_operations()
        
        # Find the insert operation result
        insert_result = None
        for result in result_data:
            if result['id'] == "insert_with_id":
                insert_result = result
                break
        
        # Check that we got the last row ID
        self.assertIsNotNone(insert_result, "Should have received insert operation result")
        self.assertEqual(insert_result['type'], 'execute_query', "Operation type should match")
        self.assertEqual(insert_result['result'], 1, "First inserted ID should be 1")
        
        # Clean up
        self.worker.operation_complete.disconnect(on_operation_complete)
        self.worker.stop()
        self.worker.wait()


class TestDatabaseManager(unittest.TestCase):
    """Test suite for the DatabaseManager class."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # Create a temporary file for the test database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='.sqlite')
        
        # Save the original database path
        cls.original_db_path = app.constants.DATABASE_PATH
        # Override the database path for testing
        app.constants.DATABASE_PATH = cls.temp_db_path
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment after all tests."""
        # Restore the original database path
        app.constants.DATABASE_PATH = cls.original_db_path
        
        # Close and remove the temporary database file
        os.close(cls.temp_db_fd)
        if os.path.exists(cls.temp_db_path):
            os.unlink(cls.temp_db_path)
    
    def setUp(self):
        """Set up before each test."""
        # Create a database manager for testing
        self.db_manager = DatabaseManager()
        
        # Wait for worker thread to start
        QThread.msleep(100)
    
    def tearDown(self):
        """Clean up after each test."""
        # Shutdown the database manager
        if hasattr(self, 'db_manager'):
            self.db_manager.shutdown()
    
    def wait_for_signals(self, timeout=1000):
        """Helper to wait for signals to be processed."""
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout)
        loop.exec()
        timer.stop()
    
    def test_manager_enqueues_operations_correctly(self):
        """Test that the manager enqueues operations correctly."""
        # Mock the worker's add_operation method
        self.db_manager.worker.add_operation = Mock()
        
        # Test create_recording
        recording_data = ("test.mp3", "/path/to/test.mp3", "2025-01-01 12:00:00", "00:05:00")
        callback = lambda x: None
        self.db_manager.create_recording(recording_data, callback)
        
        # Check that add_operation was called with the correct arguments
        self.db_manager.worker.add_operation.assert_called_with(
            'create_recording', 
            f"create_recording_{id(callback)}", 
            recording_data
        )
        
        # Reset the mock
        self.db_manager.worker.add_operation.reset_mock()
        
        # Test get_all_recordings
        self.db_manager.get_all_recordings(callback)
        self.db_manager.worker.add_operation.assert_called_with(
            'get_all_recordings',
            f"get_all_recordings_{id(callback)}"
        )
        
        # Reset the mock
        self.db_manager.worker.add_operation.reset_mock()
        
        # Test get_recording_by_id
        self.db_manager.get_recording_by_id(1, callback)
        self.db_manager.worker.add_operation.assert_called_with(
            'get_recording_by_id',
            f"get_recording_1_{id(callback)}",
            1
        )
        
        # Reset the mock
        self.db_manager.worker.add_operation.reset_mock()
        
        # Test update_recording
        self.db_manager.update_recording(1, callback, filename="updated.mp3")
        self.db_manager.worker.add_operation.assert_called_with(
            'update_recording',
            f"update_recording_1_{id(callback)}",
            1,
            filename="updated.mp3"
        )
        
        # Reset the mock
        self.db_manager.worker.add_operation.reset_mock()
        
        # Test delete_recording
        self.db_manager.delete_recording(1, callback)
        self.db_manager.worker.add_operation.assert_called_with(
            'delete_recording',
            f"delete_recording_1_{id(callback)}",
            1
        )
        
        # Reset the mock
        self.db_manager.worker.add_operation.reset_mock()
        
        # Test execute_query
        self.db_manager.execute_query("SELECT 1", [2], callback)
        # The operation_id is dynamic here so we can't check the exact value
        self.assertEqual(self.db_manager.worker.add_operation.call_count, 1)
        args, kwargs = self.db_manager.worker.add_operation.call_args
        self.assertEqual(args[0], 'execute_query')
        self.assertEqual(args[2], "SELECT 1")
        self.assertEqual(args[3], [2])
        self.assertEqual(kwargs, {'return_last_row_id': False})
    
    def test_manager_executes_callbacks_on_success(self):
        """Test that the manager executes callbacks on successful operations."""
        # Create a mock callback
        callback = Mock()
        
        # Set up a test table
        self.db_manager.execute_query(
            "CREATE TABLE IF NOT EXISTS test_callbacks (id INTEGER PRIMARY KEY, data TEXT)",
            callback=lambda x: None
        )
        self.wait_for_signals()
        
        # Insert data and test callback execution
        self.db_manager.execute_query(
            "INSERT INTO test_callbacks (data) VALUES (?)",
            ["test_callback_data"],
            callback=callback,
            return_last_row_id=True
        )
        
        # Wait for the operation to complete
        self.wait_for_signals()
        
        # Check that the callback was called with the correct result (row ID 1)
        callback.assert_called_once_with(1)
    
    def test_manager_does_not_execute_callback_on_error(self):
        """Test that the manager does not execute callbacks on failed operations."""
        # Create a mock callback
        callback = Mock()
        
        # Execute a query that will fail
        self.db_manager.execute_query(
            "SELECT * FROM nonexistent_table",
            callback=callback
        )
        
        # Wait for the operation to complete
        self.wait_for_signals()
        
        # Check that the callback was not called
        callback.assert_not_called()
    
    def test_manager_forwards_error_signal(self):
        """Test that the manager forwards the error_occurred signal from the worker."""
        # Create a signal spy
        error_data = []
        
        def on_error_occurred(op_type, error_msg):
            error_data.append((op_type, error_msg))
        
        # Connect the signal
        self.db_manager.error_occurred.connect(on_error_occurred)
        
        # Execute a query that will fail
        self.db_manager.execute_query("SELECT * FROM nonexistent_table")
        
        # Wait for the operation to complete
        self.wait_for_signals()
        
        # Check that the error signal was forwarded
        self.assertEqual(len(error_data), 1, "Should have received one error")
        self.assertEqual(error_data[0][0], 'execute_query', "Operation type should match")
        self.assertTrue('no such table: nonexistent_table' in error_data[0][1].lower(), 
                      f"Error message should mention nonexistent table, got: {error_data[0][1]}")
        
        # Clean up
        self.db_manager.error_occurred.disconnect(on_error_occurred)
    
    def test_manager_forwards_data_changed_signal(self):
        """Test that the manager forwards the dataChanged signal from the worker with parameters."""
        # Create a signal spy
        data_changed_data = []
        
        def on_data_changed(item_type, item_id):
            data_changed_data.append((item_type, item_id))
        
        # Connect the signal
        self.db_manager.dataChanged.connect(on_data_changed)
        
        # Execute a write query to trigger dataChanged
        self.db_manager.execute_query(
            "CREATE TABLE IF NOT EXISTS test_data_changed (id INTEGER PRIMARY KEY, data TEXT)"
        )
        
        # Wait for the operation to complete
        self.wait_for_signals()
        
        # Check that the dataChanged signal was forwarded with parameters
        self.assertEqual(len(data_changed_data), 1, "Should have received one dataChanged signal")
        self.assertEqual(data_changed_data[0][0], "recording", "Item type should be 'recording'")
        self.assertEqual(data_changed_data[0][1], -1, "Item ID should be -1 (refresh all)")
        
        # Clean up
        self.db_manager.dataChanged.disconnect(on_data_changed)
    
    def test_manager_shutdown_stops_worker(self):
        """Test that the manager's shutdown method stops the worker."""
        # Verify worker is running
        self.assertTrue(self.db_manager.worker.isRunning(), "Worker should be running")
        
        # Call shutdown
        self.db_manager.shutdown()
        
        # Wait a bit for the worker to stop
        QThread.msleep(200)
        
        # Verify worker has stopped
        self.assertFalse(self.db_manager.worker.isRunning(), "Worker should have stopped")
    
    @patch('app.DatabaseManager.DatabaseWorker')
    def test_manager_cleans_up_callbacks(self, mock_worker_class):
        """Test that callbacks are cleaned up after completion or error."""
        # Create a mock worker with the necessary signals
        mock_worker = MagicMock()
        mock_worker.operation_complete = pyqtSignal(dict)
        mock_worker.error_occurred = pyqtSignal(str, str)
        mock_worker.dataChanged = pyqtSignal()
        mock_worker_class.return_value = mock_worker
        
        # Create a database manager with the mock worker
        db_manager = DatabaseManager()
        
        # Get the initial number of signal connections
        initial_operation_complete_count = len(db_manager.operation_complete.receivers())
        initial_error_occurred_count = len(db_manager.error_occurred.receivers())
        
        # Create a test callback
        callback = lambda x: None
        
        # Execute a test operation with the callback
        db_manager.create_recording(("test.mp3", "/path/to/test.mp3", "2025-01-01 12:00:00", "00:05:00"), callback)
        
        # Verify that signal connections were added
        self.assertEqual(len(db_manager.operation_complete.receivers()), initial_operation_complete_count + 1,
                       "Should have added a connection to operation_complete")
        self.assertEqual(len(db_manager.error_occurred.receivers()), initial_error_occurred_count + 1,
                       "Should have added a connection to error_occurred")
        
        # Simulate operation completion
        db_manager.operation_complete.emit({
            'id': f"create_recording_{id(callback)}",
            'type': 'create_recording',
            'result': 1
        })
        
        # Verify that signal connections were removed
        self.assertEqual(len(db_manager.operation_complete.receivers()), initial_operation_complete_count,
                       "Should have removed the connection to operation_complete")
        self.assertEqual(len(db_manager.error_occurred.receivers()), initial_error_occurred_count,
                       "Should have removed the connection to error_occurred")
        
        # Execute another test operation
        db_manager.create_recording(("test2.mp3", "/path/to/test2.mp3", "2025-01-01 12:00:00", "00:05:00"), callback)
        
        # Verify signal connections were added again
        self.assertEqual(len(db_manager.operation_complete.receivers()), initial_operation_complete_count + 1,
                       "Should have added a connection to operation_complete")
        self.assertEqual(len(db_manager.error_occurred.receivers()), initial_error_occurred_count + 1,
                       "Should have added a connection to error_occurred")
        
        # Simulate error
        db_manager.error_occurred.emit('create_recording', 'Test error')
        
        # Verify that signal connections were removed
        self.assertEqual(len(db_manager.operation_complete.receivers()), initial_operation_complete_count,
                       "Should have removed the connection to operation_complete")
        self.assertEqual(len(db_manager.error_occurred.receivers()), initial_error_occurred_count,
                       "Should have removed the connection to error_occurred")


class TestConcurrentOperations(unittest.TestCase):
    """Test suite for concurrent database operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up the test environment once for all tests."""
        # Create a QApplication instance if not already created
        cls.app = QApplication(sys.argv) if not QApplication.instance() else QApplication.instance()
        
        # Create a temporary file for the test database
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix='.sqlite')
        
        # Save the original database path
        cls.original_db_path = app.constants.DATABASE_PATH
        # Override the database path for testing
        app.constants.DATABASE_PATH = cls.temp_db_path
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the test environment after all tests."""
        # Restore the original database path
        app.constants.DATABASE_PATH = cls.original_db_path
        
        # Close and remove the temporary database file
        os.close(cls.temp_db_fd)
        if os.path.exists(cls.temp_db_path):
            os.unlink(cls.temp_db_path)
    
    def setUp(self):
        """Set up before each test."""
        # Create a database manager for testing
        self.db_manager = DatabaseManager()
        
        # Wait for worker thread to start
        QThread.msleep(100)
        
        # Initialize test data
        self.results = []
        self.errors = []
        self.completed_counter = 0
    
    def tearDown(self):
        """Clean up after each test."""
        # Shutdown the database manager
        if hasattr(self, 'db_manager'):
            self.db_manager.shutdown()
    
    def test_concurrent_operations_no_locking_errors(self):
        """Test that many concurrent operations can be executed without database locking errors."""
        # Create a recording for testing with unique path
        import time
        timestamp = int(time.time())
        unique_path = f"/path/to/test_{timestamp}.mp3"
        recording_data = (f"test_{timestamp}.mp3", unique_path, "2025-04-21 12:00:00", "00:05:00")
        
        # First create a recording
        loop = QEventLoop()
        recording_id = None
        
        def on_recording_created(result):
            nonlocal recording_id
            recording_id = result
            loop.quit()
            
        self.db_manager.create_recording(recording_data, on_recording_created)
        
        # Wait for the creation to complete or timeout after 2 seconds
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(2000)
        loop.exec()
        timer.stop()
        
        self.assertIsNotNone(recording_id, "Failed to create test recording")
        
        # Handler for tracking operation completion
        def on_operation_complete(result):
            self.completed_counter += 1
            self.results.append(result)
        
        # Handler for tracking errors
        def on_error(op_type, error_msg):
            self.errors.append((op_type, error_msg))
        
        # Connect signals
        self.db_manager.operation_complete.connect(on_operation_complete)
        self.db_manager.error_occurred.connect(on_error)
        
        # Number of operations to run
        NUM_OPS = 50  # More operations to stress test
        
        # Quickly queue operations (reads and writes mixed)
        for i in range(NUM_OPS // 2):
            # Add some read operations
            self.db_manager.get_all_recordings(on_operation_complete)
            
            # Add some write operations that would typically cause locks with separate connections
            self.db_manager.execute_query(
                "UPDATE recordings SET raw_transcript = ? WHERE id = ?", 
                [f"Updated transcript {i}", recording_id],
                on_operation_complete
            )
        
        # Process events until all operations complete or timeout
        wait_loop = QEventLoop()
        
        def check_completion():
            if self.completed_counter >= NUM_OPS or len(self.errors) > 0:
                wait_loop.quit()
        
        # Check every 100ms
        check_timer = QTimer()
        check_timer.timeout.connect(check_completion)
        check_timer.start(100)
        
        # Also quit after 10 seconds maximum
        timeout_timer = QTimer()
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(wait_loop.quit)
        timeout_timer.start(10000)  # 10 second timeout
        
        # Wait for completion
        wait_loop.exec()
        
        # Stop timers
        check_timer.stop()
        timeout_timer.stop()
        
        # Disconnect signals
        self.db_manager.operation_complete.disconnect(on_operation_complete)
        self.db_manager.error_occurred.disconnect(on_error)
        
        # Check results
        self.assertEqual(len(self.errors), 0, f"Errors occurred: {self.errors}")
        self.assertGreaterEqual(self.completed_counter, NUM_OPS, 
                              f"Not enough operations completed. Got {self.completed_counter}, expected at least {NUM_OPS}")


if __name__ == '__main__':
    unittest.main()