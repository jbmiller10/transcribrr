"""Manage QThread lifecycle via singleton registry.

This module should be importable in environments without Qt installed
(e.g., headless CI). We therefore attempt to import ``QThread`` from
PyQt6 first, then fall back to PySide6, and finally to a minimal stub
class so tests that mock thread objects can run without Qt.
"""

import logging
from typing import Dict, List, Optional

# Try to import Qt's QThread, but gracefully fall back if unavailable.
try:  # Prefer PyQt6 when available
    from PyQt6.QtCore import QThread  # type: ignore
except Exception:  # pragma: no cover - exercised in CI without Qt
    try:  # Allow PySide6 as an alternative
        from PySide6.QtCore import QThread  # type: ignore
    except Exception:  # Final fallback: minimal stub for typing/runtime
        class QThread:  # type: ignore
            pass

logger = logging.getLogger(__name__)


class ThreadManager:
    """Singleton for managing QThreads."""

    _instance: Optional["ThreadManager"] = None

    @classmethod
    def instance(cls) -> "ThreadManager":
        """Return singleton ThreadManager."""
        if cls._instance is None:
            cls._instance = ThreadManager()
        return cls._instance

    def __init__(self):
        self._active_threads: Dict[int, QThread] = {}
        logger.debug("ThreadManager initialized")

    def register_thread(self, thread: QThread) -> None:
        thread_id = id(thread)
        if thread_id in self._active_threads:
            logger.warning(f"Thread {thread_id} already registered")
            return

        self._active_threads[thread_id] = thread
        logger.debug(
            f"Thread registered: {thread.__class__.__name__} (id: {thread_id})"
        )

        # Use a weak reference inside the slot to avoid keeping the thread
        # alive after it finishes (lambda would otherwise hold a strong ref).
        import weakref

        weak_thread = weakref.ref(thread)

        def _auto_unregister():
            t = weak_thread()
            if t is not None:
                self.unregister_thread(t)

        thread.finished.connect(_auto_unregister)

    def unregister_thread(self, thread: QThread) -> None:
        thread_id = id(thread)
        if thread_id in self._active_threads:
            del self._active_threads[thread_id]
            logger.debug(
                f"Thread unregistered: {thread.__class__.__name__} (id: {thread_id})"
            )
        else:
            logger.debug(
                f"Attempted to unregister non-registered thread: {thread.__class__.__name__} (id: {thread_id})"
            )

    def get_active_threads(self) -> List[QThread]:
        return list(self._active_threads.values())

    def cancel_all_threads(self, wait_timeout: int = 5000) -> None:
        """Cancel all active threads."""
        threads = self.get_active_threads()
        thread_count = len(threads)

        if thread_count == 0:
            logger.debug("No active threads to cancel")
            return

        logger.info(f"Cancelling {thread_count} active threads")

        for thread in threads:
            thread_name = thread.__class__.__name__
            thread_id = id(thread)

            logger.debug(
                f"Attempting to cancel thread: {thread_name} (id: {thread_id})"
            )

            if hasattr(thread, "cancel") and callable(getattr(thread, "cancel")):
                try:
                    thread.cancel()
                    logger.debug(f"Called cancel() on thread: {thread_name}")
                except Exception as e:
                    logger.error(
                        f"Error cancelling thread {thread_name}: {str(e)}")
            else:
                logger.warning(f"Thread {thread_name} has no cancel() method")

            if thread.isRunning():
                logger.debug(
                    f"Waiting for thread {thread_name} to finish (timeout: {wait_timeout}ms)"
                )
                thread_finished = thread.wait(wait_timeout)

                if not thread_finished:
                    logger.warning(
                        f"Thread {thread_name} did not finish within timeout"
                    )
                    # Thread will be forcefully terminated by cleanup_application in main.py
                else:
                    logger.debug(f"Thread {thread_name} finished successfully")
