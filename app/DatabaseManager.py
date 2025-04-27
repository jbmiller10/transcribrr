import os
import time
import logging
import queue
# ---------------------------------------------------------------------------
# Optional PyQt6 Dependency Handling
# ---------------------------------------------------------------------------
# DatabaseManager and its helper classes rely on a handful of QtCore symbols
# (QObject, QThread, pyqtSignal, QMutex, Qt) for signalling and basic thread
# support within the GUI application.  When the full PyQt6 package is
# available these imports work as-is.  However, the *unit-test* environment
# used in continuous integration is intentionally head-less and does **not**
# install PyQt6.  Importing it there raises an ImportError and causes the
# entire test discovery process to abort before tests are even executed.
#
# To keep the public application behaviour unchanged **and** allow the test
# suite to run without the heavy GUI dependency, we wrap the import in a
# try/except block and fall back to very light-weight *stubs* that provide the
# minimal API surface needed for class construction.  These stubs **do not**
# attempt to emulate the full Qt behaviour – they simply offer the attributes
# and methods that are referenced during unit tests.  When the real PyQt6 is
# installed it will always take precedence and the stubs are bypassed.
# ---------------------------------------------------------------------------

from types import ModuleType
import sys
import threading

try:
    from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, Qt  # type: ignore
except ImportError:  # pragma: no cover – executed only in non-Qt test envs
    # Create a minimal stub of the QtCore module and the required symbols

    class _Signal:
        """Very small replacement for pyqtSignal/SignalInstance."""

        def __init__(self, *args, **kwargs):
            pass

        # When accessed via the class attribute the object itself behaves like
        # a descriptor that yields a *bound* signal instance.  For the purpose
        # of the unit tests a shared instance is perfectly fine.
        def __get__(self, instance, owner):  # noqa: D401 – simple descriptor
            return self

        # The real SignalInstance API offers connect/emit/disconnect.  They
        # can silently ignore all arguments here because the tests never rely
        # on their side-effects.
        def connect(self, *args, **kwargs):
            pass

        def disconnect(self, *args, **kwargs):
            pass

        def emit(self, *args, **kwargs):
            pass


    class QObject:  # noqa: D401 – stub
        """Light-weight QObject replacement (no signalling, no parents)."""

        def __init__(self, *args, **kwargs):
            super().__init__()


    class QThread(threading.Thread):  # noqa: D401 – stub
        """QThread stub that behaves like a plain Python thread."""

        def __init__(self, *args, **kwargs):
            threading.Thread.__init__(self)
            self._running = False

        def start(self, *args, **kwargs):  # type: ignore[override]
            self._running = True
            super().start(*args, **kwargs)

        def run(self):  # noqa: D401 – default no-op
            # Overridden in subclasses – default does nothing
            pass

        def isRunning(self):  # noqa: N802 – mimic Qt camelCase
            return self._running and self.is_alive()

        def wait(self):
            self.join()


    class QMutex:  # noqa: D401 – stub
        """Simplistic, non-recursive mutex implementation."""

        def __init__(self):
            self._lock = threading.Lock()

        def lock(self):
            self._lock.acquire()

        def unlock(self):
            self._lock.release()


    class _ConnectionType:  # noqa: D401 – stub enumeration
        UniqueConnection = 0


    class _Qt:  # noqa: D401 – stub container for ConnectionType
        ConnectionType = _ConnectionType


    Qt = _Qt  # noqa: N801 – align with "from PyQt6.QtCore import Qt"

    # Provide a stubbed QtCore module so that *any* subsequent
    # "import PyQt6.QtCore" receives the same objects.  This prevents duplicate
    # creation of incompatible stubs if multiple files perform their own
    # guarded import.
    _qtcore_stub = ModuleType("PyQt6.QtCore")
    _qtcore_stub.QObject = QObject
    _qtcore_stub.QThread = QThread
    _qtcore_stub.QMutex = QMutex
    _qtcore_stub.pyqtSignal = _Signal  # type: ignore
    _qtcore_stub.Qt = Qt  # type: ignore

    # We also provide a parent "PyQt6" package so that "import PyQt6" works.
    _pyqt6_stub = ModuleType("PyQt6")
    _pyqt6_stub.QtCore = _qtcore_stub  # type: ignore

    # Register the stubs in sys.modules *before* assigning to local names so
    # that any follow-up imports (also in other files) resolve correctly.
    sys.modules.setdefault("PyQt6", _pyqt6_stub)
    sys.modules.setdefault("PyQt6.QtCore", _qtcore_stub)

    # Expose the symbols requested at the top-level import so that the rest of
    # this module can continue unmodified.
    pyqtSignal = _Signal  # type: ignore



