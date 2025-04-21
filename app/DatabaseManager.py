import os
import logging
import queue
import sqlite3
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, Qt

from app.constants import DATABASE_PATH
from app.db_utils import (
    ensure_database_exists, get_connection, create_recordings_table,
    get_all_recordings, get_recording_by_id, create_recording, 
    update_recording, delete_recording, search_recordings
)

logger = logging.getLogger('transcribrr')

class DatabaseWorker(QThread):
    """Thread for DB operations."""
    operation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message
    dataChanged = pyqtSignal()  # Basic signal with no parameters - parameters added by DatabaseManager

    def __init__(self, parent=None):
        super().__init__(parent)
        self.operations_queue = queue.Queue()
        self.running = True
        self.mutex = QMutex()
        # Create a persistent connection for the worker thread
        self.conn = get_connection()
        # Ensure foreign keys are enabled
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def run(self):
        """Process queued operations."""
        try:
            while self.running:
                try:
                    operation = self.operations_queue.get(timeout=0.5)
                    if operation is None:  # Sentinel value to exit
                        break

                    op_type = operation.get('type')
                    op_id = operation.get('id')
                    op_args = operation.get('args', [])
                    op_kwargs = operation.get('kwargs', {})
                    result = None
                    
                    # Flag to track if data was modified (for dataChanged signal)
                    data_modified = False
                    
                    try:
                        # Determine if operation is a write operation that requires a transaction
                        is_write_operation = op_type in ('execute_query', 'create_table', 'create_recording', 
                                                        'update_recording', 'delete_recording')
                        
                        if op_type == 'execute_query':
                            query = op_args[0]
                            params = op_args[1] if len(op_args) > 1 else []
                            
                            # Check if this is a modifying query
                            query_lower = query.lower().strip()
                            is_modifying_query = any(query_lower.startswith(prefix) for prefix in ['insert', 'update', 'delete'])
                            
                            # Track which type of data was modified for more targeted refresh
                            if is_modifying_query:
                                data_modified = True
                                logger.debug(f"Modifying query detected: {query_lower[:100]}")
                                
                                # More specific logging about what's being modified
                                if 'recording_folders' in query_lower:
                                    logger.info("Recording-folder association modified by query")
                                elif 'recordings' in query_lower:
                                    logger.info("Recording data modified by query")
                                elif 'folders' in query_lower:
                                    logger.info("Folder data modified by query")
                            
                            # Use transaction for write operations
                            if is_modifying_query:
                                with self.conn:  # This automatically handles commit/rollback
                                    cursor = self.conn.cursor()
                                    cursor.execute(query, params)
                                    result = cursor.fetchall()
                            else:
                                cursor = self.conn.cursor()
                                cursor.execute(query, params)
                                result = cursor.fetchall()
                                
                        elif op_type == 'create_table':
                            with self.conn:  # Auto commit/rollback
                                create_recordings_table(self.conn)
                                
                        elif op_type == 'create_recording':
                            with self.conn:  # Auto commit/rollback
                                result = create_recording(self.conn, op_args[0])
                                data_modified = True
                                logger.info(f"Recording created with ID: {result}")
                                
                        elif op_type == 'get_all_recordings':
                            result = get_all_recordings(self.conn)
                            
                        elif op_type == 'get_recording_by_id':
                            result = get_recording_by_id(self.conn, op_args[0])
                            
                        elif op_type == 'update_recording':
                            with self.conn:  # Auto commit/rollback
                                update_recording(self.conn, op_args[0], **op_kwargs)
                                data_modified = True
                                logger.info(f"Recording updated with ID: {op_args[0]}")
                                
                        elif op_type == 'delete_recording':
                            with self.conn:  # Auto commit/rollback
                                delete_recording(self.conn, op_args[0])
                                data_modified = True
                                logger.info(f"Recording deleted with ID: {op_args[0]}")
                                
                        elif op_type == 'search_recordings':
                            result = search_recordings(self.conn, op_args[0])
                                
                        self.operation_complete.emit({
                            'id': op_id,
                            'type': op_type,
                            'result': result
                        })
                        
                        # Emit dataChanged signal if data was modified
                        if data_modified:
                            logger.info("Database data modified, emitting dataChanged signal")
                            self.dataChanged.emit()
                        
                    except Exception as e:
                        logger.error(f"Database operation error in {op_type}: {e}", exc_info=True)
                        self.error_occurred.emit(op_type, str(e))
                    finally:
                        self.operations_queue.task_done()

                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"Operation queue error: {e}", exc_info=True)
                    self.error_occurred.emit("operation_queue", str(e))
                    try:
                        self.operations_queue.task_done()
                    except:
                        pass

        except Exception as e:
            logger.error(f"Database worker error: {e}", exc_info=True)
            self.error_occurred.emit("worker_init", str(e))
        finally:
            # Ensure connection is closed when worker is finished
            try:
                if hasattr(self, 'conn') and self.conn:
                    self.conn.close()
                    logger.debug("Database worker connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
                self.error_occurred.emit("connection_close", str(e))

    def add_operation(self, operation_type, operation_id=None, *args, **kwargs):
        """Enqueue operation."""
        self.operations_queue.put({
            'type': operation_type,
            'id': operation_id,
            'args': args,
            'kwargs': kwargs
        })

    def stop(self):
        """Stop thread."""
        self.mutex.lock()
        self.running = False
        self.mutex.unlock()
        # Add sentinel to unblock queue
        self.operations_queue.put(None)
        self.wait()


class DatabaseManager(QObject):
    """DB manager with worker thread."""
    operation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message
    dataChanged = pyqtSignal(str, int)  # Signal emitted when data is modified (create, update, delete) with type and ID

    def __init__(self, parent=None):
        super().__init__(parent)
        
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        
        if not os.path.exists(DATABASE_PATH):
            ensure_database_exists()
        
        self.worker = DatabaseWorker()
        self.worker.operation_complete.connect(self.operation_complete)
        self.worker.error_occurred.connect(self.error_occurred)
        # Connect worker's dataChanged signal to our custom handler
        self.worker.dataChanged.connect(self._on_data_changed)
        self.worker.start()
        
    def _on_data_changed(self):
        """Handle data change from worker and emit our signal with parameters."""
        logger.info("Data changed signal received from worker thread, broadcasting to UI")
        # Emit with default parameters to refresh everything
        self.dataChanged.emit("recording", -1)

    def create_recording(self, recording_data, callback=None):
        """Create a recording. recording_data tuple, optional callback."""
        operation_id = f"create_recording_{id(callback) if callback else 'no_callback'}"
        self.worker.add_operation('create_recording', operation_id, recording_data)
        
        if callback and callable(callback):
            def _finalise():
                # Disconnect both signals *if* they are still connected.
                try:
                    self.operation_complete.disconnect(handler)
                except TypeError:
                    pass
                try:
                    self.error_occurred.disconnect(error_handler)
                except TypeError:
                    pass

            def handler(result):
                if result["id"] == operation_id:
                    callback(result["result"])
                    _finalise()

            def error_handler(op_name, msg):
                if op_name == "create_recording":
                    _finalise()

            # Use UniqueConnection to prevent duplicate connections
            self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)
            self.error_occurred.connect(error_handler, Qt.ConnectionType.UniqueConnection)

    def get_all_recordings(self, callback):
        """Fetch all recordings, call callback with result."""
        if not callback or not callable(callback):
            logger.warning("get_all_recordings called without a valid callback function")
            return
            
        operation_id = f"get_all_recordings_{id(callback)}"
        self.worker.add_operation('get_all_recordings', operation_id)
        
        def handler(result):
            if result['id'] == operation_id:
                callback(result['result'])
                try:
                    self.operation_complete.disconnect(handler)
                except TypeError:
                    pass
        
        self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)

    def get_recording_by_id(self, recording_id, callback):
        """
        Get a recording by its ID.
        
        Args:
            recording_id: ID of the recording to retrieve
            callback: Function to call with the result
        """
        if not callback or not callable(callback):
            logger.warning(f"get_recording_by_id called for ID {recording_id} without a valid callback function")
            return
            
        operation_id = f"get_recording_{recording_id}_{id(callback)}"
        self.worker.add_operation('get_recording_by_id', operation_id, recording_id)
        
        def handler(result):
            if result['id'] == operation_id:
                callback(result['result'])
                try:
                    self.operation_complete.disconnect(handler)
                except TypeError:
                    pass
        
        self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)

    def update_recording(self, recording_id, callback=None, **kwargs):
        """
        Update a recording in the database.
        
        Args:
            recording_id: ID of the recording to update
            callback: Optional function to call when operation completes
            **kwargs: Fields to update and their values
        """
        operation_id = f"update_recording_{recording_id}_{id(callback) if callback else 'no_callback'}"
        self.worker.add_operation('update_recording', operation_id, recording_id, **kwargs)
        
        if callback and callable(callback):
            def _finalise():
                try:
                    self.operation_complete.disconnect(handler)
                except TypeError:
                    pass
                try:
                    self.error_occurred.disconnect(error_handler)
                except TypeError:
                    pass

            def handler(result):
                if result["id"] == operation_id:
                    callback()
                    _finalise()

            def error_handler(op_name, msg):
                if op_name == "update_recording":
                    _finalise()

            self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)
            self.error_occurred.connect(error_handler, Qt.ConnectionType.UniqueConnection)

    def delete_recording(self, recording_id, callback=None):
        """
        Delete a recording from the database.
        
        Args:
            recording_id: ID of the recording to delete
            callback: Optional function to call when operation completes
        """
        operation_id = f"delete_recording_{recording_id}_{id(callback) if callback else 'no_callback'}"
        self.worker.add_operation('delete_recording', operation_id, recording_id)
        
        if callback and callable(callback):
            def _finalise():
                try:
                    self.operation_complete.disconnect(handler)
                except TypeError:
                    pass
                try:
                    self.error_occurred.disconnect(error_handler)
                except TypeError:
                    pass

            def handler(result):
                if result["id"] == operation_id:
                    callback()
                    _finalise()

            def error_handler(op_name, msg):
                if op_name == "delete_recording":
                    _finalise()

            self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)
            self.error_occurred.connect(error_handler, Qt.ConnectionType.UniqueConnection)

    def execute_query(self, query, params=None, callback=None):
        """
        Execute a custom SQL query.
        
        Args:
            query: SQL query to execute
            params: Parameters for the query
            callback: Optional function to call with the result
        """
        operation_id = f"query_{id(query)}_{id(callback) if callback else 'no_callback'}"
        self.worker.add_operation('execute_query', operation_id, query, params or [])
        
        if callback and callable(callback):
            def handler(result):
                if result['id'] == operation_id:
                    callback(result['result'])
                    try:
                        self.operation_complete.disconnect(handler)
                    except TypeError:
                        pass
            
            self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)

    def search_recordings(self, search_term, callback):
        """
        Search for recordings by filename or transcript.
        
        Args:
            search_term: Term to search for
            callback: Function to call with the result
        """
        if not callback or not callable(callback):
            logger.warning("search_recordings called without a valid callback function")
            return
            
        operation_id = f"search_recordings_{id(callback)}"
        self.worker.add_operation('search_recordings', operation_id, search_term)
        
        def handler(result):
            if result['id'] == operation_id:
                callback(result['result'])
                try:
                    self.operation_complete.disconnect(handler)
                except TypeError:
                    pass
        
        self.operation_complete.connect(handler, Qt.ConnectionType.UniqueConnection)

    def shutdown(self):
        """Shut down the database manager and worker thread."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            logger.info("Database worker stopped")

    def get_signal_receiver_count(self):
        """Return the number of receivers for each signal. Used for testing."""
        return {
            'operation_complete': len(self.operation_complete.receivers()),
            'error_occurred': len(self.error_occurred.receivers())
        }
