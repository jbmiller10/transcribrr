import sqlite3
import os
import json
import logging
import threading
import queue
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex
from app.utils import resource_path

# Configure logging
logger = logging.getLogger('transcribrr')

class DatabaseWorker(QThread):
    """Worker thread that processes database operations from a queue."""
    operation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message

    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.operations_queue = queue.Queue()
        self.running = True
        self.mutex = QMutex()

    def run(self):
        """Process operations from the queue."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            
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
                                                   'update_recording', 'delete_recording')
                    
                    if needs_transaction:
                        conn.execute("BEGIN TRANSACTION")
                        
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
                            create_table(conn, op_args[0])
                            if needs_transaction:
                                conn.commit()
                        elif op_type == 'create_recording':
                            result = create_recording(conn, op_args[0])
                            if needs_transaction:
                                conn.commit()
                        elif op_type == 'get_all_recordings':
                            result = get_all_recordings(conn)
                        elif op_type == 'get_recording_by_id':
                            result = get_recording_by_id(conn, op_args[0])
                        elif op_type == 'update_recording':
                            update_recording(conn, op_args[0], **op_kwargs)
                            if needs_transaction:
                                conn.commit()
                        elif op_type == 'delete_recording':
                            delete_recording(conn, op_args[0])
                            if needs_transaction:
                                conn.commit()
                                
                        # Signal completion with result
                        self.operation_complete.emit({
                            'id': op_id,
                            'type': op_type,
                            'result': result
                        })
                        
                    except Exception as e:
                        # Roll back transaction on error
                        if needs_transaction:
                            conn.rollback()
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
        db_dir = resource_path('./database')
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        self.db_path = resource_path("./database/database.sqlite")
        
        # Initialize database if needed
        if not os.path.exists(self.db_path):
            self._initialize_database()
        
        # Create worker thread
        self.worker = DatabaseWorker(self.db_path)
        self.worker.operation_complete.connect(self.operation_complete)
        self.worker.error_occurred.connect(self.error_occurred)
        self.worker.start()
        
        # Initialize config if needed
        config_path = resource_path('config.json')
        if not os.path.exists(config_path):
            self._create_config_file()

    def _initialize_database(self):
        """Create database and initial tables."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Create recordings table
            sql_create_recordings_table = """
            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                date_created TEXT NOT NULL,
                duration TEXT NOT NULL,
                raw_transcript TEXT,
                processed_text TEXT,
                raw_transcript_formatted BLOB, 
                processed_text_formatted BLOB
            );
            """
            
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Begin transaction
            conn.execute("BEGIN TRANSACTION")
            
            cursor = conn.cursor()
            cursor.execute(sql_create_recordings_table)
            conn.commit()
            
            logger.info("Database initialized successfully")
        except Exception as e:
            # Rollback transaction on error
            if conn:
                conn.rollback()
            logger.error(f"Failed to initialize database: {e}", exc_info=True)
            raise
        finally:
            # Ensure connection is closed
            if conn:
                conn.close()

    def _create_config_file(self):
        """Create default configuration file."""
        config = {
            "transcription_quality": "openai/whisper-large-v3",
            "gpt_model": "gpt-4o",
            "max_tokens": 16000,
            "temperature": 1.0,
            "speaker_detection_enabled": False,
            "transcription_language": "english"
        }
        
        try:
            with open(resource_path('config.json'), 'w') as config_file:
                json.dump(config, config_file, indent=4)
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
        operation_id = f"create_recording_{id(callback)}" if callback else None
        self.worker.add_operation('create_recording', operation_id, recording_data)
        if callback:
            self.operation_complete.connect(
                lambda result: callback(result['result']) if result['id'] == operation_id else None
            )

    def get_all_recordings(self, callback):
        """
        Get all recordings from the database.
        
        Args:
            callback: Function to call with the result
        """
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
        operation_id = f"update_recording_{recording_id}_{id(callback)}" if callback else None
        self.worker.add_operation('update_recording', operation_id, recording_id, **kwargs)
        
        if callback:
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
        operation_id = f"delete_recording_{recording_id}_{id(callback)}" if callback else None
        self.worker.add_operation('delete_recording', operation_id, recording_id)
        
        if callback:
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
        operation_id = f"query_{id(query)}_{id(callback)}" if callback else None
        self.worker.add_operation('execute_query', operation_id, query, params or [])
        
        if callback:
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


# Helper functions for database operations
def create_table(conn, create_table_sql):
    """Create a new table with the provided SQL statement."""
    try:
        c = conn.cursor()
        c.execute(create_table_sql)
    except sqlite3.Error as e:
        logger.error(f"Error creating table: {e}")
        raise

def create_recording(conn, recording):
    """
    Create a new recording in the recordings table.
    
    Args:
        conn: Database connection
        recording: Tuple of (filename, file_path, date_created, duration, raw_transcript, processed_text)
        
    Returns:
        int: ID of the created recording
    """
    sql = '''INSERT INTO recordings(filename, file_path, date_created, duration, raw_transcript, processed_text)
              VALUES(?,?,?,?,?,?)'''
    cur = conn.cursor()
    cur.execute(sql, recording)
    conn.commit()
    return cur.lastrowid

def get_all_recordings(conn):
    """
    Query all rows in the recordings table.
    
    Args:
        conn: Database connection
        
    Returns:
        list: All recordings in the database
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM recordings")
    return cur.fetchall()

def get_recording_by_id(conn, id):
    """
    Get a single recording by its ID.
    
    Args:
        conn: Database connection
        id: Recording ID
        
    Returns:
        tuple: Recording data or None if not found
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM recordings WHERE id=?", (id,))
    return cur.fetchone()

def update_recording(conn, recording_id, **kwargs):
    """
    Update fields of a recording.
    
    Args:
        conn: Database connection
        recording_id: ID of the recording to update
        **kwargs: Fields to update and their values
    """
    if not kwargs:
        return  # Nothing to update
        
    parameters = [f"{key} = ?" for key in kwargs]
    values = list(kwargs.values())
    values.append(recording_id)
    
    sql = f"UPDATE recordings SET {', '.join(parameters)} WHERE id = ?"
    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()

def delete_recording(conn, id):
    """
    Delete a recording by ID.
    
    Args:
        conn: Database connection
        id: Recording ID
    """
    sql = 'DELETE FROM recordings WHERE id=?'
    cur = conn.cursor()
    cur.execute(sql, (id,))
    conn.commit()