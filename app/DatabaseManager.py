import os
import logging
import queue
import sqlite3
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
                            
                            # Use transaction for write operations
                            if is_modifying_query:
                                with self.conn:  # This automatically handles commit/rollback
                                    cursor = self.conn.cursor()
                                    cursor.execute(query, params)
                                    
                                    # If we need to return the last inserted ID directly
                                    if return_last_row_id and query_lower.startswith('insert'):
                                        result = cursor.lastrowid
                                        # Return the last insert ID directly
                                    else:
                                        result = cursor.fetchall()
                                        # Return the query results
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
                        logger.error(f"Duplicate path error in {op_type}: {e}", exc_info=True)
                        # Emit error but DO NOT set data_modified to prevent phantom refresh
                        self.error_occurred.emit(op_type, str(e))
                        # Explicitly set data_modified to False to be safe
                        data_modified = False
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
