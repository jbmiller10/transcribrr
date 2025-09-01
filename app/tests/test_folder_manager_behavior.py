"""
Behavior-first tests for FolderManager using a real SQLite database.

These tests avoid heavy mocking by running against a temp user data dir,
initializing a real DatabaseManager and exercising FolderManager's public API.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
import unittest

from app.DatabaseManager import DatabaseManager
from app.FolderManager import FolderManager
from app.constants import get_database_path
import app.constants as _const


class _Wait:
    def __init__(self) -> None:
        self.evt = threading.Event()
        self.args = None

    def cb(self, *args):  # noqa: ANN001
        self.args = args
        self.evt.set()

    def wait(self, timeout: float | None = None) -> bool:
        if timeout is None:
            try:
                timeout = float(os.getenv("TEST_TIMEOUT", "3.0"))
            except Exception:
                timeout = 3.0
        return self.evt.wait(timeout)


class TestFolderManagerBehavior(unittest.TestCase):
    def setUp(self) -> None:
        # Isolate a temp user-data dir and reset cached path
        self.tmp = tempfile.mkdtemp(prefix="transcribrr_fm_")
        self.prev_env = os.environ.get("TRANSCRIBRR_USER_DATA_DIR")
        os.environ["TRANSCRIBRR_USER_DATA_DIR"] = self.tmp
        self.prev_cache = getattr(_const, "_USER_DATA_DIR_CACHE", None)
        _const._USER_DATA_DIR_CACHE = None

        # Reset FolderManager singleton via public test helper
        FolderManager.reset_for_tests()

        # Real DB manager and folder manager
        self.dbm = DatabaseManager(parent=None)
        self.fm = FolderManager.instance(db_manager=self.dbm)

    def tearDown(self) -> None:
        try:
            self.dbm.shutdown()
        finally:
            FolderManager.reset_for_tests()
            if self.prev_env is None:
                os.environ.pop("TRANSCRIBRR_USER_DATA_DIR", None)
            else:
                os.environ["TRANSCRIBRR_USER_DATA_DIR"] = self.prev_env
            _const._USER_DATA_DIR_CACHE = self.prev_cache
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(get_database_path())
        c.execute("PRAGMA foreign_keys = ON")
        return c
    
    def _create_folder_sync(self, name: str, parent_id: int | None = None) -> tuple[bool, int | None]:
        """Helper to create a folder synchronously and return (success, folder_id)."""
        w = _Wait()
        success = self.fm.create_folder(name, parent_id=parent_id, callback=w.cb)
        if not success:
            return False, None
        self.assertTrue(w.wait(), f"create folder '{name}' callback not called")
        return w.args[0], w.args[1] if len(w.args) > 1 else None
    
    def _create_recording_sync(self, filename: str) -> int:
        """Helper to create a recording synchronously and return recording_id."""
        w = _Wait()
        rec_tuple = (filename, f"{self.tmp}/{filename}", "2024-01-01 00:00:00", "1s")
        self.dbm.create_recording(rec_tuple, w.cb)
        self.assertTrue(w.wait(), f"create recording '{filename}' callback not called")
        return w.args[0]
    
    def _add_recording_to_folder_sync(self, recording_id: int, folder_id: int) -> bool:
        """Helper to add a recording to a folder synchronously."""
        w = _Wait()
        self.fm.add_recording_to_folder(recording_id, folder_id, callback=lambda ok, _m: w.cb(ok))
        self.assertTrue(w.wait(), "add recording to folder callback not called")
        return w.args[0]

    def test_should_create_hierarchical_folder_structure_with_parent_child_relationship(self):
        # Use helper methods to reduce setup duplication
        success, root_id = self._create_folder_sync("Root", parent_id=None)
        self.assertTrue(success)
        self.assertIsNotNone(root_id)
        
        success, child_id = self._create_folder_sync("Child", parent_id=root_id)
        self.assertTrue(success)
        self.assertIsNotNone(child_id)

        # Check DB content
        with self._conn() as c:
            rows = c.execute("SELECT id, name, parent_id FROM folders ORDER BY id").fetchall()
        self.assertEqual(rows, [(root_id, "Root", None), (child_id, "Child", root_id)])

        # Check in-memory structure
        parent = self.fm.get_folder_by_id(root_id)
        child = self.fm.get_folder_by_id(child_id)
        self.assertIsNotNone(parent)
        self.assertIsNotNone(child)
        self.assertIn(child, parent["children"])  # type: ignore[index]

    def test_should_persist_folder_rename_to_database_and_update_memory_cache(self):
        success, fid = self._create_folder_sync("Old")
        self.assertTrue(success)
        self.assertIsNotNone(fid)

        done = _Wait()
        def on_rename_complete(success: bool, msg: str) -> None:  # noqa: ANN001
            done.cb(success, msg)
        self.assertTrue(
            self.fm.rename_folder(fid, "New", callback=on_rename_complete)
        )
        self.assertTrue(done.wait(), "rename callback not called")
        self.assertTrue(done.args[0], f"Rename failed: {done.args[1]}")

        with self._conn() as c:
            name = c.execute("SELECT name FROM folders WHERE id=?", (fid,)).fetchone()[0]
        self.assertEqual(name, "New")

    def test_should_associate_recording_with_folder_and_retrieve_via_query(self):
        # Use helper methods to reduce setup duplication
        success, fid = self._create_folder_sync("R")
        self.assertTrue(success)
        self.assertIsNotNone(fid)
        
        rid = self._create_recording_sync("a.wav")
        self.assertIsNotNone(rid)
        
        # Add association
        success = self._add_recording_to_folder_sync(rid, fid)
        self.assertTrue(success)

        # Query via FolderManager API
        wq = _Wait()
        self.fm.get_recordings_in_folder(fid, callback=lambda ok, res: (wq.cb(ok, res)))
        self.assertTrue(wq.wait())
        self.assertTrue(wq.args[0])
        # Ensure the tuple (id, filename) appears
        filenames = [row[1] for row in wq.args[1]]
        self.assertIn("a.wav", filenames)

    def test_should_delete_folder_from_database_and_memory_when_requested(self):
        success, fid = self._create_folder_sync("DelMe")
        self.assertTrue(success)
        self.assertIsNotNone(fid)

        wd = _Wait()
        self.fm.delete_folder(fid, callback=lambda ok, _msg: wd.cb(ok))
        self.assertTrue(wd.wait())
        self.assertTrue(wd.args[0])

        with self._conn() as c:
            cnt = c.execute("SELECT COUNT(*) FROM folders WHERE id=?", (fid,)).fetchone()[0]
        self.assertEqual(cnt, 0)

    def test_should_reject_duplicate_folder_name_at_same_hierarchy_level(self):
        # First folder creation should succeed
        success, fid = self._create_folder_sync("Dup")
        self.assertTrue(success)
        self.assertIsNotNone(fid)
        
        # Attempt duplicate name at same level - should fail immediately
        dup = _Wait()
        ok = self.fm.create_folder("Dup", callback=lambda ok, _msg: dup.cb(ok))
        self.assertFalse(ok)  # immediate False
        self.assertTrue(dup.wait())
        self.assertFalse(dup.args[0])

    def test_should_reject_rename_when_target_name_exists_at_same_level(self):
        # Create two siblings using helper methods
        success_a, aid = self._create_folder_sync("A")
        self.assertTrue(success_a)
        self.assertIsNotNone(aid)
        
        success_b, bid = self._create_folder_sync("B")
        self.assertTrue(success_b)
        self.assertIsNotNone(bid)
        done = _Wait()
        ok = self.fm.rename_folder(bid, "A", callback=lambda ok, _m: done.cb(ok))
        self.assertFalse(ok)
        self.assertTrue(done.wait(), "rename callback not called")
        self.assertFalse(done.args[0])

    def test_should_cascade_delete_child_folders_when_parent_deleted(self):
        # Create parent and child using helper methods
        success_p, pid = self._create_folder_sync("P")
        self.assertTrue(success_p)
        self.assertIsNotNone(pid)
        
        success_c, cid = self._create_folder_sync("C", parent_id=pid)
        self.assertTrue(success_c)
        self.assertIsNotNone(cid)

        d = _Wait()
        self.fm.delete_folder(pid, callback=lambda ok, _m: d.cb(ok))
        self.assertTrue(d.wait(), "delete callback not called")
        self.assertTrue(d.args[0])

        # After DB cascade, reload folders to refresh in-memory state
        loaded = _Wait()
        self.fm.load_folders(callback=lambda: loaded.cb(True))
        self.assertTrue(loaded.wait(), "reload callback not called")

        with self._conn() as cdb:
            cnt = cdb.execute("SELECT COUNT(*) FROM folders").fetchone()[0]
            self.assertEqual(cnt, 0)
        self.assertIsNone(self.fm.get_folder_by_id(pid))
        self.assertIsNone(self.fm.get_folder_by_id(cid))

    def test_should_disassociate_recording_from_folder_on_removal(self):
        # Use helper methods to set up folder, recording and association
        success, fid = self._create_folder_sync("F")
        self.assertTrue(success)
        self.assertIsNotNone(fid)
        
        rid = self._create_recording_sync("g.wav")
        self.assertIsNotNone(rid)
        
        success = self._add_recording_to_folder_sync(rid, fid)
        self.assertTrue(success)

        rm = _Wait()
        self.fm.remove_recording_from_folder(rid, fid, callback=lambda ok, _m: rm.cb(ok))
        self.assertTrue(rm.wait(), "remove association callback not called")
        self.assertTrue(rm.args[0])

        # Now folder should not list the recording
        wq = _Wait()
        self.fm.get_recordings_in_folder(fid, callback=lambda ok, res: wq.cb(ok, res))
        self.assertTrue(wq.wait(), "query callback not called")
        self.assertTrue(wq.args[0])
        ids = [row[0] for row in wq.args[1]]
        self.assertNotIn(rid, ids)

    def test_should_return_all_folders_containing_specific_recording(self):
        # Use helper methods for cleaner setup
        success, fid = self._create_folder_sync("F")
        self.assertTrue(success)
        self.assertIsNotNone(fid)
        
        rid = self._create_recording_sync("h.wav")
        self.assertIsNotNone(rid)
        
        success = self._add_recording_to_folder_sync(rid, fid)
        self.assertTrue(success)

        wq = _Wait()
        self.fm.get_folders_for_recording(rid, callback=lambda ok, res: wq.cb(ok, res))
        self.assertTrue(wq.wait())
        self.assertTrue(wq.args[0])
        fids = [row[0] for row in wq.args[1]]
        self.assertIn(fid, fids)

    def test_should_preserve_folder_structure_through_export_import_cycle(self):
        # Create a small structure using helper methods
        success_p, pid = self._create_folder_sync("P")
        self.assertTrue(success_p)
        self.assertIsNotNone(pid)
        
        success_c, cid = self._create_folder_sync("C", parent_id=pid)
        self.assertTrue(success_c)
        self.assertIsNotNone(cid)
        s = self.fm.export_folder_structure()

        # Clear via import empty first
        payload = _Wait()
        self.fm.import_folder_structure("[]", callback=lambda ok, msg: payload.cb(ok, msg))
        self.assertTrue(payload.wait(), "import empty callback not called")
        self.assertTrue(payload.args[0])

        # Import saved structure
        imp = _Wait()
        self.fm.import_folder_structure(s, callback=lambda ok, msg: imp.cb(ok, msg))
        self.assertTrue(imp.wait(), "import saved callback not called")
        self.assertTrue(imp.args[0])

        # Reload and ensure both folders exist
        loaded = _Wait()
        self.fm.load_folders(callback=lambda: loaded.cb(True))
        self.assertTrue(loaded.wait(), "reload callback not called")
        self.assertIsNotNone(self.fm.get_folder_by_id(pid))
        self.assertIsNotNone(self.fm.get_folder_by_id(cid))


class TestFolderManagerSingletonAndEdgeCases(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="transcribrr_fm_singleton_")
        self.prev_env = os.environ.get("TRANSCRIBRR_USER_DATA_DIR")
        os.environ["TRANSCRIBRR_USER_DATA_DIR"] = self.tmp
        self.prev_cache = getattr(_const, "_USER_DATA_DIR_CACHE", None)
        _const._USER_DATA_DIR_CACHE = None
        # Reset singleton
        FolderManager._instance = None
        FolderManager._db_manager_attached = False
        # Track created DatabaseManagers for cleanup
        self.db_managers = []

    def tearDown(self) -> None:
        try:
            inst = getattr(FolderManager, '_instance', None)
            if inst and getattr(inst, 'db_manager', None):
                inst.db_manager.shutdown()
        finally:
            # Shutdown all tracked DatabaseManagers
            for dbm in self.db_managers:
                try:
                    dbm.shutdown()
                except Exception:
                    pass
            FolderManager.reset_for_tests()
            if self.prev_env is None:
                os.environ.pop("TRANSCRIBRR_USER_DATA_DIR", None)
            else:
                os.environ["TRANSCRIBRR_USER_DATA_DIR"] = self.prev_env
            _const._USER_DATA_DIR_CACHE = self.prev_cache
            shutil.rmtree(self.tmp, ignore_errors=True)
    
    def _create_db_manager(self) -> DatabaseManager:
        """Helper to create and track a DatabaseManager for proper cleanup."""
        dbm = DatabaseManager(parent=None)
        self.db_managers.append(dbm)
        return dbm

    def test_instance_without_db_manager_raises(self):
        with self.assertRaises(RuntimeError):
            FolderManager.instance()

    def test_instance_returns_same_and_warns_on_different_manager(self):
        a = self._create_db_manager()
        fm1 = FolderManager.instance(db_manager=a)
        with self.assertLogs('transcribrr', level='WARNING') as cm:
            b = self._create_db_manager()
            fm2 = FolderManager.instance(db_manager=b)
        self.assertIs(fm1, fm2)
        self.assertTrue(any('Different DatabaseManager instance provided' in msg for msg in cm.output))

    def test_get_recordings_not_in_folders_without_callback_warns(self):
        a = self._create_db_manager()
        fm = FolderManager.instance(db_manager=a)
        # Force synchronous execution of the callback to capture logs deterministically
        orig = fm.db_manager.execute_query
        def fake_exec(query, params=None, callback=None, **kwargs):  # noqa: ANN001
            if callback:
                callback([])
        fm.db_manager.execute_query = fake_exec  # type: ignore[assignment]
        with self.assertLogs('transcribrr', level='WARNING') as cm:
            fm.get_recordings_not_in_folders(None)  # type: ignore[arg-type]
        fm.db_manager.execute_query = orig
        self.assertTrue(any('without a callback' in msg for msg in cm.output))

    def test_rename_nonexistent_folder_returns_false(self):
        a = self._create_db_manager()
        fm = FolderManager.instance(db_manager=a)
        done = _Wait()
        ok = fm.rename_folder(9999, 'X', callback=lambda ok, _m: done.cb(ok))
        self.assertFalse(ok)
        self.assertTrue(done.wait())
        self.assertFalse(done.args[0])

    def test_delete_nonexistent_folder_returns_false(self):
        a = self._create_db_manager()
        fm = FolderManager.instance(db_manager=a)
        done = _Wait()
        ok = fm.delete_folder(9999, callback=lambda ok, _m: done.cb(ok))
        self.assertFalse(ok)
        self.assertTrue(done.wait())
        self.assertFalse(done.args[0])

    def test_create_folder_error_when_no_id(self):
        a = self._create_db_manager()
        fm = FolderManager.instance(db_manager=a)
        # Monkeypatch execute_query to immediately call callback with None
        orig = fm.db_manager.execute_query
        def fake_exec(query, params=None, callback=None, **kwargs):  # noqa: ANN001
            if callback:
                callback(None)
        fm.db_manager.execute_query = fake_exec  # type: ignore[assignment]
        done = _Wait()
        fm.create_folder('Z', callback=lambda ok, msg: done.cb(ok, msg))
        self.assertTrue(done.wait())
        self.assertFalse(done.args[0])
        fm.db_manager.execute_query = orig  # restore
