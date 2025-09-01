"""Improved behavior-focused tests for ThreadManager.

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
        self.handler = logging.handlers.MemoryHandler(1000)
        self.original_level = self.logger.level

    def __enter__(self):
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *_):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.original_level)

    def contains(self, level: int, fragment: str) -> bool:
        for rec in self.handler.buffer:
            if rec.levelno == level and fragment in rec.getMessage():
                return True
        return False


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


class TestThreadRegistration(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ThreadManager.instance()
        # Ensure a clean slate using public API
        for t in list(self.manager.get_active_threads()):
            self.manager.unregister_thread(t)

    def test_instance_is_singleton(self):
        a = ThreadManager.instance()
        b = ThreadManager.instance()
        self.assertIs(a, b)

    def test_registers_thread_and_adds_to_active_list(self):
        thread = TestThread()
        self.assertEqual(len(self.manager.get_active_threads()), 0)
        self.manager.register_thread(thread)
        active = self.manager.get_active_threads()
        self.assertEqual(len(active), 1)
        self.assertIn(thread, active)

    def test_auto_unregisters_when_thread_finishes(self):
        thread = TestThread()
        self.manager.register_thread(thread)
        self.assertIn(thread, self.manager.get_active_threads())
        # Emit finished signal
        thread.finished.emit()
        self.assertNotIn(thread, self.manager.get_active_threads())

    def test_warns_on_duplicate_registration(self):
        thread = TestThread()
        with LogCapture('app.ThreadManager') as log:
            self.manager.register_thread(thread)
            self.manager.register_thread(thread)
        self.assertTrue(
            log.contains(logging.WARNING, "already registered"),
            "Should warn on duplicate registration",
        )


class TestThreadCancellation(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ThreadManager.instance()
        for t in list(self.manager.get_active_threads()):
            self.manager.unregister_thread(t)

    def test_cancel_all_threads_cancels_and_waits(self):
        t1, t2 = TestThread(), TestThread()
        t1.start(); t2.start()
        self.manager.register_thread(t1)
        self.manager.register_thread(t2)

        # Exercise cancellation
        self.manager.cancel_all_threads()

        # Threads should have been waited and no longer considered running
        self.assertFalse(t1.isRunning())
        self.assertFalse(t2.isRunning())

    def test_logs_warning_for_thread_without_cancel(self):
        class BasicThread:
            def __init__(self) -> None:
                self.finished = _Signal()
                self._running = True

            def isRunning(self) -> bool:  # noqa: N802
                return self._running

            def wait(self, timeout: int) -> bool:  # noqa: ARG002
                self._running = False
                return True

        t = BasicThread()
        self.manager.register_thread(t)  # type: ignore[arg-type]
        with LogCapture('app.ThreadManager') as log:
            self.manager.cancel_all_threads()
        self.assertTrue(
            log.contains(logging.WARNING, "has no cancel() method"),
            "Should log a warning for thread without cancel()",
        )


class TestThreadManagerEdgeCases(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = ThreadManager.instance()
        for t in list(self.manager.get_active_threads()):
            self.manager.unregister_thread(t)

    def tearDown(self) -> None:
        for t in list(self.manager.get_active_threads()):
            self.manager.unregister_thread(t)

    def test_register_thread_without_finished_signal(self):
        class NoFinished:
            pass
        nf = NoFinished()
        with self.assertRaises(AttributeError):
            self.manager.register_thread(nf)  # type: ignore[arg-type]
        # Cleanup: ensure not tracked
        self.manager.unregister_thread(nf)  # type: ignore[arg-type]

    def test_register_none_object(self):
        # Weakref on None will fail; ensure the error surfaces clearly
        with self.assertRaises(TypeError):
            self.manager.register_thread(None)  # type: ignore[arg-type]
        # Nothing to cleanup beyond assertion

    def test_unregister_during_cancel(self):
        class T(TestThread):
            def cancel(self) -> None:
                super().cancel()
                # Emit finished during cancel to trigger auto-unregister
                self.finished.emit()

        t = T(); t.start()
        self.manager.register_thread(t)
        # Should not raise even though registry is mutated during iteration
        self.manager.cancel_all_threads()
        self.assertNotIn(t, self.manager.get_active_threads())

    def test_is_running_raises_exception(self):
        class BadIsRunning(TestThread):
            def isRunning(self) -> bool:  # noqa: N802
                raise RuntimeError('isRunning failed')

        t = BadIsRunning(); t.start()
        self.manager.register_thread(t)
        with self.assertRaises(RuntimeError):
            self.manager.cancel_all_threads()

    def test_wait_raises_exception(self):
        class BadWait(TestThread):
            def wait(self, timeout: int) -> bool:  # noqa: ARG002
                raise RuntimeError('wait failed')

        t = BadWait(); t.start()
        self.manager.register_thread(t)
        with self.assertRaises(RuntimeError):
            self.manager.cancel_all_threads()

    def test_cancel_all_threads_when_empty_logs_and_returns(self):
        # Ensure no active threads
        for t in list(self.manager.get_active_threads()):
            self.manager.unregister_thread(t)
        with LogCapture('app.ThreadManager') as log:
            self.manager.cancel_all_threads()
        self.assertTrue(log.contains(logging.DEBUG, 'No active threads to cancel'))
