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

        # Create worker and swap in our connection
        self.worker = DatabaseWorker(parent=None)
        self.worker.conn = self.conn

        # Replace signals with lightweight captures
        self.op_complete = _Capture()
        self.data_changed = _Capture()
        self.worker.operation_complete = self.op_complete
        self.worker.dataChanged = self.data_changed
        self.err_capture = _Capture()
        self.worker.error_occurred = self.err_capture

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
        # Seed a record directly
        rec_id = db_create_recording(
            self.conn, ("b.wav", "/tmp/b.wav", "2024-01-01 00:00:00", "10s")
        )

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

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]

        self._run_single()

        self.assertTrue(called["ok"])
        self.assertGreaterEqual(len(self.data_changed.calls), 1)

    def test_delete_recording_removes_data(self):
        """Deleting a record removes it from the table."""
        rec_id = db_create_recording(
            self.conn, ("c.wav", "/tmp/c.wav", "2024-01-01 00:00:00", "1s")
        )

        self.worker.add_operation("delete_recording", "op_del", [rec_id])

        def on_complete(op_id, _):  # noqa: ANN001
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM recordings WHERE id=?", (rec_id,)
            )
            self.assertEqual(cur.fetchone()[0], 0)

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]

        self._run_single()
        self.assertGreaterEqual(len(self.data_changed.calls), 1)

    def test_unique_constraint_violation_logged_and_no_datachange(self):
        """Duplicate file_path should not trigger dataChanged and returns None result."""
        # Seed a record with a path
        db_create_recording(
            self.conn, ("d.wav", "/tmp/dup.wav", "2024-01-01 00:00:00", "1s")
        )

        # Clear any previous dataChanged emissions
        self.data_changed.calls.clear()

        # Attempt to create duplicate
        dup_payload = ("d2.wav", "/tmp/dup.wav", "2024-01-01 00:00:00", "2s")
        self.worker.add_operation("create_recording", "op_dup", [dup_payload])

        # Do not expect a completion emission for duplicate errors
        self._run_single()
        self.assertEqual(len(self.op_complete.calls), 0)
        self.assertEqual(len(self.data_changed.calls), 0)

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
        # Seed
        rid = db_create_recording(
            self.conn, ("f.wav", "/tmp/f.wav", "2024-01-01 00:00:00", "1s")
        )
        self.data_changed.calls.clear()

        op_id = "exec_sel"
        self.worker.add_operation(
            "execute_query", op_id, args=["SELECT id, filename FROM recordings WHERE id=?", (rid,)]
        )

        seen = {}

        def on_complete(oid, result):  # noqa: ANN001
            seen["oid"] = oid
            seen["rows"] = result

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]
        self._run_single()

        self.assertEqual(seen.get("oid"), op_id)
        self.assertEqual(seen.get("rows"), [(rid, "f.wav")])
        self.assertEqual(len(self.data_changed.calls), 0)

    def test_empty_queue_processing(self):
        """Running with only sentinel should not emit signals or error."""
        # Ensure no operations queued, just stop
        self.worker.operations_queue.put(None)
        self.worker.run()
        self.assertEqual(len(self.op_complete.calls), 0)
        self.assertEqual(len(self.data_changed.calls), 0)
        self.assertEqual(len(self.err_capture.calls), 0)

    def test_malformed_operation_handling(self):
        """Malformed operation (missing 'type') should emit error and continue."""
        # Directly inject a malformed dict into queue
        self.worker.operations_queue.put({})
        self.worker.operations_queue.put(None)
        self.worker.run()
        # Expect an error emission with 'invalid_operation'
        self.assertTrue(any(call and call[0] == 'invalid_operation' for call in self.err_capture.calls))
        # No completion for malformed op
        self.assertEqual(len(self.op_complete.calls), 0)

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
        big = "x" * (1024 * 1024)  # 1MB
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
        ids = [
            db_create_recording(self.conn, (f"u{i}.wav", f"/tmp/u{i}.wav", "2024-01-01 00:00:00", "1s"))
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

        self.worker.operation_complete.emit = on_complete  # type: ignore[attr-defined]
        self._run_single()
        rows = seen.get("rows")
        self.assertEqual(rows[0][1], "2s")
        self.assertEqual(rows[1][1], "2s")
        self.assertEqual(rows[2][1], "1s")


if __name__ == "__main__":
    unittest.main()
