"""
Unit tests for FolderManager singleton pattern and dependency injection.

This test suite verifies the behavior of the refactored FolderManager.instance() method,
specifically focusing on:
- Singleton property (returning the same instance on multiple calls)
- Dependency attachment during initialization
- Error handling for premature calls
- Re-attachment behavior
"""

import unittest
import json
import logging
from unittest.mock import Mock, patch
import threading

from app.FolderManager import FolderManager
from app.DatabaseManager import DatabaseManager


class TestFolderManagerSingleton(unittest.TestCase):
    """Test suite for FolderManager singleton behavior."""

    def setUp(self):
        """Set up the test environment."""
        # Create a mock db_manager for testing
        self.db_manager = Mock(spec=DatabaseManager)
        self.db_manager.execute_query = Mock()

        # Capture log messages
        self.log_capture = []
        self.log_handler = self._create_log_handler()
        self.logger = logging.getLogger("transcribrr")
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.DEBUG)

    def tearDown(self):
        """Clean up test environment."""
        # Reset the singleton state between tests
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Remove the log handler
        if self.log_handler in self.logger.handlers:
            self.logger.removeHandler(self.log_handler)
        self.log_capture.clear()

    def _create_log_handler(self):
        """Create a log handler that captures log messages."""
        log_capture = self.log_capture

        class TestLogHandler(logging.Handler):
            def emit(self, record):
                log_capture.append(record.getMessage())

        return TestLogHandler()

    def test_singleton_property(self):
        """Verify that multiple calls return the same instance."""
        # Get the first instance
        instance1 = FolderManager.instance(db_manager=self.db_manager)

        # Get a second instance
        instance2 = FolderManager.instance()

        # Verify they are the same object
        self.assertIs(
            instance1,
            instance2,
            "Multiple calls to instance() should return the same object",
        )

    def test_successful_first_attachment(self):
        """Test successful dependency attachment on first call."""
        # Get instance with dependency injection
        instance = FolderManager.instance(db_manager=self.db_manager)

        # Verify the db_manager is attached
        self.assertEqual(
            instance.db_manager,
            self.db_manager,
            "db_manager should be attached to the instance",
        )

        # Verify the _db_manager_attached flag is set
        self.assertTrue(
            FolderManager._db_manager_attached,
            "_db_manager_attached flag should be True after attachment",
        )

    def test_successful_subsequent_call(self):
        """Test successful call after attachment."""
        # First call with db_manager
        instance1 = FolderManager.instance(db_manager=self.db_manager)

        # Subsequent call without db_manager
        instance2 = FolderManager.instance()

        # Verify they are the same object
        self.assertIs(
            instance1, instance2, "Subsequent calls should return the same instance"
        )

        # Verify the db_manager is still attached
        self.assertEqual(
            instance2.db_manager, self.db_manager, "db_manager should remain attached"
        )

    def test_failure_before_attachment(self):
        """Test that calling instance() before attachment raises RuntimeError."""
        # Reset singleton state to ensure clean test
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Call instance() without db_manager should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            FolderManager.instance()

        # Verify the error message
        self.assertIn(
            "DatabaseManager",
            str(context.exception),
            "Error message should mention DatabaseManager requirement",
        )

    def test_reattachment_warning(self):
        """Test that attempting to re-attach a different db_manager logs a warning."""
        # First create and attach a db_manager
        instance1 = FolderManager.instance(db_manager=self.db_manager)

        # Create a different mock db_manager
        different_db_manager = Mock(spec=DatabaseManager)
        different_db_manager.execute_query = Mock()

        # Try to attach a different db_manager
        instance2 = FolderManager.instance(db_manager=different_db_manager)

        # Verify it's the same instance
        self.assertIs(
            instance1, instance2, "Should return the same instance regardless"
        )

        # Verify the original db_manager is still attached
        self.assertEqual(
            instance2.db_manager,
            self.db_manager,
            "Original db_manager should remain attached",
        )

        # Verify a warning was logged
        warning_logged = any(
            "Different DatabaseManager" in msg for msg in self.log_capture
        )
        self.assertTrue(
            warning_logged, "A warning should be logged when attempting to re-attach"
        )

    def test_thread_safety(self):
        """Test that the singleton initialization is thread-safe."""
        # Reset singleton state
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Shared results for thread operations
        results = {"instances": []}

        def create_instance():
            instance = FolderManager.instance(db_manager=self.db_manager)
            results["instances"].append(instance)

        # Create multiple threads that will all try to initialize the singleton
        threads = [threading.Thread(target=create_instance) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Check that all threads got the same instance
        first_instance = results["instances"][0]
        for instance in results["instances"][1:]:
            self.assertIs(
                instance, first_instance, "All threads should get the same instance"
            )

    def test_direct_instantiation_prevention(self):
        """Test that direct instantiation after singleton is created raises an error."""
        # First create the singleton instance
        FolderManager.instance(db_manager=self.db_manager)

        # Now try to create a new instance directly
        with self.assertRaises(RuntimeError) as context:
            FolderManager()

        # Verify the error message
        self.assertIn(
            "singleton",
            str(context.exception).lower(),
            "Error message should mention singleton",
        )

    def test_init_database_called_on_attachment(self):
        """Test that init_database is called when db_manager is attached."""
        # Create a subclass with mocked methods for verification
        with patch.object(FolderManager, "init_database") as mock_init_db:
            with patch.object(FolderManager, "load_folders") as mock_load_folders:
                # Initialize with db_manager
                instance = FolderManager.instance(db_manager=self.db_manager)

                # Verify init_database was called
                mock_init_db.assert_called_once()

                # Verify load_folders was called
                mock_load_folders.assert_called_once()


class TestFolderManagerOperations(unittest.TestCase):
    """Extended FolderManager behavior tests following the YAML plan."""

    def setUp(self):
        # Fresh singleton for each test
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

        # Mock db_manager with execute_query stub
        self.db_manager = Mock(spec=DatabaseManager)
        self.exec_calls = []

        def exec_stub(query, params=None, callback=None, **kwargs):
            # Record calls and allow tests to inject results by inspecting query
            self.exec_calls.append((query, params, callback, kwargs))
            # If test preloaded a response on the instance, use it
            if hasattr(self, "_next_result"):
                res = self._next_result
                delattr(self, "_next_result")
                if callback:
                    callback(res)
            elif callback:
                callback([])

        self.db_manager.execute_query = Mock(side_effect=exec_stub)
        self.fm = FolderManager.instance(db_manager=self.db_manager)
        self.fm.folders = []

    def tearDown(self):
        FolderManager._instance = None
        FolderManager._db_manager_attached = False

    def test_load_folders_success_and_structure(self):
        rows = [
            (1, "Root", None, "2024-01-01"),
            (2, "Child", 1, "2024-01-02"),
        ]
        done = {"called": False}

        def cb():
            done["called"] = True

        self._next_result = rows
        self.fm.load_folders(callback=cb)

        self.assertTrue(done["called"])  # callback invoked
        self.assertEqual(len(self.fm.folders), 2)
        parent = self.fm.get_folder_by_id(1)
        child = self.fm.get_folder_by_id(2)
        self.assertEqual(child["parent_id"], 1)
        self.assertIn(child, parent["children"])  # type: ignore[arg-type]

    def test_load_folders_empty(self):
        self._next_result = []
        self.fm.load_folders()
        self.assertEqual(self.fm.folders, [])

    def test_create_folder_success_and_parent_update(self):
        self.fm.folders = [{"id": 10, "name": "P", "parent_id": None, "created_at": "t", "children": []}]
        created = {"ok": None, "id": None}

        def cb(ok, val):
            created["ok"], created["id"] = ok, val

        self._next_result = 123
        result = self.fm.create_folder("New", parent_id=10, callback=cb)
        self.assertTrue(result)
        self.assertTrue(created["ok"])
        self.assertEqual(created["id"], 123)
        nf = self.fm.get_folder_by_id(123)
        self.assertIsNotNone(nf)
        parent = self.fm.get_folder_by_id(10)
        self.assertIn(nf, parent["children"])  # type: ignore[index]

    def test_create_folder_duplicate_name(self):
        self.fm.folders = [{"id": 1, "name": "Dup", "parent_id": None, "created_at": "t", "children": []}]
        called = {"args": None}

        def cb(ok, msg):
            called["args"] = (ok, msg)

        result = self.fm.create_folder("Dup", parent_id=None, callback=cb)
        self.assertFalse(result)
        self.assertEqual(called["args"][0], False)

    def test_create_folder_no_id_returned(self):
        self._next_result = None
        called = {"args": None}

        def cb(ok, msg):
            called["args"] = (ok, msg)

        result = self.fm.create_folder("X", callback=cb)
        self.assertTrue(result)  # async kickoff returns True
        self.assertEqual(called["args"][0], False)

    def test_rename_folder_success(self):
        self.fm.folders = [{"id": 5, "name": "Old", "parent_id": None, "created_at": "t", "children": []}]
        finished = {"ok": None}

        def cb(ok, _):
            finished["ok"] = ok

        self.fm.rename_folder(5, "New", callback=cb)
        self.assertEqual(self.fm.get_folder_by_id(5)["name"], "New")
        self.assertTrue(finished["ok"])

    def test_rename_folder_not_found(self):
        finished = {"ok": None, "msg": None}

        def cb(ok, msg):
            finished["ok"], finished["msg"] = ok, msg

        result = self.fm.rename_folder(999, "New", callback=cb)
        self.assertFalse(result)
        self.assertEqual(finished["ok"], False)
        self.assertIn("not found", finished["msg"])

    def test_rename_folder_duplicate(self):
        self.fm.folders = [
            {"id": 1, "name": "A", "parent_id": None, "created_at": "t", "children": []},
            {"id": 2, "name": "B", "parent_id": None, "created_at": "t", "children": []},
        ]
        finished = {"ok": None}

        def cb(ok, _):
            finished["ok"] = ok

        result = self.fm.rename_folder(2, "A", callback=cb)
        self.assertFalse(result)
        self.assertEqual(finished["ok"], False)

    def test_delete_folder_success(self):
        self.fm.folders = [
            {"id": 10, "name": "P", "parent_id": None, "created_at": "t", "children": []},
            {"id": 11, "name": "C", "parent_id": 10, "created_at": "t", "children": []},
        ]
        deleted = {"ok": None}

        def cb(ok, _):
            deleted["ok"] = ok

        self._next_result = None
        self.fm.delete_folder(11, callback=cb)
        self.assertIsNone(self.fm.get_folder_by_id(11))
        parent = self.fm.get_folder_by_id(10)
        self.assertEqual(parent["children"], [])  # type: ignore[index]
        self.assertTrue(deleted["ok"])

    def test_delete_folder_not_found(self):
        finished = {"ok": None, "msg": None}

        def cb(ok, msg):
            finished["ok"], finished["msg"] = ok, msg

        result = self.fm.delete_folder(999, callback=cb)
        self.assertFalse(result)
        self.assertEqual(finished["ok"], False)

    def test_add_recording_to_folder_new(self):
        calls = {"added": False}

        def cb(ok, _):
            calls["added"] = ok

        self._next_result = []
        self.fm.add_recording_to_folder(77, 5, callback=cb)
        self.assertTrue(calls["added"])  # insert path taken

    def test_add_recording_to_folder_existing(self):
        calls = {"ok": None}

        def cb(ok, _):
            calls["ok"] = ok

        self._next_result = [(1,)]
        self.fm.add_recording_to_folder(77, 5, callback=cb)
        self.assertTrue(calls["ok"])  # early success without insert

    def test_remove_recording_from_folder(self):
        calls = {"ok": None}

        def cb(ok, _):
            calls["ok"] = ok

        self.fm.remove_recording_from_folder(9, 3, callback=cb)
        self.assertTrue(calls["ok"])

    def test_get_recordings_in_folder(self):
        out = {"payload": None}

        def cb(ok, result):
            out["payload"] = (ok, result)

        self._next_result = [(1, "a"), (2, "b")]
        ret = self.fm.get_recordings_in_folder(2, callback=cb)
        self.assertIsNone(ret)
        self.assertEqual(out["payload"], (True, [(1, "a"), (2, "b")]))

    def test_get_folders_for_recording(self):
        out = {"payload": None}

        def cb(ok, result):
            out["payload"] = (ok, result)

        self._next_result = [(5, "F", None, "t")]
        ret = self.fm.get_folders_for_recording(9, callback=cb)
        self.assertEqual(ret, [])  # returns [] immediately
        self.assertEqual(out["payload"], (True, [(5, "F", None, "t")]))

    def test_get_all_root_folders(self):
        self.fm.folders = [
            {"id": 1, "name": "A", "parent_id": None, "created_at": "t", "children": []},
            {"id": 2, "name": "B", "parent_id": 1, "created_at": "t", "children": []},
        ]
        roots = self.fm.get_all_root_folders()
        self.assertEqual([f["id"] for f in roots], [1])

    def test_get_recordings_not_in_folders(self):
        out = {"payload": None}

        def cb(ok, result):
            out["payload"] = (ok, result)

        self._next_result = [(42, "x")]
        ret = self.fm.get_recordings_not_in_folders(callback=cb)
        self.assertIsNone(ret)
        self.assertEqual(out["payload"], (True, [(42, "x")]))

    def test_get_folder_by_id(self):
        self.fm.folders = [{"id": 3, "name": "N", "parent_id": None, "created_at": "t", "children": []}]
        self.assertIsNotNone(self.fm.get_folder_by_id(3))
        self.assertIsNone(self.fm.get_folder_by_id(99))

    def test_get_folder_recording_count(self):
        counts = {"value": None}

        def cb(val):
            counts["value"] = val

        self._next_result = [(5,)]
        ret = self.fm.get_folder_recording_count(7, callback=cb)
        self.assertEqual(ret, 0)  # immediate fallback
        self.assertEqual(counts["value"], 5)

    def test_folder_exists_variants(self):
        self.fm.folders = [
            {"id": 1, "name": "A", "parent_id": None, "created_at": "t", "children": []},
            {"id": 2, "name": "A", "parent_id": 1, "created_at": "t", "children": []},
        ]
        self.assertTrue(self.fm.folder_exists("A", None))
        self.assertTrue(self.fm.folder_exists("A", 1))
        self.assertFalse(self.fm.folder_exists("Z", None))
        self.assertFalse(self.fm.folder_exists("A", None, exclude_id=1))

    def test_export_folder_structure(self):
        self.fm.folders = [{"id": 1, "name": "A", "parent_id": None, "created_at": "t", "children": []}]
        s = self.fm.export_folder_structure()
        self.assertIn("\"name\": \"A\"", s)

    def test_import_folder_structure_success(self):
        data = [{"id": 1, "name": "A", "parent_id": None, "created_at": "t"}]
        payload = {"ok": None, "msg": None}

        # Inject a fake PyQt6.QtCore.QTimer into sys.modules so the import works
        import types, sys as _sys
        fake_core = types.ModuleType("PyQt6.QtCore")

        class _FakeTimer:
            @staticmethod
            def singleShot(_ms, cb):
                cb()

        fake_core.QTimer = _FakeTimer
        _sys.modules["PyQt6"] = types.ModuleType("PyQt6")
        _sys.modules["PyQt6.QtCore"] = fake_core

        try:
            self.fm.import_folder_structure(json.dumps(data), callback=lambda ok, msg: payload.update({"ok": ok, "msg": msg}))
        finally:
            # Cleanup injected modules to avoid side effects
            _sys.modules.pop("PyQt6", None)
            _sys.modules.pop("PyQt6.QtCore", None)

        self.assertTrue(payload["ok"])
        self.assertIn("success", payload["msg"].lower())

    def test_import_folder_structure_invalid_json(self):
        payload = {"ok": None, "msg": None}
        out = self.fm.import_folder_structure("{ not json }", callback=lambda ok, msg: payload.update({"ok": ok, "msg": msg}))
        self.assertFalse(out)
        self.assertEqual(payload["ok"], False)

    def test_import_folder_structure_db_error(self):
        self.db_manager.execute_query.side_effect = Exception("DB boom")
        payload = {"ok": None, "msg": None}
        out = self.fm.import_folder_structure("[]", callback=lambda ok, msg: payload.update({"ok": ok, "msg": msg}))
        self.assertFalse(out)
        self.assertEqual(payload["ok"], False)


if __name__ == "__main__":
    unittest.main()
