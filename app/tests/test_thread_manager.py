"""Behavior-focused tests for ThreadManager (canonicalized from v2).

Uses a minimal QThread substitute to avoid PyQt dependency while
exercising real behavior (signals, registration, cancellation).
"""

import unittest
import logging
import logging.handlers


from app.ThreadManager import ThreadManager


class _Signal:
    """Very small signal shim with connect/emit/disconnect."""

    def __init__(self) -> None:
        self._subs: list[callable] = []

    def connect(self, fn):  # type: ignore[no-untyped-def]
        self._subs.append(fn)

    def disconnect(self, fn):  # type: ignore[no-untyped-def]
        if fn in self._subs:
            self._subs.remove(fn)

    def emit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        for fn in list(self._subs):
            fn(*args, **kwargs)


class LogCapture:
    """Capture logs for a given logger name for assertions."""

    def __init__(self, logger_name: str):
        self.logger = logging.getLogger(logger_name)
        # Simple list-based handler to capture records
        self.records: list[logging.LogRecord] = []
        
        # Create a custom handler that captures to our list
        class RecordCapturingHandler(logging.Handler):
            def __init__(self, record_list):
                super().__init__()
                self.record_list = record_list
                
            def emit(self, record):
                self.record_list.append(record)
        
        self.handler = RecordCapturingHandler(self.records)
        self.handler.setLevel(logging.DEBUG)  # Capture all levels
        self.original_level = self.logger.level

    def __enter__(self):
        # Ensure the logger is enabled and set to DEBUG level
        self.logger.disabled = False
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(self.handler)
        return self

    def __exit__(self, *_):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.original_level)

    def contains(self, level: int, fragment: str) -> bool:
        """Check if any log record contains the given fragment at the specified level."""
        for rec in self.records:
            if rec.levelno == level and fragment in rec.getMessage():
                return True
        return False
    
    @property
    def buffer(self) -> list[logging.LogRecord]:
        """Compatibility property for debugging."""
        return self.records


class TestThread:
    """Minimal thread-like object compatible with ThreadManager."""

    def __init__(self) -> None:
        self.finished = _Signal()
        self._running = False
        self._cancelled = False

    # API used by ThreadManager.cancel_all_threads
    def cancel(self) -> None:
        self._cancelled = True

    def isRunning(self) -> bool:  # noqa: N802 - mimic Qt naming
        return self._running

    def wait(self, timeout: int) -> bool:  # noqa: ARG002
        # Simulate immediate finish for tests
        self._running = False
        return True

    # Helpers for tests
    def start(self) -> None:
        self._running = True
    
    @property
    def was_cancelled(self) -> bool:
        """Helper property to verify cancellation was called."""
        return self._cancelled


class BaseThreadManagerTest(unittest.TestCase):
    """Base test class with common setup and teardown for ThreadManager tests."""
    
    @classmethod
    def setUpClass(cls):
        """Configure logging for tests."""
        # Configure basic logging so loggers actually work
        # Send to NullHandler to keep tests quiet
        logging.basicConfig(level=logging.DEBUG, handlers=[logging.NullHandler()])
    
    def setUp(self) -> None:
        """Create a fresh ThreadManager singleton and common test fixtures."""
        # Reset singleton to ensure test isolation
        ThreadManager.reset_for_tests()
        self.manager = ThreadManager.create_for_testing()
        
        # Common test logger name
        self.logger_name = 'app.ThreadManager'
    
    def tearDown(self) -> None:
        """Clean up singleton state and any remaining threads."""
        # Ensure all threads are cleaned up
        for thread in list(self.manager.get_active_threads()):
            self.manager.unregister_thread(thread)
        
        # Reset singleton for next test
        ThreadManager.reset_for_tests()
    
    def create_test_thread(self, start: bool = False) -> TestThread:
        """Helper to create a test thread with optional auto-start."""
        thread = TestThread()
        if start:
            thread.start()
        return thread
    
    def create_and_register_threads(self, count: int, start: bool = True) -> list[TestThread]:
        """Helper to create and register multiple test threads."""
        threads = []
        for _ in range(count):
            thread = self.create_test_thread(start=start)
            self.manager.register_thread(thread)
            threads.append(thread)
        return threads


class TestThreadRegistration(BaseThreadManagerTest):
    """Tests for thread registration and unregistration behavior."""
    
    def test_instance_is_singleton(self):
        """Verify ThreadManager follows singleton pattern."""
        a = ThreadManager.instance()
        b = ThreadManager.instance()
        self.assertIs(a, b)

    def test_registers_thread_and_adds_to_active_list(self):
        """Verify thread registration adds thread to active list."""
        thread = self.create_test_thread()
        
        # Verify initial state
        self.assertEqual(len(self.manager.get_active_threads()), 0)
        
        # Register and verify
        self.manager.register_thread(thread)
        active = self.manager.get_active_threads()
        self.assertEqual(len(active), 1)
        self.assertIn(thread, active)

    def test_auto_unregisters_when_thread_finishes(self):
        """Verify thread is automatically unregistered when it emits finished signal."""
        thread = self.create_test_thread()
        self.manager.register_thread(thread)
        
        # Verify thread is registered
        self.assertIn(thread, self.manager.get_active_threads())
        
        # Emit finished signal and verify auto-unregistration
        thread.finished.emit()
        self.assertNotIn(thread, self.manager.get_active_threads())

    def test_warns_on_duplicate_registration(self):
        """Verify warning is logged when attempting to register the same thread twice."""
        thread = self.create_test_thread()
        
        with LogCapture('app.ThreadManager') as log:
            self.manager.register_thread(thread)
            self.manager.register_thread(thread)
        
        self.assertTrue(
            log.contains(logging.WARNING, "already registered"),
            f"Warn on duplicate registration; buf={len(log.buffer)}",
        )


