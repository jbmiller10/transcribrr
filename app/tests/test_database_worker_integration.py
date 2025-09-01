"""
Integration-style tests for DatabaseWorker using a real SQLite database.

These tests follow the plan to reduce excessive mocking by exercising
actual SQL behavior in an in-memory database. We replace only the
signal endpoints with light capture helpers to assert observable
outcomes.
"""

from __future__ import annotations

import sqlite3
import unittest
from typing import Any

from app.DatabaseManager import DatabaseWorker
from app.db_utils import (
    create_recordings_table,
    create_recording as db_create_recording,
)


def create_test_database() -> sqlite3.Connection:
    """Create a fresh in-memory SQLite DB with required tables."""
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_recordings_table(conn)
    return conn


class _Capture:
    """Simple capture helper mimicking a Qt signal endpoint with emit()."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def emit(self, *args: Any) -> None:
        self.calls.append(tuple(args))


class TestDatabaseWorkerWithRealSQLite(unittest.TestCase):
    """Behavior-focused tests using a real DB connection."""

    def setUp(self) -> None:
        # Real in-memory database
        self.conn = create_test_database()

        # Prepare signal adapters (capture objects) and inject at construction
        self.op_complete = _Capture()
        self.data_changed = _Capture()
        self.err_capture = _Capture()
        try:
            import types as _types
            _signals = _types.SimpleNamespace(
                operation_complete=self.op_complete,
                dataChanged=self.data_changed,
                error_occurred=self.err_capture,
            )
            self.worker = DatabaseWorker(parent=None, signals=_signals)
        except TypeError:
            # Backward-compat if constructor doesn't yet accept signals
            self.worker = DatabaseWorker(parent=None)
            self.worker.operation_complete = self.op_complete
            self.worker.dataChanged = self.data_changed
            self.worker.error_occurred = self.err_capture

        # Swap in our connection
        self.worker.conn = self.conn

    def tearDown(self) -> None:
        # Ensure connection closed if still open
        try:
            self.conn.close()
        except Exception:
            pass

    def _run_single(self) -> None:
        """Run worker until it processes the queued op and sentinel."""
        # Push sentinel to ensure the loop terminates after the operation
        self.worker.operations_queue.put(None)
        self.worker.run()
    
    def _create_test_recording(self, filename: str = "test.wav", path: str = "/tmp/test.wav", 
                               date: str = "2024-01-01 00:00:00", duration: str = "1s") -> int:
        """Helper to create a test recording with default values."""
        return db_create_recording(self.conn, (filename, path, date, duration))
    
    def _setup_completion_capture(self, callback):
        """Helper to setup operation completion callback."""
        self.worker.operation_complete.emit = callback  # type: ignore[attr-defined]
    
    def _assert_signal_emitted(self, signal_capture: _Capture, min_calls: int = 1, 
                              message: str = "Signal should have been emitted"):
        """Helper to assert a signal was emitted at least min_calls times."""
        self.assertGreaterEqual(len(signal_capture.calls), min_calls, message)
    
    def _assert_no_signal(self, signal_capture: _Capture, message: str = "Signal should not have been emitted"):
        """Helper to assert a signal was not emitted."""
        self.assertEqual(len(signal_capture.calls), 0, message)

    def test_create_recording_persists_data(self):
        """Recording is inserted and can be queried with expected fields."""
        payload = ("a.wav", "/tmp/a.wav", "2024-01-01 00:00:00", "00:00:10")

        # Enqueue create operation
        self.worker.add_operation("create_recording", "op1", [payload])

        # During operation_complete, verify row is present
        seen: dict[str, Any] = {}

        def capture_and_query(op_id, result):  # noqa: ANN001
            seen["op_id"] = op_id
            seen["new_id"] = result
            cur = self.conn.execute(
                "SELECT filename, file_path FROM recordings WHERE id=?", (result,)
            )
            seen["row"] = cur.fetchone()

        self.worker.operation_complete.emit = capture_and_query  # type: ignore[attr-defined]

        self._run_single()

        self.assertEqual(seen.get("op_id"), "op1")
        self.assertIsInstance(seen.get("new_id"), int)
        self.assertEqual(seen.get("row"), ("a.wav", "/tmp/a.wav"))
        # Data was modified => dataChanged should have emitted once
        self.assertGreaterEqual(len(self.data_changed.calls), 1)

    def test_update_recording_modifies_data(self):
        """Updates via worker persist to the database."""
        # Seed a record directly using helper
        rec_id = self._create_test_recording("b.wav", "/tmp/b.wav", "2024-01-01 00:00:00", "10s")

        # Enqueue update: change raw_transcript
        self.worker.add_operation(
            "update_recording", "op_upd", [rec_id], {"raw_transcript": "hello"}
        )

        # Capture completion and verify in-place
        called = {"ok": False}

        def on_complete(op_id, _):  # noqa: ANN001
            called["ok"] = True
            cur = self.conn.execute(
                "SELECT raw_transcript FROM recordings WHERE id=?", (rec_id,)
            )
            row = cur.fetchone()
            self.assertEqual(row[0], "hello")

        self._setup_completion_capture(on_complete)

        self._run_single()

        self.assertTrue(called["ok"])
        self._assert_signal_emitted(self.data_changed, message="dataChanged should emit after update")

    def test_delete_recording_removes_data(self):
        """Deleting a record removes it from the table."""
        rec_id = self._create_test_recording("c.wav", "/tmp/c.wav")

        self.worker.add_operation("delete_recording", "op_del", [rec_id])

        def on_complete(op_id, _):  # noqa: ANN001
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM recordings WHERE id=?", (rec_id,)
            )
            self.assertEqual(cur.fetchone()[0], 0)

        self._setup_completion_capture(on_complete)

        self._run_single()
        self._assert_signal_emitted(self.data_changed, message="dataChanged should emit after delete")

    def test_unique_constraint_violation_logged_and_no_datachange(self):
        """Duplicate file_path should not trigger dataChanged and returns None result."""
        # Seed a record with a path using helper
        self._create_test_recording("d.wav", "/tmp/dup.wav")

        # Clear any previous dataChanged emissions
        self.data_changed.calls.clear()

        # Attempt to create duplicate
        dup_payload = ("d2.wav", "/tmp/dup.wav", "2024-01-01 00:00:00", "2s")
        self.worker.add_operation("create_recording", "op_dup", [dup_payload])

        # Do not expect a completion emission for duplicate errors
        self._run_single()
        self._assert_no_signal(self.op_complete, "Duplicate should not trigger completion")
        self._assert_no_signal(self.data_changed, "Duplicate should not trigger data change")

    def test_execute_query_insert_returns_lastrowid_and_datachange(self):
        """INSERT via execute_query returns lastrowid and triggers dataChanged."""
        # Prepare operation
        sql = (
            "INSERT INTO recordings (filename, file_path, date_created, duration)"
            " VALUES (?,?,?,?)"
        )
        params = ("e.wav", "/tmp/e.wav", "2024-01-01 00:00:00", "1s")

        # Enqueue with return_last_row_id
        op_id = "exec_ins"
        self.worker.add_operation(
            "execute_query",
            op_id,
            args=[sql, params],
            kwargs={"return_last_row_id": True},
        )

        seen = {}

        def on_complete(oid, result):  # noqa: ANN001
            seen["oid"] = oid
            seen["id"] = result
            cur = self.conn.execute(
                "SELECT filename FROM recordings WHERE id=?", (result,)
            )
            seen["row"] = cur.fetchone()

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]
        self._run_single()

        self.assertEqual(seen.get("oid"), op_id)
        self.assertIsInstance(seen.get("id"), int)
        self.assertEqual(seen.get("row"), ("e.wav",))
        self.assertGreaterEqual(len(self.data_changed.calls), 1)

    def test_execute_query_select_no_datachange(self):
        """SELECT via execute_query does not emit dataChanged and returns rows."""
        # Seed using helper
        rid = self._create_test_recording("f.wav", "/tmp/f.wav")
        self.data_changed.calls.clear()

        op_id = "exec_sel"
        self.worker.add_operation(
            "execute_query", op_id, args=["SELECT id, filename FROM recordings WHERE id=?", (rid,)]
        )

        seen = {}

        def on_complete(oid, result):  # noqa: ANN001
            seen["oid"] = oid
            seen["rows"] = result

        self._setup_completion_capture(on_complete)
        self._run_single()

        self.assertEqual(seen.get("oid"), op_id)
        self.assertEqual(seen.get("rows"), [(rid, "f.wav")])
        self._assert_no_signal(self.data_changed, "SELECT should not trigger dataChanged")

    def test_empty_queue_processing(self):
        """Running with only sentinel should terminate cleanly without processing operations."""
        # Track that the worker processes the queue and terminates properly
        initial_queue_size = self.worker.operations_queue.qsize()
        
        # Ensure no operations queued, just stop sentinel
        self.worker.operations_queue.put(None)
        
        # Run should process the sentinel and exit
        self.worker.run()
        
        # Verify queue was processed (sentinel consumed)
        self.assertEqual(self.worker.operations_queue.qsize(), initial_queue_size, 
                        "Queue should be back to initial size after processing sentinel")
        
        # No operations means no signals should be emitted
        self._assert_no_signal(self.op_complete, "No operations should complete")
        self._assert_no_signal(self.data_changed, "No data changes should occur")
        self._assert_no_signal(self.err_capture, "No errors should occur")

    def test_malformed_operation_handling(self):
        """Malformed operation (missing 'type') should emit error and continue processing."""
        # Add a valid operation after the malformed one to verify continued processing
        self.worker.operations_queue.put({})  # Malformed - missing 'type'
        
        # Add valid operation to verify worker continues after error
        valid_payload = ("valid.wav", "/tmp/valid.wav", "2024-01-01 00:00:00", "1s")
        self.worker.add_operation("create_recording", "valid_op", [valid_payload])
        
        # Track successful processing
        processed_valid = {"completed": False}
        
        def on_complete(op_id, result):  # noqa: ANN001
            if op_id == "valid_op":
                processed_valid["completed"] = True
                processed_valid["result"] = result
        
        self._setup_completion_capture(on_complete)
        
        self._run_single()
        
        # Verify error was emitted for malformed operation
        self.assertTrue(any(call and call[0] == 'invalid_operation' for call in self.err_capture.calls),
                       "Error should be emitted for malformed operation")
        
        # Verify worker continued and processed valid operation
        self.assertTrue(processed_valid["completed"], 
                       "Worker should continue processing after malformed operation")
        self.assertIsInstance(processed_valid.get("result"), int,
                            "Valid operation should complete successfully")

    def test_concurrent_create_same_path_sequential_queue(self):
        """Two creates with same path: first succeeds, second rejected."""
        payload = ("x.wav", "/tmp/dupe.wav", "2024-01-01 00:00:00", "1s")
        self.worker.add_operation("create_recording", "op1", [payload])
        self.worker.add_operation("create_recording", "op2", [payload])
        seen = {}

        def on_complete(oid, _):  # noqa: ANN001
            if oid == "op1":
                cur = self.conn.execute(
                    "SELECT COUNT(*) FROM recordings WHERE file_path=?",
                    ("/tmp/dupe.wav",),
                )
                seen["cnt"] = cur.fetchone()[0]

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]
        self._run_single()
        # Only first completes; second yields warning via error signal
        self.assertTrue(any(call and call[0] == 'Duplicate path error' for call in self.err_capture.calls))
        self.assertEqual(seen.get("cnt"), 1)

    def test_extremely_large_data_reasonable(self):
        """Insert reasonably large text to ensure handling without slowdown."""
        big = "x" * (256 * 1024)  # 256KB to keep unit tests fast
        payload = ("big.wav", "/tmp/big.wav", "2024-01-01 00:00:00", "1s", big, big)
        self.worker.add_operation("create_recording", "op_big", [payload])
        seen = {}

        def on_complete(oid, _):  # noqa: ANN001
            if oid == "op_big":
                cur = self.conn.execute(
                    "SELECT LENGTH(raw_transcript) FROM recordings WHERE file_path=?",
                    ("/tmp/big.wav",),
                )
                seen["len"] = cur.fetchone()[0]

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]
        self._run_single()
        self.assertEqual(seen.get("len"), len(big))

    def test_execute_query_update_affected_rows(self):
        """UPDATE should change only matching rows."""
        # Create test records using helper
        ids = [
            self._create_test_recording(f"u{i}.wav", f"/tmp/u{i}.wav")
            for i in range(3)
        ]
        
        sql = "UPDATE recordings SET duration=? WHERE id IN (?, ?)"
        params = ("2s", ids[0], ids[1])
        self.worker.add_operation("execute_query", "op_upd", [sql, params])
        
        seen = {}

        def on_complete(oid, _):  # noqa: ANN001
            if oid == "op_upd":
                rows = self.conn.execute(
                    "SELECT id, duration FROM recordings ORDER BY id"
                ).fetchall()
                seen["rows"] = rows

        self._setup_completion_capture(on_complete)
        self._run_single()
        
        rows = seen.get("rows")
        # Verify only the first two records were updated
        self.assertEqual(rows[0][1], "2s", "First record should be updated")
        self.assertEqual(rows[1][1], "2s", "Second record should be updated")
        self.assertEqual(rows[2][1], "1s", "Third record should remain unchanged")


if __name__ == "__main__":
    unittest.main()
