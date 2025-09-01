"""Unit tests for DatabaseManager and DatabaseWorker classes."""

import unittest
import sqlite3
import queue
import logging
from unittest.mock import Mock, MagicMock, patch, call, PropertyMock
from typing import Any, Dict, List, Optional

# Import the module under test
from app.DatabaseManager import DatabaseManager, DatabaseWorker


class TestDatabaseWorker(unittest.TestCase):
    """Test suite for DatabaseWorker class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_parent = Mock()
        self.mock_connection = Mock()
        self.mock_cursor = Mock()
        self.mock_connection.cursor.return_value = self.mock_cursor
        self.mock_connection.__enter__ = Mock(return_value=self.mock_connection)
        self.mock_connection.__exit__ = Mock(return_value=None)
        
        # Set up logger mock
        self.mock_logger = Mock()
        
    # DatabaseWorker.__init__ tests
    
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.queue.Queue')
    @patch('app.DatabaseManager.QMutex')
    def test_init_successful(self, mock_mutex_class, mock_queue_class, mock_get_conn):
        """Tests successful initialization of DatabaseWorker with all required attributes."""
        # Arrange
        mock_queue_instance = Mock()
        mock_queue_class.return_value = mock_queue_instance
        mock_mutex_instance = Mock()
        mock_mutex_class.return_value = mock_mutex_instance
        mock_get_conn.return_value = self.mock_connection
        
        # Act
        worker = DatabaseWorker(self.mock_parent)
        
        # Assert
        self.assertEqual(worker.operations_queue, mock_queue_instance)
        self.assertTrue(worker.running)
        self.assertEqual(worker.mutex, mock_mutex_instance)
        self.assertEqual(worker.conn, self.mock_connection)
        self.mock_connection.execute.assert_called_once_with("PRAGMA foreign_keys = ON")
        
    @patch('app.DatabaseManager.get_connection')
    def test_init_connection_fails(self, mock_get_conn):
        """Tests DatabaseWorker initialization when get_connection fails."""
        # Arrange
        mock_get_conn.side_effect = RuntimeError('Database unavailable')
        
        # Act & Assert
        with self.assertRaises(RuntimeError) as context:
            DatabaseWorker(self.mock_parent)
        self.assertIn('Database unavailable', str(context.exception))
    
    # DatabaseWorker._log_error tests
    
    @patch('app.DatabaseManager.logger')
    @patch('app.DatabaseManager.redact')
    @patch('app.DatabaseManager.get_connection')
    def test_log_error_with_error_level_and_signal(self, mock_get_conn, mock_redact, mock_logger):
        """Tests error logging with signal emission for error level."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_redact.return_value = 'redacted_error_message'
        worker = DatabaseWorker(self.mock_parent)
        mock_error_signal = Mock()
        worker.error_occurred = mock_error_signal
        
        # Act
        result = worker._log_error(
            'test_operation',
            Exception('Test error'),
            'Test error occurred',
            level='error',
            emit_signal=True
        )
        
        # Assert
        mock_logger.error.assert_called_once()
        mock_redact.assert_called_once()
        mock_error_signal.emit.assert_called_once_with('test_operation', 'redacted_error_message')
        self.assertIn('Test error occurred', result)
        
    @patch('app.DatabaseManager.logger')
    @patch('app.DatabaseManager.get_connection')
    def test_log_error_warning_level_no_signal(self, mock_get_conn, mock_logger):
        """Tests error logging with warning level without signal emission."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        mock_error_signal = Mock()
        worker.error_occurred = mock_error_signal
        
        # Act
        result = worker._log_error(
            'test_op',
            Exception('Warning'),
            'Warning message',
            level='warning',
            emit_signal=False
        )
        
        # Assert
        mock_logger.warning.assert_called_once()
        mock_error_signal.emit.assert_not_called()
        self.assertIn('Warning message', result)
        
    @patch('app.DatabaseManager.logger')
    @patch('app.DatabaseManager.redact')
    @patch('app.DatabaseManager.get_connection')
    def test_log_error_with_operation_context(self, mock_get_conn, mock_redact, mock_logger):
        """Tests error logging with operation context."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_redact.return_value = 'safe_message'
        worker = DatabaseWorker(self.mock_parent)
        mock_error_signal = Mock()
        worker.error_occurred = mock_error_signal
        
        # Act
        result = worker._log_error(
            'specific_operation',
            Exception('Error'),
            'Operation failed',
            emit_signal=True
        )
        
        # Assert
        mock_error_signal.emit.assert_called_once_with('specific_operation', 'safe_message')
        self.assertIn('specific_operation', mock_logger.error.call_args[0][0])
    
    # DatabaseWorker.run tests - Main loop
    
    @patch('app.DatabaseManager.get_all_recordings')
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_main_loop_with_valid_operations(self, mock_logger, mock_get_conn, mock_get_all):
        """Tests worker thread main loop processing queue operations."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        mock_get_all.return_value = [{'id': 1}, {'id': 2}]
        
        # Set up queue to return operation then None sentinel
        operation = {
            'type': 'get_all_recordings',
            'id': 'test_1',
            'args': [],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        worker.operation_complete = Mock()
        
        # Act
        worker.run()
        
        # Assert
        mock_get_all.assert_called_once_with(self.mock_connection)
        worker.operation_complete.emit.assert_called_once_with('test_1', [{'id': 1}, {'id': 2}])
        self.mock_connection.close.assert_called_once()
        
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_with_queue_timeout(self, mock_logger, mock_get_conn):
        """Tests worker thread with queue timeout."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        
        # Simulate queue.Empty then stop running
        worker.operations_queue.get.side_effect = [queue.Empty, None]
        worker.running = False  # Stop after first iteration
        
        # Act
        worker.run()
        
        # Assert
        worker.operations_queue.get.assert_called()
        self.mock_connection.close.assert_called_once()
        
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')

    def test_run_execute_query_select(self, mock_logger, mock_get_conn):
        """Tests execute_query operation for SELECT query."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        self.mock_cursor.fetchall.return_value = [(1, 'file1'), (2, 'file2')]
        
        worker = DatabaseWorker(self.mock_parent)
        worker.operation_complete = Mock()
        worker.dataChanged = Mock()
        
        operation = {
            'type': 'execute_query',
            'id': 'query_1',
            'args': ['SELECT * FROM recordings'],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        self.mock_cursor.execute.assert_called_once_with('SELECT * FROM recordings')
        self.mock_cursor.fetchall.assert_called_once()
        worker.operation_complete.emit.assert_called_once_with('query_1', [(1, 'file1'), (2, 'file2')])
        worker.dataChanged.emit.assert_not_called()
        
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_execute_query_insert_with_lastrowid(self, mock_logger, mock_get_conn):
        """Tests execute_query operation for INSERT with return_last_row_id."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        self.mock_cursor.lastrowid = 42
        
        worker = DatabaseWorker(self.mock_parent)
        worker.operation_complete = Mock()
        worker.dataChanged = Mock()
        
        operation = {
            'type': 'execute_query',
            'id': 'query_2',
            'args': ['INSERT INTO recordings VALUES (?)', ['data']],
            'kwargs': {'return_last_row_id': True}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        self.mock_cursor.execute.assert_called()
        worker.operation_complete.emit.assert_called_once_with('query_2', 42)
        worker.dataChanged.emit.assert_called_once()
        
    @patch('app.DatabaseManager.create_recording')
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_create_recording_success(self, mock_logger, mock_get_conn, mock_create):
        """Tests create_recording operation success."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_create.return_value = 123
        
        worker = DatabaseWorker(self.mock_parent)
        worker.operation_complete = Mock()
        worker.dataChanged = Mock()
        
        recording_data = {'filename': 'test.wav'}
        operation = {
            'type': 'create_recording',
            'id': 'create_1',
            'args': [recording_data],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        mock_create.assert_called_once_with(self.mock_connection, recording_data)
        worker.operation_complete.emit.assert_called_once_with('create_1', 123)
        worker.dataChanged.emit.assert_called_once()
        
    @patch('app.DatabaseManager.create_recording')
    @patch('app.DatabaseManager.DuplicatePathError', new=type('DuplicatePathError', (Exception,), {}))
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_create_recording_duplicate_path(self, mock_logger, mock_get_conn, mock_create):
        """Tests create_recording with duplicate path error."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        
        # Simulate duplicate path by raising a generic exception that includes the phrase
        mock_create.side_effect = Exception('Duplicate path: /path/to/file')
        
        worker = DatabaseWorker(self.mock_parent)
        worker._log_error = Mock(return_value='error_message')
        worker.error_occurred = Mock()
        
        recording_data = {'file_path': '/path/to/file'}
        operation = {
            'type': 'create_recording',
            'id': 'create_2',
            'args': [recording_data],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        worker._log_error.assert_called()
        # Check that warning level was used for duplicate
        call_args = worker._log_error.call_args
        self.assertEqual(call_args[1].get('level'), 'warning')
        
    @patch('app.DatabaseManager.update_recording')
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')

    def test_run_update_recording_success(self, mock_logger, mock_get_conn, mock_update):
        """Tests update_recording operation success."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_update.return_value = None
        
        worker = DatabaseWorker(self.mock_parent)
        worker.operation_complete = Mock()
        worker.dataChanged = Mock()
        
        operation = {
            'type': 'update_recording',
            'id': 'update_1',
            'args': [42],
            'kwargs': {'transcript': 'new text'}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        mock_update.assert_called_once_with(self.mock_connection, 42, transcript='new text')
        worker.operation_complete.emit.assert_called_once()
        worker.dataChanged.emit.assert_called_once()
        
    @patch('app.DatabaseManager.delete_recording')
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')

    def test_run_delete_recording_success(self, mock_logger, mock_get_conn, mock_delete):
        """Tests delete_recording operation success."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_delete.return_value = None
        
        worker = DatabaseWorker(self.mock_parent)
        worker.operation_complete = Mock()
        worker.dataChanged = Mock()
        
        operation = {
            'type': 'delete_recording',
            'id': 'delete_1',
            'args': [42],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        mock_delete.assert_called_once_with(self.mock_connection, 42)
        worker.operation_complete.emit.assert_called_once()
        worker.dataChanged.emit.assert_called_once()
        
    @patch('app.DatabaseManager.create_recordings_table')
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_create_table_success(self, mock_logger, mock_get_conn, mock_create_table):
        """Tests create_table operation success."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_create_table.return_value = None
        
        worker = DatabaseWorker(self.mock_parent)
        worker.operation_complete = Mock()
        worker.dataChanged = Mock()
        
        operation = {
            'type': 'create_table',
            'id': 'table_1',
            'args': [],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        mock_create_table.assert_called_once_with(self.mock_connection)
        worker.operation_complete.emit.assert_called_once()
        worker.dataChanged.emit.assert_called_once()
        
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_unknown_operation_type(self, mock_logger, mock_get_conn):
        """Tests unknown operation type handling."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        worker.error_occurred = Mock()
        
        operation = {
            'type': 'unknown_op',
            'id': 'unknown_1',
            'args': [],
            'kwargs': {}
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        mock_logger.warning.assert_called()
        worker.error_occurred.emit.assert_called()
        
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_operation_missing_type(self, mock_logger, mock_get_conn):
        """Tests operation with missing type field."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        worker.error_occurred = Mock()
        
        operation = {
            'id': 'no_type_1',
            'args': []
        }
        worker.operations_queue.get.side_effect = [operation, None]
        
        # Act
        worker.run()
        
        # Assert
        mock_logger.error.assert_called()
        worker.error_occurred.emit.assert_called()
    
    # DatabaseWorker.run - Exception handling tests
    
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_connection_close_error(self, mock_logger, mock_get_conn):
        """Tests connection close error handling."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        self.mock_connection.close.side_effect = sqlite3.Error('Close failed')
        
        worker = DatabaseWorker(self.mock_parent)
        worker._log_error = Mock(return_value='error_message')
        worker.running = False
        worker.operations_queue.get.return_value = None
        
        # Act
        worker.run()
        
        # Assert
        worker._log_error.assert_called()
        mock_logger.info.assert_called()  # Worker finished log
    
    # DatabaseWorker.add_operation tests
    
    @patch('app.DatabaseManager.get_connection')
    def test_add_operation_with_all_params(self, mock_get_conn):
        """Tests adding operation to queue."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        
        # Act
        worker.add_operation('test_op', 'op_123', ['arg1'], {'key': 'value'})
        
        # Assert
        worker.operations_queue.put.assert_called_once_with({
            'type': 'test_op',
            'id': 'op_123',
            'args': ['arg1'],
            'kwargs': {'key': 'value'}
        })
        
    @patch('app.DatabaseManager.get_connection')
    def test_add_operation_minimal_params(self, mock_get_conn):
        """Tests adding operation without optional parameters."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        
        # Act
        worker.add_operation('test_op')
        
        # Assert
        worker.operations_queue.put.assert_called_once_with({
            'type': 'test_op',
            'id': None,
            'args': [],
            'kwargs': {}
        })
    
    # DatabaseWorker.stop tests
    
    @patch('app.DatabaseManager.QMutex')
    @patch('app.DatabaseManager.get_connection')
    def test_stop_worker_thread(self, mock_get_conn, mock_mutex_class):
        """Tests stopping worker thread."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        mock_mutex = Mock()
        mock_mutex_class.return_value = mock_mutex
        
        worker = DatabaseWorker(self.mock_parent)
        worker.wait = Mock()
        
        # Act
        worker.stop()
        
        # Assert
        mock_mutex.lock.assert_called_once()
        self.assertFalse(worker.running)
        mock_mutex.unlock.assert_called_once()
        worker.operations_queue.put.assert_called_with(None)
        worker.wait.assert_called_once()
        
    # Edge cases and error conditions
    
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_task_done_error(self, mock_logger, mock_get_conn):
        """Tests handling of operation queue task_done error."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        
        operation = {
            'type': 'get_all_recordings',
            'id': 'test',
            'args': []
        }
        worker.operations_queue.get.side_effect = [operation, None]
        worker.operations_queue.task_done.side_effect = ValueError('Queue empty')
        
        # Mock get_all_recordings
        with patch('app.DatabaseManager.get_all_recordings') as mock_get_all:
            mock_get_all.return_value = []
            
            # Act
            worker.run()
            
            # Assert
            mock_logger.warning.assert_called()
            
    @patch('app.DatabaseManager.time.sleep')
    @patch('app.DatabaseManager.get_connection')
    @patch('app.DatabaseManager.logger')
    def test_run_persistent_queue_error(self, mock_logger, mock_get_conn, mock_sleep):
        """Tests persistent queue error handling with sleep."""
        # Arrange
        mock_get_conn.return_value = self.mock_connection
        worker = DatabaseWorker(self.mock_parent)
        worker._log_error = Mock(return_value='error_message')
        worker.operations_queue.get.side_effect = [RuntimeError('Queue corrupted'), None]
        worker.running = False  # Stop after first error
        
        # Act
        worker.run()
        
        # Assert
        worker._log_error.assert_called()
        mock_sleep.assert_called_with(0.1)
        
    @patch('app.DatabaseManager.get_connection')
    def test_run_disconnect_error_in_cleanup(self, mock_get_conn):
        """Tests handling of disconnection errors in callback cleanup."""
        from app.DatabaseManager import DatabaseManager
        mock_get_conn.return_value = self.mock_connection
        # Patch DatabaseWorker to control signal behavior
        with patch('app.DatabaseManager.DatabaseWorker') as mock_worker_cls:
            worker = Mock()
            # Signals with connect/disconnect
            worker.operation_complete = Mock()
            worker.error_occurred = Mock()
            # Capture connected handler
            captured_handler = {}
            def connect_handler(func, *args, **kwargs):
                captured_handler['fn'] = func
            worker.operation_complete.connect.side_effect = connect_handler
            # Make disconnect raise TypeError to simulate already disconnected
            worker.operation_complete.disconnect.side_effect = TypeError('already disconnected')
            worker.error_occurred.disconnect.side_effect = TypeError('already disconnected')
            mock_worker_cls.return_value = worker

            manager = DatabaseManager(self.mock_parent)
            cb = Mock()
            # Act: create and then simulate completion
            manager.create_recording({'filename': 'x.wav'}, cb)
            # Ensure handler captured
            self.assertIn('fn', captured_handler)
            # Invoke handler; should perform cleanup without propagating TypeError
            captured_handler['fn']('create_recording_callback_1', 99)
            # Callback executed
            cb.assert_called_once_with(99)
        
    # Note: The following decorators were dangling without a test function.
    # They caused a SyntaxError/IndentationError at import time.
    # Removed to restore test discovery.
class TestDatabaseManager(unittest.TestCase):
    """Test suite for DatabaseManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_parent = Mock()
        self.mock_worker = Mock()
        self.mock_worker.isRunning.return_value = True
        self.mock_worker.start = Mock()
        self.mock_worker.stop = Mock()
        self.mock_worker.add_operation = Mock()
        self.mock_worker.operation_complete = Mock()
        self.mock_worker.error_occurred = Mock()
        self.mock_worker.dataChanged = Mock()
        
    # DatabaseManager.__init__ tests
    
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.ensure_database_exists')
    @patch('app.DatabaseManager.os.makedirs')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.os.path.dirname')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_init_database_exists(self, mock_logger, mock_get_path, mock_dirname,
                                   mock_exists, mock_makedirs, mock_ensure_db, mock_worker_class):
        """Tests DatabaseManager initialization when database exists."""
        # Arrange
        mock_get_path.return_value = '/path/to/db.sqlite'
        mock_dirname.return_value = '/path/to'
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        
        # Act
        manager = DatabaseManager(self.mock_parent)
        
        # Assert
        mock_makedirs.assert_called_once_with('/path/to', exist_ok=True)
        mock_ensure_db.assert_not_called()
        mock_worker_class.assert_called_once_with(manager)
        self.mock_worker.start.assert_called_once()
        mock_logger.info.assert_called()
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.ensure_database_exists')
    @patch('app.DatabaseManager.os.makedirs')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.os.path.dirname')
    @patch('app.DatabaseManager.get_database_path')
    def test_init_database_not_exists(self, mock_get_path, mock_dirname,
                                       mock_exists, mock_makedirs, mock_ensure_db, mock_worker_class):
        """Tests DatabaseManager initialization when database doesn't exist."""
        # Arrange
        mock_get_path.return_value = '/path/to/db.sqlite'
        mock_dirname.return_value = '/path/to'
        mock_exists.return_value = False
        mock_worker_class.return_value = self.mock_worker
        
        # Act
        manager = DatabaseManager(self.mock_parent)
        
        # Assert
        mock_makedirs.assert_called_once()
        mock_ensure_db.assert_called_once()
        mock_worker_class.assert_called_once()
        self.mock_worker.start.assert_called_once()
    
    # DatabaseManager._on_data_changed tests
    
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_on_data_changed(self, mock_logger, mock_get_path, mock_exists, mock_worker_class):
        """Tests data change signal propagation."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        manager.dataChanged = Mock()
        
        # Act
        manager._on_data_changed()
        
        # Assert
        mock_logger.info.assert_called()
        manager.dataChanged.emit.assert_called_once_with('recording', -1)
    
    # DatabaseManager.create_recording tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_create_recording_with_callback(self, mock_get_path, mock_exists, 
                                             mock_worker_class, mock_qt):
        """Tests create_recording with callback function."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        recording_data = {'filename': 'test.wav'}
        
        # Act
        manager.create_recording(recording_data, callback)
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertEqual(call_args[0][0], 'create_recording')
        self.assertIn('callback', call_args[0][1])
        self.assertEqual(call_args[0][2], [recording_data])
        self.mock_worker.operation_complete.connect.assert_called()
        self.mock_worker.error_occurred.connect.assert_called()
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_create_recording_without_callback(self, mock_get_path, mock_exists, mock_worker_class):
        """Tests create_recording without callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        recording_data = {'filename': 'test.wav'}
        
        # Act
        manager.create_recording(recording_data)
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertIn('no_callback', call_args[0][1])
        self.mock_worker.operation_complete.connect.assert_not_called()
        
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_create_recording_callback_execution(self, mock_get_path, mock_exists,
                                                  mock_worker_class, mock_qt):
        """Tests create_recording callback execution on success."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Capture the handler function when connect is called
        handler = None
        def capture_handler(func, connection_type=None):
            nonlocal handler
            handler = func
        self.mock_worker.operation_complete.connect.side_effect = capture_handler
        
        # Act
        manager.create_recording({'filename': 'test.wav'}, callback)
        
        # Simulate operation complete
        if handler:
            handler('create_recording_callback_123', 42)
        
        # Assert
        callback.assert_called_once_with(42)
        
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_create_recording_error_cleanup(self, mock_get_path, mock_exists,
                                             mock_worker_class, mock_qt):
        """Tests create_recording callback cleanup on error."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Capture the error handler
        error_handler = None
        def capture_error_handler(func, connection_type=None):
            nonlocal error_handler
            error_handler = func
        self.mock_worker.error_occurred.connect.side_effect = capture_error_handler
        
        # Act
        manager.create_recording({'filename': 'test.wav'}, callback)
        
        # Simulate error
        if error_handler:
            error_handler('create_recording', 'Error message')
        
        # Assert
        callback.assert_not_called()
        self.mock_worker.operation_complete.disconnect.assert_called()
        self.mock_worker.error_occurred.disconnect.assert_called()
    
    # DatabaseManager.get_all_recordings tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_get_all_recordings_with_callback(self, mock_logger, mock_get_path, mock_exists,
                                               mock_worker_class, mock_qt):
        """Tests get_all_recordings with valid callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Act
        manager.get_all_recordings(callback)
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        self.mock_worker.operation_complete.connect.assert_called_once()
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_get_all_recordings_without_callback(self, mock_logger, mock_get_path, mock_exists,
                                                  mock_worker_class):
        """Tests get_all_recordings without valid callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.get_all_recordings(None)
        
        # Assert
        mock_logger.warning.assert_called()
        self.mock_worker.add_operation.assert_not_called()
        
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_get_all_recordings_callback_execution(self, mock_get_path, mock_exists,
                                                    mock_worker_class, mock_qt):
        """Tests get_all_recordings callback execution and cleanup."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Capture handler
        handler = None
        def capture_handler(func, connection_type=None):
            nonlocal handler
            handler = func
        self.mock_worker.operation_complete.connect.side_effect = capture_handler
        
        # Act
        manager.get_all_recordings(callback)
        
        # Simulate completion
        if handler:
            handler('get_all_recordings_callback_123', [{'id': 1}])
        
        # Assert
        callback.assert_called_once_with([{'id': 1}])
        self.mock_worker.operation_complete.disconnect.assert_called()
    
    # DatabaseManager.get_recording_by_id tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_get_recording_by_id_with_callback(self, mock_get_path, mock_exists,
                                                mock_worker_class, mock_qt):
        """Tests get_recording_by_id with valid parameters."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Act
        manager.get_recording_by_id(42, callback)
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertIn('42', call_args[0][1])
        self.assertEqual(call_args[0][2], [42])
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_get_recording_by_id_without_callback(self, mock_logger, mock_get_path,
                                                   mock_exists, mock_worker_class):
        """Tests get_recording_by_id without valid callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.get_recording_by_id(42, None)
        
        # Assert
        mock_logger.warning.assert_called()
        self.mock_worker.add_operation.assert_not_called()
    
    # DatabaseManager.update_recording tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_update_recording_with_callback(self, mock_get_path, mock_exists,
                                             mock_worker_class, mock_qt):
        """Tests update_recording with callback and kwargs."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Act
        manager.update_recording(42, callback, transcript='new text')
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertEqual(call_args[0][2], [42])
        self.assertEqual(call_args[0][3], {'transcript': 'new text'})
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_update_recording_without_callback(self, mock_get_path, mock_exists,
                                                mock_worker_class):
        """Tests update_recording without callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.update_recording(42, None, transcript='text')
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertIn('no_callback', call_args[0][1])
        
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_update_recording_callback_execution(self, mock_get_path, mock_exists,
                                                  mock_worker_class, mock_qt):
        """Tests update_recording callback execution and cleanup."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Capture handler
        handler = None
        def capture_handler(func, connection_type=None):
            nonlocal handler
            handler = func
        self.mock_worker.operation_complete.connect.side_effect = capture_handler
        
        # Act
        manager.update_recording(42, callback)
        
        # Simulate completion
        if handler:
            handler('update_recording_42_callback_123', None)
        
        # Assert
        callback.assert_called_once_with()
    
    # DatabaseManager.delete_recording tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_delete_recording_with_callback(self, mock_get_path, mock_exists,
                                             mock_worker_class, mock_qt):
        """Tests delete_recording with callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Act
        manager.delete_recording(42, callback)
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        self.mock_worker.operation_complete.connect.assert_called()
        self.mock_worker.error_occurred.connect.assert_called()
        
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_delete_recording_error_handling(self, mock_get_path, mock_exists,
                                              mock_worker_class, mock_qt):
        """Tests delete_recording error handling."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Capture error handler
        error_handler = None
        def capture_error_handler(func, connection_type=None):
            nonlocal error_handler
            error_handler = func
        self.mock_worker.error_occurred.connect.side_effect = capture_error_handler
        
        # Act
        manager.delete_recording(42, callback)
        
        # Simulate error
        if error_handler:
            error_handler('delete_recording', 'Failed')
        
        # Assert
        callback.assert_not_called()
        self.mock_worker.operation_complete.disconnect.assert_called()
    
    # DatabaseManager.execute_query tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_execute_query_with_all_params(self, mock_get_path, mock_exists,
                                            mock_worker_class, mock_qt):
        """Tests execute_query with all parameters."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Act
        manager.execute_query(
            'SELECT * FROM recordings WHERE id = ?',
            [42],
            callback,
            operation_id='custom_id',
            return_last_row_id=True
        )
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertEqual(call_args[0][1], 'custom_id')
        self.assertEqual(call_args[0][3], {'return_last_row_id': True})
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_execute_query_with_defaults(self, mock_get_path, mock_exists, mock_worker_class):
        """Tests execute_query with default parameters."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.execute_query('SELECT * FROM recordings')
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertIn('execute_query', call_args[0][1])
        self.assertEqual(call_args[0][2], ['SELECT * FROM recordings', []])
        self.assertEqual(call_args[0][3], {'return_last_row_id': False})
        
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_execute_query_callback_execution(self, mock_get_path, mock_exists,
                                               mock_worker_class, mock_qt):
        """Tests execute_query callback execution."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Capture handler
        handler = None
        def capture_handler(func, connection_type=None):
            nonlocal handler
            handler = func
        self.mock_worker.operation_complete.connect.side_effect = capture_handler
        
        # Act
        manager.execute_query('SELECT * FROM recordings', callback=callback)
        
        # Simulate completion
        if handler:
            operation_id = self.mock_worker.add_operation.call_args[0][1]
            handler(operation_id, [(1, 'file1')])
        
        # Assert
        callback.assert_called_once_with([(1, 'file1')])
    
    # DatabaseManager.search_recordings tests
    
    @patch('app.DatabaseManager.Qt', create=True)
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_search_recordings_with_callback(self, mock_get_path, mock_exists,
                                              mock_worker_class, mock_qt):
        """Tests search_recordings with valid parameters."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        mock_qt.UniqueConnection = 0
        
        manager = DatabaseManager(self.mock_parent)
        callback = Mock()
        
        # Act
        manager.search_recordings('keyword', callback)
        
        # Assert
        self.mock_worker.add_operation.assert_called_once()
        call_args = self.mock_worker.add_operation.call_args
        self.assertEqual(call_args[0][2], ['keyword'])
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_search_recordings_without_callback(self, mock_logger, mock_get_path,
                                                 mock_exists, mock_worker_class):
        """Tests search_recordings without valid callback."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.search_recordings('keyword', None)
        
        # Assert
        mock_logger.warning.assert_called()
        self.mock_worker.add_operation.assert_not_called()
    
    # DatabaseManager.shutdown tests
    
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    @patch('app.DatabaseManager.logger')
    def test_shutdown_worker_running(self, mock_logger, mock_get_path, mock_exists,
                                      mock_worker_class):
        """Tests shutdown when worker is running."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        self.mock_worker.isRunning.return_value = True
        
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.shutdown()
        
        # Assert
        self.mock_worker.isRunning.assert_called()
        self.mock_worker.stop.assert_called_once()
        mock_logger.info.assert_called()
        
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_shutdown_worker_not_running(self, mock_get_path, mock_exists, mock_worker_class):
        """Tests shutdown when worker is already stopped."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        self.mock_worker.isRunning.return_value = False
        
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        manager.shutdown()
        
        # Assert
        self.mock_worker.isRunning.assert_called()
        self.mock_worker.stop.assert_not_called()
        
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_shutdown_worker_none(self, mock_get_path, mock_exists):
        """Tests shutdown when worker was never initialized."""
        # Arrange
        mock_exists.return_value = True
        
        # Create manager but don't initialize worker
        with patch('app.DatabaseManager.DatabaseWorker') as mock_worker_class:
            mock_worker_class.side_effect = Exception('Init failed')
            try:
                manager = DatabaseManager(self.mock_parent)
            except:
                pass
            
        # Manually set worker to None
        manager = Mock()
        manager.worker = None
        
        # Act - should not raise exception
        DatabaseManager.shutdown(manager)
    
    # DatabaseManager.get_signal_receiver_count tests
    
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_get_signal_receiver_count(self, mock_get_path, mock_exists, mock_worker_class):
        """Tests getting signal receiver counts."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        
        # Mock receiver lists
        mock_op_complete_receivers = [Mock(), Mock()]
        mock_error_receivers = [Mock()]
        self.mock_worker.operation_complete.receivers = Mock(return_value=mock_op_complete_receivers)
        self.mock_worker.error_occurred.receivers = Mock(return_value=mock_error_receivers)
        
        manager = DatabaseManager(self.mock_parent)
        
        # Act
        result = manager.get_signal_receiver_count()
        
        # Assert
        self.assertEqual(result['operation_complete'], 2)
        self.assertEqual(result['error_occurred'], 1)
        
    # Additional edge case tests
    
    @patch('app.DatabaseManager.DatabaseWorker')
    @patch('app.DatabaseManager.os.path.exists')
    @patch('app.DatabaseManager.get_database_path')
    def test_disconnect_error_handling(self, mock_get_path, mock_exists, mock_worker_class):
        """Tests handling of disconnection errors in callback cleanup."""
        # Arrange
        mock_exists.return_value = True
        mock_worker_class.return_value = self.mock_worker
        self.mock_worker.operation_complete.disconnect.side_effect = TypeError('Not connected')
        
        manager = DatabaseManager(self.mock_parent)
        
        # Act - should not raise exception
        manager._finalise(Mock(), Mock())
        
        # Assert - method completes without error
        self.mock_worker.operation_complete.disconnect.assert_called()


if __name__ == '__main__':
    unittest.main()