class TestThreadCancellation(BaseThreadManagerTest):
    """Tests for thread cancellation behavior."""
    
    def test_cancel_all_threads_cancels_and_waits(self):
        """Verify cancel_all_threads cancels threads and waits for them to finish."""
        # Create and register multiple running threads
        threads = self.create_and_register_threads(2, start=True)
        
        # Verify threads are running
        for thread in threads:
            self.assertTrue(thread.isRunning())
            self.assertFalse(thread.was_cancelled)
        
        # Exercise cancellation
        self.manager.cancel_all_threads()
        
        # Verify threads were cancelled and are no longer running
        for thread in threads:
            self.assertTrue(thread.was_cancelled, "Thread should have been cancelled")
            self.assertFalse(thread.isRunning(), "Thread should no longer be running")

    def test_logs_warning_for_thread_without_cancel(self):
        """Verify warning is logged when thread lacks cancel() method."""
        class BasicThread:
            """Thread without cancel() method."""
            def __init__(self) -> None:
                self.finished = _Signal()
                self._running = True

            def isRunning(self) -> bool:  # noqa: N802
                return self._running

            def wait(self, timeout: int) -> bool:  # noqa: ARG002
                self._running = False
                return True

        thread = BasicThread()
        self.manager.register_thread(thread)  # type: ignore[arg-type]
        
        with LogCapture('app.ThreadManager') as log:
            self.manager.cancel_all_threads()
        
        self.assertTrue(
            log.contains(logging.WARNING, "has no cancel() method"),
            f"Warn when no cancel(); buf={len(log.buffer)}",
        )


class TestThreadManagerEdgeCases(BaseThreadManagerTest):
    """Tests for edge cases and error conditions."""

    def test_register_thread_without_finished_signal(self):
        """Verify proper error when registering thread without finished signal."""
        class NoFinished:
            pass
        
        thread_without_signal = NoFinished()
        
        # Should raise AttributeError when trying to connect to non-existent finished signal
        with self.assertRaises(AttributeError):
            self.manager.register_thread(thread_without_signal)  # type: ignore[arg-type]

    def test_register_none_object(self):
        """Verify proper error when attempting to register None."""
        # Weakref on None will fail; ensure the error surfaces clearly
        with self.assertRaises(TypeError):
            self.manager.register_thread(None)  # type: ignore[arg-type]

    def test_unregister_during_cancel(self):
        """Verify safe handling when thread unregisters itself during cancellation."""
        class SelfUnregisteringThread(TestThread):
            def cancel(self) -> None:
                super().cancel()
                # Emit finished during cancel to trigger auto-unregister
                self.finished.emit()

        thread = SelfUnregisteringThread()
        thread.start()
        self.manager.register_thread(thread)
        
        # Should not raise even though registry is mutated during iteration
        self.manager.cancel_all_threads()
        
        # Verify thread was unregistered
        self.assertNotIn(thread, self.manager.get_active_threads())

    def test_is_running_raises_exception(self):
        """Verify exception propagation when isRunning() fails."""
        class BadIsRunning(TestThread):
            def isRunning(self) -> bool:  # noqa: N802
                raise RuntimeError('isRunning failed')

        thread = BadIsRunning()
        thread.start()
        self.manager.register_thread(thread)
        
        # Exception should propagate
        with self.assertRaises(RuntimeError) as cm:
            self.manager.cancel_all_threads()
        self.assertEqual(str(cm.exception), 'isRunning failed')

    def test_wait_raises_exception(self):
        """Verify exception propagation when wait() fails."""
        class BadWait(TestThread):
            def wait(self, timeout: int) -> bool:  # noqa: ARG002
                raise RuntimeError('wait failed')

        thread = BadWait()
        thread.start()
        self.manager.register_thread(thread)
        
        # Exception should propagate
        with self.assertRaises(RuntimeError) as cm:
            self.manager.cancel_all_threads()
        self.assertEqual(str(cm.exception), 'wait failed')

    def test_cancel_all_threads_when_empty_logs_and_returns(self):
        """Verify graceful handling when no threads are active."""
        # Ensure no active threads (base class already ensures this, but double-check)
        self.assertEqual(len(self.manager.get_active_threads()), 0)
        
        with LogCapture('app.ThreadManager') as log:
            self.manager.cancel_all_threads()
        
        self.assertTrue(
            log.contains(logging.DEBUG, 'No active threads to cancel'),
            f"Logs when no threads; buf={len(log.buffer)}",
        )
