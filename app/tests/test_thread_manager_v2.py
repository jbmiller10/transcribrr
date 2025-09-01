"""Improved behavior-focused tests for ThreadManager.

Uses a minimal QThread substitute to avoid PyQt dependency while
exercising real behavior (signals, registration, cancellation).
"""

import unittest

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

