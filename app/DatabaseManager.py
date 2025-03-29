import os
import json
import logging
import queue
import sqlite3
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex

from app.constants import DATABASE_PATH, CONFIG_PATH, DEFAULT_CONFIG
from app.db_utils import (
    ensure_database_exists, get_connection, create_recordings_table,
    get_all_recordings, get_recording_by_id, create_recording, 
    update_recording, delete_recording, search_recordings
)

# Configure logging
logger = logging.getLogger('transcribrr')

class DatabaseWorker(QThread):
    """Worker thread that processes database operations from a queue."""
    operation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.operations_queue = queue.Queue()
        self.running = True
        self.mutex = QMutex()

    def run(self):
        """Process operations from the queue."""
        conn = None
        try:
            conn = get_connection()
            
            while self.running:
                try:
                    # Get next operation with a timeout to allow for thread termination
                    operation = self.operations_queue.get(timeout=0.5)
                    if operation is None:  # Sentinel value to exit
                        break

                    # Process operation
                    op_type = operation.get('type')
                    op_id = operation.get('id')
                    op_args = operation.get('args', [])
                    op_kwargs = operation.get('kwargs', {})
                    result = None
                    
                    # Start transaction for write operations
                    needs_transaction = op_type in ('execute_query', 'create_table', 'create_recording', 
                                                   'update_recording', 'delete_recording', 'search_recordings')
                    
                    try:
                        # Execute appropriate database function
                        if op_type == 'execute_query':
                            query = op_args[0]
                            params = op_args[1] if len(op_args) > 1 else []
                            cursor = conn.cursor()
                            cursor.execute(query, params)
                            result = cursor.fetchall()
                            if needs_transaction:
                                conn.commit()
                        elif op_type == 'create_table':
                            create_recordings_table(conn)
                        elif op_type == 'create_recording':
                            result = create_recording(conn, op_args[0])
                        elif op_type == 'get_all_recordings':
                            result = get_all_recordings(conn)
                        elif op_type == 'get_recording_by_id':
                            result = get_recording_by_id(conn, op_args[0])
                        elif op_type == 'update_recording':
                            update_recording(conn, op_args[0], **op_kwargs)
                        elif op_type == 'delete_recording':
                            delete_recording(conn, op_args[0])
                        elif op_type == 'search_recordings':
                            result = search_recordings(conn, op_args[0])
                                
                        # Signal completion with result
                        self.operation_complete.emit({
                            'id': op_id,
                            'type': op_type,
                            'result': result
                        })
                        
                    except Exception as e:
                        logger.error(f"Database operation error in {op_type}: {e}", exc_info=True)
                        self.error_occurred.emit(op_type, str(e))
                    finally:
                        # Mark operation as done regardless of success/failure
                        self.operations_queue.task_done()

                except queue.Empty:
                    # No operations in queue, continue waiting
                    continue
                except Exception as e:
                    logger.error(f"Operation queue error: {e}", exc_info=True)
                    self.error_occurred.emit("operation_queue", str(e))
                    try:
                        self.operations_queue.task_done()
                    except:
                        pass  # Queue might be in an unstable state

        except Exception as e:
            logger.error(f"Database worker error: {e}", exc_info=True)
            self.error_occurred.emit("worker_init", str(e))
        finally:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Error closing database connection: {e}")
                    self.error_occurred.emit("connection_close", str(e))

    def add_operation(self, operation_type, operation_id=None, *args, **kwargs):
        """Add an operation to the queue."""
        self.operations_queue.put({
            'type': operation_type,
            'id': operation_id,
            'args': args,
            'kwargs': kwargs
        })

    def stop(self):
        """Stop the worker thread."""
        self.mutex.lock()
        self.running = False
        self.mutex.unlock()
        # Add sentinel to unblock queue
        self.operations_queue.put(None)
        self.wait()


class DatabaseManager(QObject):
    """Manages database operations in a separate thread."""
    operation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        
        # Initialize database if needed
        if not os.path.exists(DATABASE_PATH):
            ensure_database_exists()
        
        # Create worker thread
        self.worker = DatabaseWorker()
        self.worker.operation_complete.connect(self.operation_complete)
        self.worker.error_occurred.connect(self.error_occurred)
        self.worker.start()
        
        # Initialize config if needed
        if not os.path.exists(CONFIG_PATH):
            self._create_config_file()


    def _create_config_file(self):
        """Create default configuration file."""
        try:
            with open(CONFIG_PATH, 'w') as config_file:
                json.dump(DEFAULT_CONFIG, config_file, indent=4)
            logger.info("Config file created successfully")
        except Exception as e:
            logger.error(f"Failed to create config file: {e}", exc_info=True)

    def create_recording(self, recording_data, callback=None):
        """
        Create a new recording in the database.
        
        Args:
            recording_data: Tuple of (filename, file_path, date_created, duration, raw_transcript, processed_text)
            callback: Optional function to call when operation completes
        """
        operation_id = f"create_recording_{id(callback) if callback else 'no_callback'}"
        self.worker.add_operation('create_recording', operation_id, recording_data)
        
        if callback and callable(callback):
            def handler(result):
                if result['id'] == operation_id:
                    callback(result['result'])
                    self.operation_complete.disconnect(handler)
            
            self.operation_complete.connect(handler)

    def get_all_recordings(self, callback):
        """
        Get all recordings from the database.
        
        Args:
            callback: Function to call with the result
        """
        if not callback or not callable(callback):
            logger.warning("get_all_recordings called without a valid callback function")
            return
            
        operation_id = f"get_all_recordings_{id(callback)}"
        self.worker.add_operation('get_all_recordings', operation_id)
        
        # Connect a one-time handler for this specific operation
        def handler(result):
            if result['id'] == operation_id:
                callback(result['result'])
                self.operation_complete.disconnect(handler)
        
        self.operation_complete.connect(handler)

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
                self.operation_complete.disconnect(handler)
        
        self.operation_complete.connect(handler)

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
            def handler(result):
                if result['id'] == operation_id:
                    callback()
                    self.operation_complete.disconnect(handler)
            
            self.operation_complete.connect(handler)

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
            def handler(result):
                if result['id'] == operation_id:
                    callback()
                    self.operation_complete.disconnect(handler)
            
            self.operation_complete.connect(handler)

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
                    self.operation_complete.disconnect(handler)
            
            self.operation_complete.connect(handler)

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
                self.operation_complete.disconnect(handler)
        
        self.operation_complete.connect(handler)

    def shutdown(self):
        """Shut down the database manager and worker thread."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            logger.info("Database worker stopped")


