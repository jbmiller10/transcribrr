"""
Behavior-first tests for DatabaseManager using a real SQLite database file.

No heavy mocking: use a temp user-data directory to isolate the DB, rely on
DatabaseManager APIs and verify outcomes through callbacks or direct queries.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock

from app.DatabaseManager import DatabaseManager
from app.constants import get_database_path
import app.constants as _const


try:
    # Allow override via environment, default to a tighter 0.3s to keep failures fast
    DEFAULT_TIMEOUT = float(os.getenv("TEST_TIMEOUT", "0.3"))
except Exception:
    DEFAULT_TIMEOUT = 0.3


class _Wait:
    """Tiny helper to wait for async callbacks from the worker.

    Avoids fixed 1s timeouts by honoring TEST_TIMEOUT env and using Events.
    """

    def __init__(self) -> None:
        self.evt = threading.Event()
        self.payload = None

    def cb(self, *args):  # noqa: ANN001
        self.payload = args[0] if len(args) == 1 else args
        self.evt.set()

    def wait(self, timeout: float | None = None) -> bool:
        return self.evt.wait(DEFAULT_TIMEOUT if timeout is None else timeout)


class _DatabaseTestBase(unittest.TestCase):
    """Base class for database tests with common setup/teardown."""
    
    def _setup_test_environment(self, prefix: str = "transcribrr_mgr_") -> None:
        """Set up isolated test environment with temp directory and env vars."""
        self.tmp = tempfile.mkdtemp(prefix=prefix)
        self.prev = os.environ.get("TRANSCRIBRR_USER_DATA_DIR")
        os.environ["TRANSCRIBRR_USER_DATA_DIR"] = self.tmp
        # Force Qt stubs to ensure signal delivery without an event loop
        self.prev_use_stubs = os.environ.get("TRANSCRIBRR_USE_QT_STUBS")
        os.environ["TRANSCRIBRR_USE_QT_STUBS"] = "1"
        # Reset cached user data dir to honor env override
        self.prev_cache = getattr(_const, "_USER_DATA_DIR_CACHE", None)
        _const._USER_DATA_DIR_CACHE = None
    
    def _teardown_test_environment(self) -> None:
        """Clean up test environment."""
        if self.prev is None:
            os.environ.pop("TRANSCRIBRR_USER_DATA_DIR", None)
        else:
            os.environ["TRANSCRIBRR_USER_DATA_DIR"] = self.prev
        # Restore stub forcing variable
        if self.prev_use_stubs is None:
            os.environ.pop("TRANSCRIBRR_USE_QT_STUBS", None)
        else:
            os.environ["TRANSCRIBRR_USE_QT_STUBS"] = self.prev_use_stubs
        _const._USER_DATA_DIR_CACHE = self.prev_cache
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestDatabaseManagerBehavior(_DatabaseTestBase):
    def setUp(self) -> None:
        self._setup_test_environment()
        self.mgr = DatabaseManager(parent=None)

    def tearDown(self) -> None:
        try:
            # Stop worker thread
            self.mgr.shutdown()
        finally:
            self._teardown_test_environment()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(get_database_path())
        c.execute("PRAGMA foreign_keys = ON")
        return c

    # Helpers
    def _generate_recording_data(self, index: int, with_transcript: bool = False):
        filename = f"file_{index:03d}.wav"
        filepath = f"{self.tmp}/{filename}"
        timestamp = "2024-06-15 14:30:45"
        duration = "1m30s"
        base = (filename, filepath, timestamp, duration)
        if with_transcript:
            return base + (f"hello #{index}",)
        return base

    def test_create_recording_persists_to_database_and_appears_in_listing(self):
        """Creates two records and lists them via manager API."""
        w1, w2 = _Wait(), _Wait()
        self.mgr.create_recording(("a.wav", f"{self.tmp}/a.wav", "2024-01-01 00:00:00", "1s"), w1.cb)
        self.mgr.create_recording(("b.wav", f"{self.tmp}/b.wav", "2024-01-01 00:00:00", "2s"), w2.cb)
        self.assertTrue(w1.wait(), "create #1 callback not called within 0.5s")
        self.assertTrue(w2.wait(), "create #2 callback not called within 0.5s")

        # Now list
        wlist = _Wait()
        self.mgr.get_all_recordings(wlist.cb)
        self.assertTrue(wlist.wait(), "get_all callback not called within 0.5s")
        rows = wlist.payload
        self.assertIsInstance(rows, list)
        # Fresh DB should only contain these two
        self.assertEqual(len(rows), 2, f"Expected 2 rows, got {len(rows)}: {rows}")

    def test_update_recording_modifies_fields_retrievable_by_id(self):
        """Updates a field and retrieves by id as Recording object."""
        win = _Wait()
        self.mgr.create_recording(("c.wav", f"{self.tmp}/c.wav", "2024-01-01 00:00:00", "1s"), win.cb)
        self.assertTrue(win.wait(), "create callback not received in 0.5s")
        rec_id = win.payload

        wupd = _Wait()
        self.mgr.update_recording(rec_id, wupd.cb, raw_transcript="hello")
        self.assertTrue(wupd.wait(), "update callback not received in 0.5s")

        wget = _Wait()
        self.mgr.get_recording_by_id(rec_id, wget.cb)
        self.assertTrue(wget.wait(), "get_by_id callback not received in 0.5s")
        rec = wget.payload
        # get_recording_by_id returns Recording dataclass or None
        self.assertIsNotNone(rec)
        self.assertEqual(getattr(rec, "raw_transcript", None), "hello")

    def test_delete_recording_removes_from_database_permanently(self):
        win = _Wait()
        self.mgr.create_recording(("d.wav", f"{self.tmp}/d.wav", "2024-01-01 00:00:00", "1s"), win.cb)
        self.assertTrue(win.wait(), "create callback not received in 0.5s")
        rec_id = win.payload

        wdel = _Wait()
        self.mgr.delete_recording(rec_id, wdel.cb)
        self.assertTrue(wdel.wait(), "delete callback not received in 0.5s")

        # Verify gone via direct SQL
        with self._conn() as c:
            cnt = c.execute("SELECT COUNT(*) FROM recordings WHERE id=?", (rec_id,)).fetchone()[0]
        self.assertEqual(cnt, 0)

    def test_search_recordings_returns_matching_transcripts(self):
        # Seed two records; one with a keyword
        w1, w2 = _Wait(), _Wait()
        self.mgr.create_recording(("e.wav", f"{self.tmp}/e.wav", "2024-01-01 00:00:00", "1s", "hello world"), w1.cb)
        self.mgr.create_recording(("f.wav", f"{self.tmp}/f.wav", "2024-01-01 00:00:00", "1s", "other"), w2.cb)
        self.assertTrue(w1.wait(), "create #1 callback not received in 0.5s")
        self.assertTrue(w2.wait(), "create #2 callback not received in 0.5s")

        wsearch = _Wait()
        self.mgr.search_recordings("hello", wsearch.cb)
        self.assertTrue(wsearch.wait(), "search callback not received in 0.5s")
        rows = wsearch.payload
        # Expect at least one match containing the first file
        filenames = [r[1] for r in rows]
        self.assertIn("e.wav", filenames)

    def test_create_recording_with_duplicate_path_raises_error(self):
        """Second insert with same file_path should not create a new row and emits error."""
        w1, w2 = _Wait(), _Wait()
        data = ("dup.wav", f"{self.tmp}/dup.wav", "2024-01-01 00:00:00", "1s")

        # Capture error signal
        err_evt = _Wait()
        self.mgr.worker.error_occurred.connect(lambda etype, msg: err_evt.cb(etype, msg))

        self.mgr.create_recording(data, w1.cb)
        self.assertTrue(w1.wait(), "initial create did not callback")

        # Second with same path
        # Second with same path triggers error signal; callback may not be invoked on error
        self.mgr.create_recording(data, w2.cb)
        self.assertTrue(err_evt.wait(), "expected error signal on duplicate path")
        etype, _msg = err_evt.payload if isinstance(err_evt.payload, tuple) else (err_evt.payload, None)
        self.assertIn(etype, {"Duplicate path", "Duplicate path error"})

        # Verify only one row exists
        with self._conn() as c:
            cnt = c.execute("SELECT COUNT(*) FROM recordings WHERE file_path=?", (data[1],)).fetchone()[0]
        self.assertEqual(cnt, 1, f"Duplicate insert created extra row for path {data[1]}")

    def test_create_recording_with_invalid_data_formats(self):
        """Invalid tuples are rejected and do not crash worker."""
        bad = ("x.wav", f"{self.tmp}/x.wav")  # missing fields
        # Hook error signal to ensure it's emitted
        err_evt = _Wait()
        self.mgr.worker.error_occurred.connect(lambda etype, msg: err_evt.cb(etype, msg))
        self.mgr.create_recording(bad, None)
        self.assertTrue(err_evt.wait(), "no error signal for invalid data")
        etype, _msg = err_evt.payload if isinstance(err_evt.payload, tuple) else (err_evt.payload, None)
        # db_utils raises ValueError, worker wraps as RuntimeError -> 'Runtime error'
        self.assertEqual(etype, "Runtime error")

    def test_dataChanged_emitted_on_create_recording(self):
        """Creating a recording emits DatabaseManager.dataChanged for UI refresh."""
        # Arrange: subscribe to manager-level dataChanged
        chg = _Wait()
        self.mgr.dataChanged.connect(lambda t, i: chg.cb((t, i)))

        # Act: create a new recording
        win = _Wait()
        data = ("z.wav", f"{self.tmp}/z.wav", "2024-01-01 00:00:00", "1s")
        self.mgr.create_recording(data, win.cb)
        self.assertTrue(win.wait(1.0), "create callback not received in time")

        # Assert: dataChanged fired with expected payload
        self.assertTrue(chg.wait(1.0), "dataChanged not emitted in time")
        payload = chg.payload
        self.assertIsInstance(payload, tuple)
        self.assertEqual(payload[0], "recording")
        # -1 indicates 'refresh all' semantics for the UI model
        self.assertEqual(payload[1], -1)

    def test_create_recording_with_none_in_required_field_emits_error(self):
        data = (None, f"{self.tmp}/z.wav", "2024-01-01 00:00:00", "1s")
        err_evt = _Wait()
        self.mgr.worker.error_occurred.connect(lambda etype, msg: err_evt.cb(etype, msg))
        self.mgr.create_recording(data, None)
        self.assertTrue(err_evt.wait(), "expected error on NOT NULL violation")
        etype, _msg = err_evt.payload if isinstance(err_evt.payload, tuple) else (err_evt.payload, None)
        self.assertEqual(etype, "Runtime error")

    def test_update_nonexistent_recording_handles_gracefully(self):
        """Updating a non-existent id should not crash and completes callback."""
        wupd = _Wait()
        self.mgr.update_recording(999999, wupd.cb, raw_transcript="noop")
        self.assertTrue(wupd.wait(), "update on missing id did not callback")

        # Verify actually nothing exists with that id
        with self._conn() as c:
            cnt = c.execute("SELECT COUNT(*) FROM recordings WHERE id=?", (999999,)).fetchone()[0]
        self.assertEqual(cnt, 0)

    def test_delete_nonexistent_recording_handles_gracefully(self):
        wdel = _Wait()
        self.mgr.delete_recording(424242, wdel.cb)
        self.assertTrue(wdel.wait(), "delete on missing id did not callback")

    def test_search_recordings_with_empty_term_returns_all(self):
        # Seed a few
        ws = [_Wait() for _ in range(3)]
        for i, w in enumerate(ws):
            self.mgr.create_recording(self._generate_recording_data(i, with_transcript=True), w.cb)
        for w in ws:
            self.assertTrue(w.wait(), "seed create did not callback")

        wsearch = _Wait()
        self.mgr.search_recordings("", wsearch.cb)
        self.assertTrue(wsearch.wait(), "empty search did not callback")
        rows = wsearch.payload
        self.assertGreaterEqual(len(rows), 3)

    def test_unicode_characters_in_filenames_and_transcripts(self):
        entries = [
            ("hello_世界.wav", f"{self.tmp}/h1.wav", "2024-01-01 00:00:00", "1s", "Hello 世界"),
            ("مرحبا.wav", f"{self.tmp}/h2.wav", "2024-01-01 00:00:00", "1s", "مرحبا بالعالم"),
            ("music.wav", f"{self.tmp}/h3.wav", "2024-01-01 00:00:00", "1s", "🎵 Music 🎶"),
        ]
        waits = [_Wait() for _ in entries]
        for data, w in zip(entries, waits):
            self.mgr.create_recording(data, w.cb)
        for w in waits:
            self.assertTrue(w.wait(), "unicode create did not callback in 0.5s")

        for term in ["世界", "مرحبا", "Music", "🎶"]:
            wsearch = _Wait()
            self.mgr.search_recordings(term, wsearch.cb)
            self.assertTrue(wsearch.wait(), f"search for {term!r} timed out")
            self.assertGreaterEqual(len(wsearch.payload), 1, f"Expected results for {term!r}")

    def test_create_recording_with_sql_injection_literal(self):
        w = _Wait()
        malicious = "'; DROP TABLE recordings; --"
        self.mgr.create_recording(
            (malicious, f"{self.tmp}/inj.wav", "2024-01-01 00:00:00", "1s"), w.cb
        )
        self.assertTrue(w.wait())

        # Verify stored literally via listing
        wl = _Wait()
        self.mgr.get_all_recordings(wl.cb)
        self.assertTrue(wl.wait())
        names = [r[1] for r in wl.payload]
        self.assertIn(malicious, names)

    def test_update_with_invalid_fields_still_callbacks(self):
        w = _Wait()
        self.mgr.create_recording(("iv.wav", f"{self.tmp}/iv.wav", "2024-01-01 00:00:00", "1s"), w.cb)
        self.assertTrue(w.wait())
        rid = w.payload

        wupd = _Wait()
        # invalid field should be ignored; callback still fires
        self.mgr.update_recording(rid, wupd.cb, not_a_field="x")  # type: ignore[arg-type]
        self.assertTrue(wupd.wait())


class TestDatabaseManagerInitFailure(_DatabaseTestBase):
    def setUp(self) -> None:
        self._setup_test_environment(prefix="transcribrr_mgr_fail_")

    def tearDown(self) -> None:
        self._teardown_test_environment()

    def test_init_connection_failure_raises_runtimeerror(self):
        # Simulate sqlite connection failure deep in db_utils.get_connection
        with mock.patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
            with self.assertRaises(RuntimeError):
                DatabaseManager(parent=None)