from app.constants import get_database_path
from app.db_utils import (
    ensure_database_exists, get_connection, create_recordings_table,
    get_all_recordings, get_recording_by_id, create_recording, 
    update_recording, delete_recording, search_recordings,
    DuplicatePathError  # Import our custom exception
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

    def _log_error(self, error_type, error, operation=None, level="error", exc_info=True, emit_signal=True):
        """
        Centralized error handling helper to reduce code duplication.
        
        Args:
            error_type: Type of error (for signal and logging)
            error: The exception or error message
            operation: Optional operation type for context
            level: Logging level (debug, info, warning, error, critical)
            exc_info: Whether to include exception info in log
            emit_signal: Whether to emit the error_occurred signal
        """
        # Format operation context if provided
        op_context = f" in {operation}" if operation else ""
        
        # Get the logging function based on level
        log_func = getattr(logger, level)
        
        # Log the error
        error_msg = f"{error_type}{op_context}: {error}"
        log_func(error_msg, exc_info=exc_info)
        
        # Emit signal if requested
        if emit_signal:
            # For user-facing messages, we may want to redact sensitive info
            if level in ("error", "critical"):
                from app.secure import redact
                safe_msg = redact(str(error))
                self.error_occurred.emit(operation or error_type, f"{error_type}: {safe_msg}")
            else:
                self.error_occurred.emit(operation or error_type, str(error))
                
        return error_msg
        
    def run(self):
        """Process queued operations."""
        try:
            logger.info("DatabaseWorker thread started")
            if not hasattr(self, 'conn') or self.conn is None:
                try:
                    # Ensure we have a valid connection
                    self.conn = get_connection()
                    # Ensure foreign keys are enabled
                    self.conn.execute("PRAGMA foreign_keys = ON;")
                    logger.info("Database connection successfully established")
                except Exception as conn_error:
                    self._log_error("Database connection failure", conn_error, level="critical")
                    return  # Exit thread if we can't establish a connection
            
            while self.running:
                operation = None
                try:
                    # Queue.get with timeout to allow for thread interruption
                    try:
                        operation = self.operations_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue  # No operation available, continue the loop
                    
                    # Check for sentinel value indicating thread should exit
                    if operation is None:
                        logger.debug("Received sentinel value, exiting worker thread")
                        break

                    # Extract operation details with validation
                    op_type = operation.get('type')
                    op_id = operation.get('id')
                    op_args = operation.get('args', [])
                    op_kwargs = operation.get('kwargs', {})
                    
                    if not op_type:
                        logger.error("Invalid operation received: missing 'type'")
                        self.error_occurred.emit("invalid_operation", "Invalid operation format: missing type")
                        continue
                        
                    # Initialize result and modification flag
                    result = None
                    data_modified = False
                    
                    # Log the operation being processed
                    logger.debug(f"Processing database operation: {op_type} (id: {op_id})")
                    
                    try:
                        # Check database connection health before processing
                        try:
                            self.conn.execute("SELECT 1")
                        except Exception as health_error:
                            self._log_error("Database connection issue", health_error, level="warning")
                            # Try to reconnect
                            try:
                                self.conn = get_connection()
                                self.conn.execute("PRAGMA foreign_keys = ON;")
                                logger.info("Database connection successfully re-established")
                            except Exception as reconnect_error:
                                error_msg = self._log_error("Database reconnection failure", reconnect_error)
                                raise RuntimeError(f"Database connection lost and reconnection failed: {reconnect_error}")
                        
                        # Determine if operation is a write operation that requires a transaction
                        is_write_operation = op_type in ('execute_query', 'create_table', 'create_recording', 
                                                        'update_recording', 'delete_recording')
                        
                        # Process operation based on type
                        if op_type == 'execute_query':
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError("Missing query string for execute_query operation")
                                
                            query = op_args[0]
                            params = op_args[1] if len(op_args) > 1 else []
                            return_last_row_id = op_kwargs.get('return_last_row_id', False)
                            
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
                            
                            # Use transaction for write operations with proper error handling
                            if is_modifying_query:
                                try:
                                    with self.conn:  # This automatically handles commit/rollback
                                        cursor = self.conn.cursor()
                                        cursor.execute(query, params)
                                        
                                        # If we need to return the last inserted ID directly
                                        if return_last_row_id and query_lower.startswith('insert'):
                                            result = cursor.lastrowid
                                        else:
                                            result = cursor.fetchall()
                                except Exception as sql_error:
                                    self._log_error("SQL error", sql_error, "modifying query", emit_signal=False)
                                    raise RuntimeError(f"Database error executing query: {sql_error}")
                            else:
                                # Read-only query with proper error handling
                                try:
                                    cursor = self.conn.cursor()
                                    cursor.execute(query, params)
                                    result = cursor.fetchall()
                                except Exception as sql_error:
                                    self._log_error("SQL error", sql_error, "read query", emit_signal=False)
                                    raise RuntimeError(f"Database error executing query: {sql_error}")
                                
                        elif op_type == 'create_table':
                            try:
                                with self.conn:  # Auto commit/rollback
                                    create_recordings_table(self.conn)
                                    data_modified = True
                            except Exception as table_error:
                                self._log_error("Error creating table", table_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to create database table: {table_error}")
                                
                        elif op_type == 'create_recording':
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError("Missing recording data for create_recording operation")
                                
                            try:
                                with self.conn:  # Auto commit/rollback
                                    result = create_recording(self.conn, op_args[0])
                                    data_modified = True
                                    logger.info(f"Recording created with ID: {result}")
                            except DuplicatePathError as dupe_error:
                                # Special handling for duplicate path errors (don't log as error)
                                self._log_error("Duplicate path", dupe_error, op_type, level="warning")
                                raise  # Re-raise for special handling in the exception block
                            except Exception as create_error:
                                self._log_error("Error creating recording", create_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to create recording: {create_error}")
                                
                        elif op_type == 'get_all_recordings':
                            try:
                                result = get_all_recordings(self.conn)
                            except Exception as get_error:
                                self._log_error("Error getting recordings", get_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to retrieve recordings: {get_error}")
                            
                        elif op_type == 'get_recording_by_id':
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError("Missing recording ID for get_recording_by_id operation")
                                
                            try:
                                result = get_recording_by_id(self.conn, op_args[0])
                            except Exception as get_error:
                                self._log_error(f"Error getting recording by ID {op_args[0]}", get_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to retrieve recording: {get_error}")
                            
                        elif op_type == 'update_recording':
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError("Missing recording ID for update_recording operation")
                                
                            try:
                                with self.conn:  # Auto commit/rollback
                                    update_recording(self.conn, op_args[0], **op_kwargs)
                                    data_modified = True
                                    logger.info(f"Recording updated with ID: {op_args[0]}")
                            except Exception as update_error:
                                self._log_error(f"Error updating recording {op_args[0]}", update_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to update recording: {update_error}")
                                
                        elif op_type == 'delete_recording':
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError("Missing recording ID for delete_recording operation")
                                
                            try:
                                with self.conn:  # Auto commit/rollback
                                    delete_recording(self.conn, op_args[0])
                                    data_modified = True
                                    logger.info(f"Recording deleted with ID: {op_args[0]}")
                            except Exception as delete_error:
                                self._log_error(f"Error deleting recording {op_args[0]}", delete_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to delete recording: {delete_error}")
                                
                        elif op_type == 'search_recordings':
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError("Missing search term for search_recordings operation")
                                
                            try:
                                result = search_recordings(self.conn, op_args[0])
                            except Exception as search_error:
                                self._log_error("Error searching recordings", search_error, op_type, emit_signal=False)
                                raise RuntimeError(f"Failed to search recordings: {search_error}")
                        else:
                            logger.warning(f"Unknown operation type: {op_type}")
                            self.error_occurred.emit(op_type, f"Unknown operation type: {op_type}")
                            continue
                                
                        # Operation complete, emit signal
                        self.operation_complete.emit({
                            'id': op_id,
                            'type': op_type,
                            'result': result
                        })
                        
                        # Emit dataChanged signal if data was modified
                        if data_modified:
                            logger.info("Database data modified, emitting dataChanged signal")
                            self.dataChanged.emit()
                        
                    except DuplicatePathError as e:
                        # Special handling for duplicate path errors
                        self._log_error("Duplicate path error", e, op_type, level="warning")
                        # Explicitly set data_modified to False to be safe
                        data_modified = False
                    except ValueError as e:
                        # Input validation errors
                        self._log_error("Validation error", e, op_type, level="warning")
                    except RuntimeError as e:
                        # Operation execution errors
                        self._log_error("Runtime error", e, op_type)
                    except Exception as e:
                        # Catch all other exceptions
                        self._log_error("Unexpected database operation error", e, op_type)
                    finally:
                        # Always mark the task as done, regardless of success or failure
                        if operation is not None:
                            try:
                                self.operations_queue.task_done()
                            except Exception as task_done_error:
                                logger.warning(f"Error marking queue task as done: {task_done_error}")

                except queue.Empty:
                    # This shouldn't happen since we already handle it above, but just in case
                    continue
                except Exception as e:
                    # Error in the outer try block (queue operations)
                    self._log_error("Operation queue error", e, "operation_queue")
                    
                    # Try to mark the task as done if we have an operation
                    if operation is not None:
                        try:
                            self.operations_queue.task_done()
                        except Exception:
                            pass
                    
                    # Short sleep to prevent CPU spinning in case of persistent errors
                    time.sleep(0.1)

        except Exception as e:
            # Error in the outermost try block (worker thread itself)
            self._log_error("Critical database worker error", e, "worker_thread", level="critical")
        finally:
            # Ensure connection is closed when worker is finished
            try:
                if hasattr(self, 'conn') and self.conn:
                    self.conn.close()
                    logger.info("Database worker connection closed")
            except Exception as e:
                self._log_error("Error closing database connection", e, "connection_close")
            
            logger.info("Database worker thread finished execution")

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
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(get_database_path()), exist_ok=True)
        
        if not os.path.exists(get_database_path()):
            ensure_database_exists()
        
        self.worker = DatabaseWorker()
        self.worker.operation_complete.connect(self.operation_complete)
        self.worker.error_occurred.connect(self.error_occurred)
        # Connect worker's dataChanged signal to our custom handler
        self.worker.dataChanged.connect(self._on_data_changed)
        
        # Start the worker thread
        logger.info("Starting DatabaseWorker thread")
        self.worker.start()
        logger.info(f"DatabaseWorker thread started: {self.worker.isRunning()}")
        
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

    def execute_query(self, query, params=None, callback=None, return_last_row_id=False, operation_id=None):
        """
        Execute a custom SQL query.
        
        Args:
            query: SQL query to execute
            params: Parameters for the query
            callback: Optional function to call with the result
            return_last_row_id: If True, returns last_insert_rowid() directly after INSERT
            operation_id: Optional custom operation ID to use for callback binding
        """
        if operation_id is None:
            operation_id = f"query_{id(query)}_{id(callback) if callback else 'no_callback'}"
        
        # Use the operation_id for callback binding
        self.worker.add_operation('execute_query', operation_id, query, params or [], return_last_row_id=return_last_row_id)
        
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
