"""
Thread Manager responsible for centralized thread tracking and lifecycle management.

This module provides a singleton ThreadManager that keeps track of all active QThreads
in the application, making thread cleanup and application exit more reliable.
"""

import logging
from typing import Dict, List, Optional
from PyQt6.QtCore import QThread

logger = logging.getLogger(__name__)

class ThreadManager:
    """
    Singleton class that manages all QThreads in the application.
    
    This class maintains a registry of active threads, provides methods to register
    and unregister threads, and offers functionality to cancel all active threads
    during application shutdown.
    """
    
    _instance: Optional['ThreadManager'] = None
    
    @classmethod
    def instance(cls) -> 'ThreadManager':
        """
        Get the singleton instance of ThreadManager.
        
        Returns:
            ThreadManager: The singleton instance
        """
        if cls._instance is None:
            cls._instance = ThreadManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the ThreadManager."""
        self._active_threads: Dict[int, QThread] = {}
        logger.debug("ThreadManager initialized")
    
    def register_thread(self, thread: QThread) -> None:
        """
        Register a new thread with the manager.
        
        Args:
            thread: QThread instance to register
        """
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
        """
        Unregister a thread from the manager.
        
        Args:
            thread: QThread instance to unregister
        """
        thread_id = id(thread)
        if thread_id in self._active_threads:
            del self._active_threads[thread_id]
            logger.debug(f"Thread unregistered: {thread.__class__.__name__} (id: {thread_id})")
        else:
            logger.debug(f"Attempted to unregister non-registered thread: {thread.__class__.__name__} (id: {thread_id})")
    
    def get_active_threads(self) -> List[QThread]:
        """
        Get a list of all active threads.
        
        Returns:
            List[QThread]: List of active thread instances
        """
        return list(self._active_threads.values())
    
    def cancel_all_threads(self, wait_timeout: int = 5000) -> None:
        """
        Cancel all active threads and wait for them to finish.
        
        Args:
            wait_timeout: Maximum time in ms to wait for each thread to finish
        """
        threads = self.get_active_threads()
        thread_count = len(threads)
        
        if thread_count == 0:
            logger.debug("No active threads to cancel")
            return
        
        logger.info(f"Cancelling {thread_count} active threads")
        
        for thread in threads:
            thread_name = thread.__class__.__name__
            thread_id = id(thread)
            
            logger.debug(f"Attempting to cancel thread: {thread_name} (id: {thread_id})")
            
            # Call cancel() method if it exists
            if hasattr(thread, 'cancel') and callable(getattr(thread, 'cancel')):
                try:
                    thread.cancel()
                    logger.debug(f"Called cancel() on thread: {thread_name}")
                except Exception as e:
                    logger.error(f"Error cancelling thread {thread_name}: {str(e)}")
            else:
                logger.warning(f"Thread {thread_name} has no cancel() method")
            
            # Wait for the thread to finish
            if thread.isRunning():
                logger.debug(f"Waiting for thread {thread_name} to finish (timeout: {wait_timeout}ms)")
                thread_finished = thread.wait(wait_timeout)
                
                if not thread_finished:
                    logger.warning(f"Thread {thread_name} did not finish within timeout")
                    # Thread will be forcefully terminated by cleanup_application in main.py
                else:
                    logger.debug(f"Thread {thread_name} finished successfully")