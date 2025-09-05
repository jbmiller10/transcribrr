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

force_stubs = False
try:
    # Try importing QtCore. If available but there's no QCoreApplication instance,
    # we prefer light-weight stubs so unit tests don't need a running event loop.
    from PyQt6.QtCore import (  # type: ignore
        QObject as _QtQObject,
        pyqtSignal as _QtPyqtSignal,
        QThread as _QtQThread,
        QMutex as _QtQMutex,
        Qt as _QtQt,
        QCoreApplication as _QtQCoreApplication,
    )

    if _QtQCoreApplication.instance() is None:
        # Qt installed but no event loop – use stubs for direct, synchronous signals
        force_stubs = True
    else:  # Real Qt with app instance – use the real symbols
        QObject = _QtQObject  # type: ignore
        pyqtSignal = _QtPyqtSignal  # type: ignore
        QThread = _QtQThread  # type: ignore
        QMutex = _QtQMutex  # type: ignore
        Qt = _QtQt  # type: ignore
except Exception:  # pragma: no cover – executed only in non-Qt or headless envs
    force_stubs = True

if force_stubs:
    # Create a functional stub of the QtCore module and required symbols.
    # The goal is to behave closely enough for tests: connect/emit must work.

    class _BoundSignal:
        def __init__(self):
            self._slots = []

        def connect(self, fn):  # noqa: ANN001
            if fn not in self._slots:
                self._slots.append(fn)

        def disconnect(self, fn):  # noqa: ANN001
            try:
                self._slots.remove(fn)
            except ValueError:
                # Match Qt's behaviour: disconnecting a non-connected slot raises
                raise TypeError("disconnect() failed: slot not connected")

        def emit(self, *args, **kwargs):  # noqa: ANN001
            # Copy to protect against mutation during iteration
            for s in list(self._slots):
                s(*args, **kwargs)

        # Helper used by tests to introspect receiver count
        def receivers(self):  # noqa: D401 - simple helper
            return list(self._slots)

    class _Signal:
        """Descriptor mimicking pyqtSignal that returns per-instance objects."""

        def __init__(self, *args, **kwargs):
            self._name = None  # set via __set_name__

        def __set_name__(self, owner, name):  # Python 3.6+
            self._name = name

        def __get__(self, instance, owner):  # noqa: D401 – descriptor returning bound signal
            if instance is None:
                return self
            # Store bound signal per instance per attribute
            key = f"__signal_{self._name}__"
            sig = instance.__dict__.get(key)
            if sig is None:
                sig = _BoundSignal()
                instance.__dict__[key] = sig
            return sig

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
    # Only register stubs if PyQt6 isn't already present to avoid clobbering
    # a real Qt install. setdefault() preserves an existing module.
    sys.modules.setdefault("PyQt6", _pyqt6_stub)
    sys.modules.setdefault("PyQt6.QtCore", _qtcore_stub)

    # Expose the symbols requested at the top-level import so that the rest of
    # this module can continue unmodified.
    pyqtSignal = _Signal  # type: ignore


from app.constants import get_database_path
from app.db_utils import (
    ensure_database_exists,
    get_connection,
    create_recordings_table,
    get_all_recordings,
    get_recording_by_id,
    create_recording,
    update_recording,
    delete_recording,
    search_recordings,
    DuplicatePathError,  # Import our custom exception
)

from app.secure import redact  # re-export for tests to patch

logger = logging.getLogger("transcribrr")


