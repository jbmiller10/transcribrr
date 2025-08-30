"""Test the ThreadManager functionality."""

import unittest
import weakref
from unittest.mock import MagicMock, Mock, patch, call
import logging


class TestThreadManager(unittest.TestCase):
    """Test ThreadManager singleton and thread management functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Reset singleton state for each test
        from app.ThreadManager import ThreadManager
        ThreadManager._instance = None
        
        # Create a fresh instance for testing
        self.thread_manager = ThreadManager.instance()
        
        # Clear active threads
        self.thread_manager._active_threads = {}
        
        # Set up logger mock
        self.logger_patcher = patch('app.ThreadManager.logger')
        self.mock_logger = self.logger_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.logger_patcher.stop()
        
        # Reset singleton state
        from app.ThreadManager import ThreadManager
        ThreadManager._instance = None

    # ============= Singleton Pattern Tests =============

    def test_singleton_creation_first_call(self):
        """Tests singleton creation on first call."""
        from app.ThreadManager import ThreadManager
        
        # Reset singleton to ensure fresh start
        ThreadManager._instance = None
        
        # First call should create new instance
        instance = ThreadManager.instance()
        
        # Verify instance is created
        self.assertIsNotNone(instance)
        self.assertIsInstance(instance, ThreadManager)
        
        # Verify _instance is set
        self.assertEqual(ThreadManager._instance, instance)
        
        # Verify initialization log
        self.mock_logger.debug.assert_any_call("ThreadManager initialized")

    def test_singleton_returns_same_instance(self):
        """Tests singleton returns same instance on subsequent calls."""
        from app.ThreadManager import ThreadManager
        
        # Reset and get first instance
        ThreadManager._instance = None
        instance1 = ThreadManager.instance()
        
        # Clear logger calls from first creation
        self.mock_logger.reset_mock()
        
        # Get second and third instances
        instance2 = ThreadManager.instance()
        instance3 = ThreadManager.instance()
        
        # All should be the same instance
        self.assertIs(instance1, instance2)
        self.assertIs(instance2, instance3)
        
        # No additional initialization logging should occur
        self.mock_logger.debug.assert_not_called()

    def test_direct_initialization(self):
        """Tests initialization of ThreadManager instance."""
        from app.ThreadManager import ThreadManager
        
        # Reset singleton
        ThreadManager._instance = None
        
        # Direct instantiation (not through instance())
        manager = ThreadManager()
        
        # Verify _active_threads is initialized as empty dictionary
        self.assertEqual(manager._active_threads, {})
        
        # Verify initialization log
        self.mock_logger.debug.assert_called_with("ThreadManager initialized")

    # ============= Thread Registration Tests =============

    def test_register_thread_success(self):
        """Tests successful thread registration."""
        # Create mock thread
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        mock_thread.finished = MagicMock()
        thread_id = id(mock_thread)
        
        # Mock weakref
        with patch('weakref.ref') as mock_weakref:
            mock_weak_ref = MagicMock()
            mock_weakref.return_value = mock_weak_ref
            
            # Register thread
            self.thread_manager.register_thread(mock_thread)
        
        # Verify thread is added to _active_threads
        self.assertIn(thread_id, self.thread_manager._active_threads)
        self.assertEqual(self.thread_manager._active_threads[thread_id], mock_thread)
        
        # Verify debug log message
        self.mock_logger.debug.assert_called_with(
            f"Thread registered: TestThread (id: {thread_id})"
        )
        
        # Verify finished signal is connected
        mock_thread.finished.connect.assert_called_once()
        
        # Verify weak reference is created
        mock_weakref.assert_called_once_with(mock_thread)

    def test_register_thread_duplicate(self):
        """Tests duplicate thread registration handling."""
        # Create and register first thread
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        mock_thread.finished = MagicMock()
        thread_id = id(mock_thread)
        
        # Register thread first time
        with patch('weakref.ref'):
            self.thread_manager.register_thread(mock_thread)
        
        # Clear mock calls
        self.mock_logger.reset_mock()
        mock_thread.finished.connect.reset_mock()
        
        # Try to register same thread again
        self.thread_manager.register_thread(mock_thread)
        
        # Verify warning log message
        self.mock_logger.warning.assert_called_with(
            f"Thread {thread_id} already registered"
        )
        
        # Verify thread is not added again (still only one entry)
        self.assertEqual(len(self.thread_manager._active_threads), 1)
        
        # Verify finished signal is not connected again
        mock_thread.finished.connect.assert_not_called()

    def test_register_thread_auto_unregister_callback(self):
        """Tests automatic unregistration callback setup."""
        # Create mock thread
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        mock_thread.finished = MagicMock()
        
        # Mock weakref that returns the thread
        mock_weak_ref = MagicMock()
        mock_weak_ref.return_value = mock_thread
        
        callback_func = None
        
        # Capture the callback function
        def capture_callback(func):
            nonlocal callback_func
            callback_func = func
        
        mock_thread.finished.connect.side_effect = capture_callback
        
        with patch('weakref.ref', return_value=mock_weak_ref):
            self.thread_manager.register_thread(mock_thread)
        
        # Verify callback was connected
        self.assertIsNotNone(callback_func)
        
        # Clear logger to check unregister logs
        self.mock_logger.reset_mock()
        
        # Simulate thread finished by calling the callback
        callback_func()
        
        # Verify unregister_thread was called (thread removed)
        self.assertNotIn(id(mock_thread), self.thread_manager._active_threads)
        
        # Verify unregister log
        self.mock_logger.debug.assert_called_with(
            f"Thread unregistered: TestThread (id: {id(mock_thread)})"
        )

    def test_register_thread_weak_ref_garbage_collected(self):
        """Tests weak reference cleanup when thread is garbage collected."""
        # Create mock thread
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        mock_thread.finished = MagicMock()
        
        # Mock weakref that returns None (garbage collected)
        mock_weak_ref = MagicMock()
        mock_weak_ref.return_value = None
        
        callback_func = None
        
        # Capture the callback function
        def capture_callback(func):
            nonlocal callback_func
            callback_func = func
        
        mock_thread.finished.connect.side_effect = capture_callback
        
        with patch('weakref.ref', return_value=mock_weak_ref):
            self.thread_manager.register_thread(mock_thread)
        
        # Thread is registered initially
        self.assertIn(id(mock_thread), self.thread_manager._active_threads)
        
        # Clear logger
        self.mock_logger.reset_mock()
        
        # Simulate thread finished with garbage collected thread
        callback_func()
        
        # Thread should still be in registry (not unregistered when weak_ref returns None)
        self.assertIn(id(mock_thread), self.thread_manager._active_threads)
        
        # No unregister log should occur
        self.mock_logger.debug.assert_not_called()

    # ============= Thread Unregistration Tests =============

    def test_unregister_thread_success(self):
        """Tests successful thread unregistration."""
        # Create and register mock thread
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        thread_id = id(mock_thread)
        
        # Manually add to active threads (bypass registration)
        self.thread_manager._active_threads[thread_id] = mock_thread
        
        # Unregister thread
        self.thread_manager.unregister_thread(mock_thread)
        
        # Verify thread is removed from _active_threads
        self.assertNotIn(thread_id, self.thread_manager._active_threads)
        
        # Verify debug log message
        self.mock_logger.debug.assert_called_with(
            f"Thread unregistered: TestThread (id: {thread_id})"
        )

    def test_unregister_thread_not_registered(self):
        """Tests unregistering non-registered thread."""
        # Create mock thread that's not registered
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        thread_id = id(mock_thread)
        
        # Ensure _active_threads is empty
        self.assertEqual(len(self.thread_manager._active_threads), 0)
        
        # Try to unregister non-registered thread
        self.thread_manager.unregister_thread(mock_thread)
        
        # Verify debug log message about non-registered thread
        self.mock_logger.debug.assert_called_with(
            f"Attempted to unregister non-registered thread: TestThread (id: {thread_id})"
        )
        
        # Verify _active_threads remains unchanged (still empty)
        self.assertEqual(len(self.thread_manager._active_threads), 0)

    # ============= Active Threads Retrieval Tests =============

    def test_get_active_threads_multiple(self):
        """Tests retrieving list of active threads."""
        # Create multiple mock threads
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread2 = MagicMock()
        thread2.__class__.__name__ = "Thread2"
        thread3 = MagicMock()
        thread3.__class__.__name__ = "Thread3"
        
        # Manually add threads to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        self.thread_manager._active_threads[id(thread2)] = thread2
        self.thread_manager._active_threads[id(thread3)] = thread3
        
        # Get active threads
        active_threads = self.thread_manager.get_active_threads()
        
        # Verify all threads are returned
        self.assertEqual(len(active_threads), 3)
        self.assertIn(thread1, active_threads)
        self.assertIn(thread2, active_threads)
        self.assertIn(thread3, active_threads)
        
        # Verify it's a copy, not reference to internal dictionary
        active_threads.clear()
        self.assertEqual(len(self.thread_manager._active_threads), 3)

    def test_get_active_threads_empty(self):
        """Tests retrieving empty list when no threads."""
        # Ensure no threads are registered
        self.thread_manager._active_threads = {}
        
        # Get active threads
        active_threads = self.thread_manager.get_active_threads()
        
        # Verify empty list is returned
        self.assertEqual(active_threads, [])
        self.assertEqual(len(active_threads), 0)

    # ============= Thread Cancellation Tests =============

    def test_cancel_all_threads_with_cancel_method(self):
        """Tests cancelling all threads with cancel method."""
        # Create mock threads with cancel method
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread1.cancel = MagicMock()
        thread1.isRunning.return_value = True
        thread1.wait.return_value = True
        
        thread2 = MagicMock()
        thread2.__class__.__name__ = "Thread2"
        thread2.cancel = MagicMock()
        thread2.isRunning.return_value = True
        thread2.wait.return_value = True
        
        # Add threads to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        self.thread_manager._active_threads[id(thread2)] = thread2
        
        # Cancel all threads
        self.thread_manager.cancel_all_threads()
        
        # Verify info log about cancelling threads
        self.mock_logger.info.assert_called_with("Cancelling 2 active threads")
        
        # Verify cancel() is called on each thread
        thread1.cancel.assert_called_once()
        thread2.cancel.assert_called_once()
        
        # Verify debug logs for each cancellation
        self.mock_logger.debug.assert_any_call(
            f"Attempting to cancel thread: Thread1 (id: {id(thread1)})"
        )
        self.mock_logger.debug.assert_any_call(
            f"Called cancel() on thread: Thread1"
        )
        self.mock_logger.debug.assert_any_call(
            f"Attempting to cancel thread: Thread2 (id: {id(thread2)})"
        )
        self.mock_logger.debug.assert_any_call(
            f"Called cancel() on thread: Thread2"
        )
        
        # Verify wait() is called with timeout
        thread1.wait.assert_called_once_with(5000)
        thread2.wait.assert_called_once_with(5000)
        
        # Verify successful completion logs
        self.mock_logger.debug.assert_any_call(
            "Thread Thread1 finished successfully"
        )
        self.mock_logger.debug.assert_any_call(
            "Thread Thread2 finished successfully"
        )

    def test_cancel_all_threads_without_cancel_method(self):
        """Tests handling threads without cancel method."""
        # Create thread without cancel method
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread1.isRunning.return_value = True
        thread1.wait.return_value = True
        # Remove cancel attribute
        del thread1.cancel
        
        # Create thread with non-callable cancel
        thread2 = MagicMock()
        thread2.__class__.__name__ = "Thread2"
        thread2.cancel = "not_callable"
        thread2.isRunning.return_value = True
        thread2.wait.return_value = True
        
        # Add threads to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        self.thread_manager._active_threads[id(thread2)] = thread2
        
        # Cancel all threads
        self.thread_manager.cancel_all_threads()
        
        # Verify warning logs for missing cancel method
        self.mock_logger.warning.assert_any_call(
            "Thread Thread1 has no cancel() method"
        )
        self.mock_logger.warning.assert_any_call(
            "Thread Thread2 has no cancel() method"
        )
        
        # Verify wait() is still called
        thread1.wait.assert_called_once_with(5000)
        thread2.wait.assert_called_once_with(5000)

    def test_cancel_all_threads_exception_handling(self):
        """Tests cancel method exception handling."""
        # Create thread where cancel raises exception
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread1.cancel.side_effect = RuntimeError("Cancel failed")
        thread1.isRunning.return_value = True
        thread1.wait.return_value = True
        
        # Create normal thread
        thread2 = MagicMock()
        thread2.__class__.__name__ = "Thread2"
        thread2.cancel = MagicMock()
        thread2.isRunning.return_value = True
        thread2.wait.return_value = True
        
        # Add threads to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        self.thread_manager._active_threads[id(thread2)] = thread2
        
        # Cancel all threads
        self.thread_manager.cancel_all_threads()
        
        # Verify exception is caught and logged
        self.mock_logger.error.assert_called_with(
            "Error cancelling thread Thread1: Cancel failed"
        )
        
        # Verify processing continues for other threads
        thread2.cancel.assert_called_once()
        
        # Verify wait() is still attempted for both
        thread1.wait.assert_called_once_with(5000)
        thread2.wait.assert_called_once_with(5000)

    def test_cancel_all_threads_timeout(self):
        """Tests thread timeout during cancellation."""
        # Create thread that doesn't finish within timeout
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread1.cancel = MagicMock()
        thread1.isRunning.return_value = True
        thread1.wait.return_value = False  # Timeout
        
        # Add thread to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        
        # Cancel all threads
        self.thread_manager.cancel_all_threads()
        
        # Verify wait() is called with default timeout
        thread1.wait.assert_called_once_with(5000)
        
        # Verify timeout warning log
        self.mock_logger.warning.assert_called_with(
            "Thread Thread1 did not finish within timeout"
        )
        
        # Verify debug log about waiting
        self.mock_logger.debug.assert_any_call(
            "Waiting for thread Thread1 to finish (timeout: 5000ms)"
        )

    def test_cancel_all_threads_custom_timeout(self):
        """Tests custom timeout parameter."""
        # Create running thread
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread1.cancel = MagicMock()
        thread1.isRunning.return_value = True
        thread1.wait.return_value = True
        
        # Add thread to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        
        # Cancel with custom timeout
        self.thread_manager.cancel_all_threads(wait_timeout=10000)
        
        # Verify wait() is called with custom timeout
        thread1.wait.assert_called_once_with(10000)
        
        # Verify debug log shows custom timeout
        self.mock_logger.debug.assert_any_call(
            "Waiting for thread Thread1 to finish (timeout: 10000ms)"
        )

    def test_cancel_all_threads_no_active_threads(self):
        """Tests with no active threads."""
        # Ensure no threads are registered
        self.thread_manager._active_threads = {}
        
        # Cancel all threads
        self.thread_manager.cancel_all_threads()
        
        # Verify debug log message
        self.mock_logger.debug.assert_called_with("No active threads to cancel")
        
        # Verify no other processing occurs
        self.mock_logger.info.assert_not_called()

    def test_cancel_all_threads_not_running(self):
        """Tests with threads that are not running."""
        # Create thread that is not running
        thread1 = MagicMock()
        thread1.__class__.__name__ = "Thread1"
        thread1.cancel = MagicMock()
        thread1.isRunning.return_value = False
        
        # Add thread to registry
        self.thread_manager._active_threads[id(thread1)] = thread1
        
        # Cancel all threads
        self.thread_manager.cancel_all_threads()
        
        # Verify cancel() is still called
        thread1.cancel.assert_called_once()
        
        # Verify wait() is not called since thread is not running
        thread1.wait.assert_not_called()
        
        # Verify no timeout warnings
        self.mock_logger.warning.assert_not_called()

    # ============= Thread Lifecycle Integration Tests =============

    def test_thread_lifecycle_integration(self):
        """Tests complete thread lifecycle from registration to auto-unregistration."""
        # Create mock thread with full signal support
        mock_thread = MagicMock()
        mock_thread.__class__.__name__ = "TestThread"
        mock_thread.finished = MagicMock()
        thread_id = id(mock_thread)
        
        # Mock weakref that properly returns thread
        mock_weak_ref = MagicMock()
        mock_weak_ref.return_value = mock_thread
        
        callback_func = None
        
        # Capture the callback
        def capture_callback(func):
            nonlocal callback_func
            callback_func = func
        
        mock_thread.finished.connect.side_effect = capture_callback
        
        with patch('weakref.ref', return_value=mock_weak_ref):
            # Register thread
            self.thread_manager.register_thread(mock_thread)
        
        # Verify thread is registered successfully
        self.assertIn(thread_id, self.thread_manager._active_threads)
        
        # Verify thread appears in get_active_threads()
        active_threads = self.thread_manager.get_active_threads()
        self.assertIn(mock_thread, active_threads)
        
        # Clear logger for unregistration
        self.mock_logger.reset_mock()
        
        # Simulate finished signal emission
        callback_func()
        
        # Verify thread is removed from active threads
        self.assertNotIn(thread_id, self.thread_manager._active_threads)
        
        # Verify thread no longer appears in get_active_threads()
        active_threads = self.thread_manager.get_active_threads()
        self.assertNotIn(mock_thread, active_threads)

    def test_concurrent_thread_operations(self):
        """Tests thread-safe operations with concurrent registrations."""
        # Create multiple mock threads with unique ids
        threads = []
        for i in range(5):
            thread = MagicMock()
            thread.__class__.__name__ = f"Thread{i}"
            thread.finished = MagicMock()
            threads.append(thread)
        
        # Register all threads
        with patch('weakref.ref'):
            for thread in threads:
                self.thread_manager.register_thread(thread)
        
        # Verify all threads are registered without conflicts
        self.assertEqual(len(self.thread_manager._active_threads), 5)
        
        # Verify each thread has unique id in _active_threads
        thread_ids = list(self.thread_manager._active_threads.keys())
        self.assertEqual(len(thread_ids), len(set(thread_ids)))
        
        # Unregister threads in different order
        for thread in reversed(threads):
            self.thread_manager.unregister_thread(thread)
        
        # Verify all threads are unregistered without errors
        self.assertEqual(len(self.thread_manager._active_threads), 0)
        
        # Verify final state is correct
        active_threads = self.thread_manager.get_active_threads()
        self.assertEqual(len(active_threads), 0)


if __name__ == "__main__":
    unittest.main()