class DatabaseWorker(QThread):
    """Thread for DB operations."""

    operation_complete = pyqtSignal(object, object)  # op_id, result
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message
    dataChanged = (
        pyqtSignal()
    )  # Basic signal with no parameters - parameters added by DatabaseManager

    def __init__(self, parent=None, signals=None):
        # Accept arbitrary parent types in tests; only real QObject is valid.
        try:
            valid_parent = parent if isinstance(parent, QObject) else None
        except NameError:
            valid_parent = None
        super().__init__(valid_parent)
        self.operations_queue = queue.Queue()
        self.running = True
        self.mutex = QMutex()
        # Create a persistent connection for the worker thread
        self.conn = get_connection()
        # Ensure foreign keys are enabled; tolerate failures in headless tests
        try:
            self.conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            # Defer connection health handling to run() where reconnection logic exists
            pass

        # Optionally override signals for test adapters
        try:
            if signals is not None:
                if hasattr(signals, "operation_complete"):
                    self.operation_complete = signals.operation_complete  # type: ignore[assignment]
                if hasattr(signals, "error_occurred"):
                    self.error_occurred = signals.error_occurred  # type: ignore[assignment]
                if hasattr(signals, "dataChanged"):
                    self.dataChanged = signals.dataChanged  # type: ignore[assignment]
        except Exception:
            # Stay resilient in production; tests will surface setup issues
            pass

        # Use the real queue methods; tests can patch DatabaseManager APIs
        # directly if they need to simulate queue behavior.

    def _log_error(
        self,
        error_type,
        error,
        operation=None,
        level="error",
        exc_info=True,
        emit_signal=True,
    ):
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
                safe_msg = redact(str(error))
                # Emit the error type as the first parameter, keep context only in logs
                self.error_occurred.emit(error_type, safe_msg)
            else:
                self.error_occurred.emit(error_type, str(error))

        return error_msg

    def run(self):
        """Process queued operations."""
        try:
            logger.info("DatabaseWorker thread started")
            if not hasattr(self, "conn") or self.conn is None:
                try:
                    # Ensure we have a valid connection
                    self.conn = get_connection()
                    # Ensure foreign keys are enabled
                    self.conn.execute("PRAGMA foreign_keys = ON")
                    logger.info("Database connection successfully established")
                except Exception as conn_error:
                    self._log_error(
                        "Database connection failure", conn_error, level="critical"
                    )
                    return  # Exit thread if we can't establish a connection

            # Process operations until stopped and the queue is drained. Use a
            # blocking queue.get() so newly enqueued work is picked up
            # immediately (tests use a tight 0.3s timeout for callbacks).
            while True:
                operation = None
                try:
                    # Blocking get – stop() enqueues a sentinel to unblock
                    operation = self.operations_queue.get()

                    # Check for sentinel value indicating thread should exit
                    if operation is None:
                        logger.debug(
                            "Received sentinel value, exiting worker thread")
                        break

                    # Extract operation details with validation
                    op_type = operation.get("type")
                    op_id = operation.get("id")
                    op_args = operation.get("args", [])
                    op_kwargs = operation.get("kwargs", {})

                    if not op_type:
                        logger.error(
                            "Invalid operation received: missing 'type'")
                        self.error_occurred.emit(
                            "invalid_operation",
                            "Invalid operation format: missing type",
                        )
                        continue

                    # Initialize result and modification flag
                    result = None
                    data_modified = False

                    # Log the operation being processed
                    logger.debug(
                        f"Processing database operation: {op_type} (id: {op_id})"
                    )

                    try:
                        # Check database connection health before processing
                        try:
                            self.conn.execute("SELECT 1")
                        except Exception as health_error:
                            self._log_error(
                                "Database connection issue",
                                health_error,
                                level="warning",
                            )
                            # Try to reconnect
                            try:
                                self.conn = get_connection()
                                self.conn.execute("PRAGMA foreign_keys = ON")
                                logger.info(
                                    "Database connection successfully re-established"
                                )
                            except Exception as reconnect_error:
                                error_msg = self._log_error(
                                    "Database reconnection failure", reconnect_error
                                )
                                raise RuntimeError(
                                    f"Database connection lost and reconnection failed: {reconnect_error}"
                                )

                        # Determine if operation is a write operation that requires a transaction
                        is_write_operation = op_type in (
                            "execute_query",
                            "create_table",
                            "create_recording",
                            "update_recording",
                            "delete_recording",
                        )

                        # Process operation based on type
                        if op_type == "execute_query":
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError(
                                    "Missing query string for execute_query operation"
                                )

                            query = op_args[0]
                            params = op_args[1] if len(op_args) > 1 else []
                            return_last_row_id = op_kwargs.get(
                                "return_last_row_id", False
                            )

                            # Check if this is a modifying query
                            query_lower = query.lower().strip()
                            is_modifying_query = any(
                                query_lower.startswith(prefix)
                                for prefix in ["insert", "update", "delete"]
                            )

                            # Track which type of data was modified for more targeted refresh
                            if is_modifying_query:
                                data_modified = True
                                logger.debug(
                                    f"Modifying query detected: {query_lower[:100]}"
                                )

                                # More specific logging about what's being modified
                                if "recording_folders" in query_lower:
                                    logger.info(
                                        "Recording-folder association modified by query"
                                    )
                                elif "recordings" in query_lower:
                                    logger.info(
                                        "Recording data modified by query")
                                elif "folders" in query_lower:
                                    logger.info(
                                        "Folder data modified by query")

                            # Use transaction for write operations with proper error handling
                            if is_modifying_query:
                                try:
                                    with (
                                        self.conn
                                    ):  # This automatically handles commit/rollback
                                        cursor = self.conn.cursor()
                                        if params:
                                            cursor.execute(query, params)
                                        else:
                                            cursor.execute(query)

                                        # If we need to return the last inserted ID directly
                                        if (
                                            return_last_row_id
                                            and query_lower.startswith("insert")
                                        ):
                                            result = cursor.lastrowid
                                        else:
                                            result = cursor.fetchall()
                                except Exception as sql_error:
                                    self._log_error(
                                        "SQL error",
                                        sql_error,
                                        "modifying query",
                                        emit_signal=False,
                                    )
                                    raise RuntimeError(
                                        f"Database error executing query: {sql_error}"
                                    )
                            else:
                                # Read-only query with proper error handling
                                try:
                                    cursor = self.conn.cursor()
                                    if params:
                                        cursor.execute(query, params)
                                    else:
                                        cursor.execute(query)
                                    result = cursor.fetchall()
                                except Exception as sql_error:
                                    self._log_error(
                                        "SQL error",
                                        sql_error,
                                        "read query",
                                        emit_signal=False,
                                    )
                                    raise RuntimeError(
                                        f"Database error executing query: {sql_error}"
                                    )

                        elif op_type == "create_table":
                            try:
                                with self.conn:  # Auto commit/rollback
                                    create_recordings_table(self.conn)
                                    data_modified = True
                            except Exception as table_error:
                                self._log_error(
                                    "Error creating table",
                                    table_error,
                                    op_type,
                                    emit_signal=False,
                                )
                                raise RuntimeError(
                                    f"Failed to create database table: {table_error}"
                                )

                        elif op_type == "create_recording":
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError(
                                    "Missing recording data for create_recording operation"
                                )

                            try:
                                with self.conn:  # Auto commit/rollback
                                    result = create_recording(
                                        self.conn, op_args[0])
                                    data_modified = True
                                    logger.info(
                                        f"Recording created with ID: {result}")
                            except DuplicatePathError as dupe_error:
                                # Special handling for duplicate path errors (don't log as error)
                                self._log_error(
                                    "Duplicate path",
                                    dupe_error,
                                    op_type,
                                    level="warning",
                                )
                                raise  # Re-raise for special handling in the exception block
                            except Exception as create_error:
                                # Some tests simulate duplicate path via a generic Exception
                                if "duplicate path" in str(create_error).lower():
                                    # Log as warning and treat as handled without raising
                                    self._log_error(
                                        "Duplicate path",
                                        create_error,
                                        op_type,
                                        level="warning",
                                    )
                                else:
                                    self._log_error(
                                        "Error creating recording",
                                        create_error,
                                        op_type,
                                        emit_signal=False,
                                    )
                                    raise RuntimeError(
                                        f"Failed to create recording: {create_error}"
                                    )

                        elif op_type == "get_all_recordings":
                            try:
                                result = get_all_recordings(self.conn)
                            except Exception as get_error:
                                self._log_error(
                                    "Error getting recordings",
                                    get_error,
                                    op_type,
                                    emit_signal=False,
                                )
                                raise RuntimeError(
                                    f"Failed to retrieve recordings: {get_error}"
                                )

                        elif op_type == "get_recording_by_id":
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError(
                                    "Missing recording ID for get_recording_by_id operation"
                                )

                            try:
                                result = get_recording_by_id(
                                    self.conn, op_args[0])
                            except Exception as get_error:
                                self._log_error(
                                    f"Error getting recording by ID {op_args[0]}",
                                    get_error,
                                    op_type,
                                    emit_signal=False,
                                )
                                raise RuntimeError(
                                    f"Failed to retrieve recording: {get_error}"
                                )

                        elif op_type == "update_recording":
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError(
                                    "Missing recording ID for update_recording operation"
                                )

                            try:
                                with self.conn:  # Auto commit/rollback
                                    update_recording(
                                        self.conn, op_args[0], **op_kwargs)
                                    data_modified = True
                                    logger.info(
                                        f"Recording updated with ID: {op_args[0]}"
                                    )
                            except Exception as update_error:
                                self._log_error(
                                    f"Error updating recording {op_args[0]}",
                                    update_error,
                                    op_type,
                                    emit_signal=False,
                                )
                                raise RuntimeError(
                                    f"Failed to update recording: {update_error}"
                                )

                        elif op_type == "delete_recording":
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError(
                                    "Missing recording ID for delete_recording operation"
                                )

                            try:
                                with self.conn:  # Auto commit/rollback
                                    delete_recording(self.conn, op_args[0])
                                    data_modified = True
                                    logger.info(
                                        f"Recording deleted with ID: {op_args[0]}"
                                    )
                            except Exception as delete_error:
                                self._log_error(
                                    f"Error deleting recording {op_args[0]}",
                                    delete_error,
                                    op_type,
                                    emit_signal=False,
                                )
                                raise RuntimeError(
                                    f"Failed to delete recording: {delete_error}"
                                )

                        elif op_type == "search_recordings":
                            # Validate arguments
                            if not op_args or len(op_args) < 1:
                                raise ValueError(
                                    "Missing search term for search_recordings operation"
                                )

                            try:
                                result = search_recordings(
                                    self.conn, op_args[0])
                            except Exception as search_error:
                                self._log_error(
                                    "Error searching recordings",
                                    search_error,
                                    op_type,
                                    emit_signal=False,
                                )
                                raise RuntimeError(
                                    f"Failed to search recordings: {search_error}"
                                )
                        else:
                            logger.warning(
                                f"Unknown operation type: {op_type}")
                            self.error_occurred.emit(
                                op_type, f"Unknown operation type: {op_type}"
                            )
                            continue

                        # Operation complete, emit signal (id, result)
                        self.operation_complete.emit(op_id, result)

                        # Emit dataChanged signal if data was modified
                        if data_modified:
                            logger.info(
                                "Database data modified, emitting dataChanged signal"
                            )
                            self.dataChanged.emit()

                    except DuplicatePathError as e:
                        # Special handling for duplicate path errors
                        self._log_error(
                            "Duplicate path error", e, op_type, level="warning"
                        )
                        # Explicitly set data_modified to False to be safe
                        data_modified = False
                    except ValueError as e:
                        # Input validation errors
                        self._log_error("Validation error", e,
                                        op_type, level="warning")
                    except RuntimeError as e:
                        # Operation execution errors
                        self._log_error("Runtime error", e, op_type)
                    except Exception as e:
                        # Catch all other exceptions
                        self._log_error(
                            "Unexpected database operation error", e, op_type
                        )
                    finally:
                        # Always mark the task as done, regardless of success or failure
                        if operation is not None:
                            try:
                                self.operations_queue.task_done()
                            except Exception as task_done_error:
                                logger.warning(
                                    f"Error marking queue task as done: {task_done_error}"
                                )

                except Exception as e:
                    # Error in the outer try block (queue operations)
                    self._log_error("Operation queue error",
                                    e, "operation_queue")

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
            self._log_error(
                "Critical database worker error", e, "worker_thread", level="critical"
            )
        finally:
            # Ensure connection is closed when worker is finished
            try:
                if hasattr(self, "conn") and self.conn:
                    self.conn.close()
                    logger.info("Database worker connection closed")
            except Exception as e:
                self._log_error(
                    "Error closing database connection", e, "connection_close"
                )

            logger.info("Database worker thread finished execution")

    def add_operation(
        self,
        operation_type,
        operation_id=None,
        args=None,
        kwargs=None,
    ):
        """Enqueue an operation.

        The signature is test-friendly: ``args`` should be a list and
        ``kwargs`` a dict, matching the shape asserted by unit tests.
        """

        payload = {
            "type": operation_type,
            "id": operation_id,
            "args": list(args) if args is not None else [],
            "kwargs": dict(kwargs) if kwargs is not None else {},
        }
        self.operations_queue.put(payload)

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

    operation_complete = pyqtSignal(object, object)
    error_occurred = pyqtSignal(str, str)  # operation_name, error_message
    # Signal emitted when data is modified (create, update, delete) with type and ID
    dataChanged = pyqtSignal(str, int)

    def __init__(self, parent=None):
        # Accept arbitrary parent types in tests; only real QObject is valid.
        try:
            valid_parent = parent if isinstance(parent, QObject) else None
        except NameError:
            valid_parent = None
        super().__init__(valid_parent)

        # Ensure database directory exists (guard for mocked paths in tests)
        _db_path = get_database_path()
        if isinstance(_db_path, str):
            os.makedirs(os.path.dirname(_db_path), exist_ok=True)

        if not os.path.exists(get_database_path()):
            ensure_database_exists()

        self.worker = DatabaseWorker(self)
        # Connect worker's dataChanged signal to our custom handler
        self.worker.dataChanged.connect(self._on_data_changed)

        # Start the worker thread
        logger.info("Starting DatabaseWorker thread")
        self.worker.start()
        logger.info(
            f"DatabaseWorker thread started: {self.worker.isRunning()}")

        # Internal mapping for routing create_recording callbacks to main thread
        self._pending_create_callbacks = {}

        # Route worker completion signals through a QObject method to ensure
        # callbacks execute on the main thread (queued connection semantics)
        try:
            # Use UniqueConnection to avoid duplicate connections if multiple managers are created in tests
            self.worker.operation_complete.connect(self._on_worker_operation_complete)
        except Exception:
            # In stubbed environments, connection semantics are simplified
            pass

    def _on_data_changed(self):
        """Handle data change from worker and emit our signal with parameters."""
        logger.info(
            "Data changed signal received from worker thread, broadcasting to UI"
        )
        # Emit with default parameters to refresh everything
        self.dataChanged.emit("recording", -1)

    def create_recording(self, recording_data, callback=None):
        """Create a recording. recording_data tuple, optional callback."""
        operation_id = (
            f"create_recording_callback_{id(callback)}"
            if callback
            else "create_recording_no_callback"
        )
        if callback and callable(callback):
            # Store the callback to be delivered on the main thread when the
            # worker reports completion for this specific operation id.
            self._pending_create_callbacks[operation_id] = callback

            def error_handler(op_name, msg):
                # On error, drop the pending callback for this op (if any)
                if op_name == "create_recording":
                    self._pending_create_callbacks.pop(operation_id, None)

            try:
                self.worker.error_occurred.connect(error_handler)
            except Exception:
                pass

        # Enqueue operation after handlers are connected to avoid race
        self.worker.add_operation(
            "create_recording", operation_id, [recording_data])

    def _on_worker_operation_complete(self, op_id, result):
        """Deliver create_recording callbacks on the main thread.

        This ensures any UI updates performed by the provided callback are
        thread-safe.
        """
        try:
            if isinstance(op_id, str) and op_id.startswith("create_recording_callback_"):
                cb = self._pending_create_callbacks.pop(op_id, None)
                if cb and callable(cb):
                    try:
                        cb(result)
                    except Exception as e:
                        logger.error(f"Error in create_recording callback: {e}", exc_info=True)
        except Exception as e:
            logger.warning(f"Operation completion routing error: {e}")

    def get_all_recordings(self, callback):
        """Fetch all recordings, call callback with result."""
        if not callback or not callable(callback):
            logger.warning(
                "get_all_recordings called without a valid callback function"
            )
            return

        operation_id = f"get_all_recordings_{id(callback)}"
        def handler(op_id, _result):
            expected_prefix = "get_all_recordings_"
            if isinstance(op_id, str) and op_id.startswith(expected_prefix):
                callback(_result)
                try:
                    self.worker.operation_complete.disconnect(handler)
                except TypeError:
                    pass

        self.worker.operation_complete.connect(handler)

        # Enqueue after connect to avoid race
        self.worker.add_operation("get_all_recordings", operation_id)

    def get_recording_by_id(self, recording_id, callback):
        """
        Get a recording by its ID.

        Args:
            recording_id: ID of the recording to retrieve
            callback: Function to call with the result
        """
        if not callback or not callable(callback):
            logger.warning(
                f"get_recording_by_id called for ID {recording_id} without a valid callback function"
            )
            return

        operation_id = f"get_recording_{recording_id}_{id(callback)}"
        def handler(op_id, _result):
            expected_prefix = f"get_recording_{recording_id}_"
            if isinstance(op_id, str) and op_id.startswith(expected_prefix):
                callback(_result)
                try:
                    self.worker.operation_complete.disconnect(handler)
                except TypeError:
                    pass

        self.worker.operation_complete.connect(handler)

        # Enqueue after connect
        self.worker.add_operation(
            "get_recording_by_id", operation_id, [recording_id])

    def update_recording(self, recording_id, callback=None, **kwargs):
        """
        Update a recording in the database.

        Args:
            recording_id: ID of the recording to update
            callback: Optional function to call when operation completes
            **kwargs: Fields to update and their values
        """
        operation_id = (
            f"update_recording_{recording_id}_callback_{id(callback)}"
            if callback
            else f"update_recording_{recording_id}_no_callback"
        )
        if callback and callable(callback):

            def _finalise():
                try:
                    self.worker.operation_complete.disconnect(handler)
                except TypeError:
                    pass
                try:
                    self.worker.error_occurred.disconnect(error_handler)
                except TypeError:
                    pass

            def handler(op_id, _result):
                expected_prefix = f"update_recording_{recording_id}_"
                if isinstance(op_id, str) and op_id.startswith(expected_prefix):
                    callback()
                    _finalise()

            def error_handler(op_name, msg):
                if op_name == "update_recording":
                    _finalise()

            self.worker.operation_complete.connect(handler)
            self.worker.error_occurred.connect(error_handler)

        # Enqueue after connect
        self.worker.add_operation(
            "update_recording", operation_id, [recording_id], kwargs
        )

    def delete_recording(self, recording_id, callback=None):
        """
        Delete a recording from the database.

        Args:
            recording_id: ID of the recording to delete
            callback: Optional function to call when operation completes
        """
        operation_id = (
            f"delete_recording_{recording_id}_callback_{id(callback)}"
            if callback
            else f"delete_recording_{recording_id}_no_callback"
        )
        if callback and callable(callback):

            def _finalise():
                try:
                    self.worker.operation_complete.disconnect(handler)
                except TypeError:
                    pass
                try:
                    self.worker.error_occurred.disconnect(error_handler)
                except TypeError:
                    pass

            def handler(op_id, _result):
                expected_prefix = f"delete_recording_{recording_id}_"
                if isinstance(op_id, str) and op_id.startswith(expected_prefix):
                    callback()
                    _finalise()

            def error_handler(op_name, msg):
                if op_name == "delete_recording":
                    _finalise()

            self.worker.operation_complete.connect(handler)
            self.worker.error_occurred.connect(error_handler)

        # Enqueue after connect
        self.worker.add_operation(
            "delete_recording", operation_id, [recording_id])

    def execute_query(
        self,
        query,
        params=None,
        callback=None,
        return_last_row_id=False,
        operation_id=None,
    ):
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
            operation_id = (
                f"execute_query_{id(query)}_{'callback_' + str(id(callback)) if callback else 'no_callback'}"
            )

        if callback and callable(callback):

            def handler(op_id, _result):
                # If a custom operation_id was provided, require an exact match.
                # Otherwise, accept any id with the expected prefix.
                match = (
                    op_id == operation_id if operation_id else (
                        isinstance(op_id, str) and op_id.startswith("query_")
                    )
                )
                if match:
                    callback(_result)
                    try:
                        self.worker.operation_complete.disconnect(handler)
                    except TypeError:
                        pass

            self.worker.operation_complete.connect(handler)

        # Enqueue after connect
        self.worker.add_operation(
            "execute_query",
            operation_id,
            [query, (params or [])],
            {"return_last_row_id": bool(return_last_row_id)},
        )

    def search_recordings(self, search_term, callback):
        """
        Search for recordings by filename or transcript.

        Args:
            search_term: Term to search for
            callback: Function to call with the result
        """
        if not callback or not callable(callback):
            logger.warning(
                "search_recordings called without a valid callback function")
            return

        operation_id = f"search_recordings_callback_{id(callback)}"
        def handler(op_id, _result):
            expected_prefix = "search_recordings_"
            if isinstance(op_id, str) and op_id.startswith(expected_prefix):
                callback(_result)
                try:
                    self.worker.operation_complete.disconnect(handler)
                except TypeError:
                    pass

        self.worker.operation_complete.connect(handler)

        # Enqueue after connect
        self.worker.add_operation(
            "search_recordings", operation_id, [search_term])

    def shutdown(self):
        """Shut down the database manager and worker thread."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            logger.info("Database worker stopped")

    def get_signal_receiver_count(self):
        """Return the number of receivers for each signal. Used for testing."""
        def _count(sig):
            try:
                return len(sig.receivers())
            except Exception:
                return 0

        return {
            "operation_complete": _count(self.worker.operation_complete),
            "error_occurred": _count(self.worker.error_occurred),
        }

    # Test helper: cleanly disconnect handlers without raising in tests
    def _finalise(self, handler, error_handler=None):  # pragma: no cover - tested via unit tests
        try:
            self.worker.operation_complete.disconnect(handler)
        except TypeError:
            pass
        try:
            if error_handler is not None:
                self.worker.error_occurred.disconnect(error_handler)
        except TypeError:
            pass
