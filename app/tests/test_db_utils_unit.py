"""Focused unit tests for app.db_utils using an in-memory SQLite database.

Reduces mocking to validate actual SQL behavior and state changes.
"""

import unittest
from unittest.mock import Mock, patch
import sqlite3

from app import db_utils
from app.models.recording import Recording


class TestDbUtilsCRUD(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        db_utils.create_recordings_table(self.conn)

    def test_create_recording_inserts_data_and_returns_id(self):
        rec = ("file.wav", "/tmp/file.wav", "2024-01-02T03:04:05", "10:00")
        new_id = db_utils.create_recording(self.conn, rec)
        # Verify actual database state
        cur = self.conn.cursor()
        cur.execute("SELECT id, filename, file_path, duration FROM recordings WHERE id=?", (new_id,))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "file.wav")
        self.assertEqual(row[2], "/tmp/file.wav")
        self.assertEqual(row[3], "10:00")
        self.assertGreater(new_id, 0)

    def test_create_recording_raises_on_duplicate_path(self):
        db_utils.create_recording(self.conn, ("a", "/x", "t", "d"))
        with self.assertRaises(db_utils.DuplicatePathError):
            db_utils.create_recording(self.conn, ("b", "/x", "t2", "d2"))

    def test_update_recording_ignores_invalid_fields(self):
        rid = db_utils.create_recording(self.conn, ("n.wav", "/p/n.wav", "t", "00:01"))
        # Update valid and invalid fields
        db_utils.update_recording(self.conn, rid, raw_transcript="x", filename="name.wav", unknown="bad")
        cur = self.conn.cursor()
        cur.execute("SELECT filename, raw_transcript FROM recordings WHERE id=?", (rid,))
        row = cur.fetchone()
        self.assertEqual(row[0], "name.wav")
        self.assertEqual(row[1], "x")

    def test_update_recording_no_fields(self):
        # Arrange: Create a recording with known values
        rid = db_utils.create_recording(self.conn, ("a.wav", "/p/a.wav", "t", "00:01", "raw", "proc"))
        
        # Get original state to verify no changes
        cur = self.conn.cursor()
        cur.execute("SELECT filename, file_path, duration, raw_transcript, processed_text FROM recordings WHERE id=?", (rid,))
        original_state = cur.fetchone()
        
        # Act: Update with no fields (should be a no-op)
        db_utils.update_recording(self.conn, rid)
        
        # Assert: Verify ALL fields remain unchanged
        cur.execute("SELECT filename, file_path, duration, raw_transcript, processed_text FROM recordings WHERE id=?", (rid,))
        current_state = cur.fetchone()
        self.assertEqual(original_state, current_state, "No fields should change when update called with no arguments")

    def test_delete_recording_executes(self):
        # Arrange: Create a recording and verify it exists
        rid = db_utils.create_recording(self.conn, ("b.wav", "/p/b.wav", "t", "00:02"))
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM recordings WHERE id=?", (rid,))
        self.assertEqual(cur.fetchone()[0], 1, "Recording should exist before deletion")
        
        # Act: Delete the recording
        db_utils.delete_recording(self.conn, rid)
        
        # Assert: Verify the recording is actually deleted
        cur.execute("SELECT COUNT(*) FROM recordings WHERE id=?", (rid,))
        self.assertEqual(cur.fetchone()[0], 0, "Recording should be deleted")

    def test_create_recording_with_empty_tuple_raises(self):
        with self.assertRaises(ValueError):
            db_utils.create_recording(self.conn, tuple())

    def test_create_recording_sql_injection_literal(self):
        malicious = "'; DROP TABLE recordings; --"
        rec = (malicious, "/tmp/mal.wav", "2024-01-02T03:04:05", "10:00")
        new_id = db_utils.create_recording(self.conn, rec)
        cur = self.conn.cursor()
        cur.execute("SELECT filename FROM recordings WHERE id=?", (new_id,))
        self.assertEqual(cur.fetchone()[0], malicious)

    def test_create_recording_large_fields(self):
        # Keep size reasonable for unit tests while still non-trivial
        big_text = "x" * (256 * 1024)  # 256KB
        rec = ("big.wav", "/tmp/big.wav", "2024-01-02T03:04:05", "10:00", big_text, big_text)
        new_id = db_utils.create_recording(self.conn, rec)
        self.assertGreater(new_id, 0)

    def test_create_recording_null_in_required_field_raises(self):
        with self.assertRaises(sqlite3.IntegrityError):
            db_utils.create_recording(self.conn, ("f.wav", None, "2024-01-01", "10:00"))

    def test_update_recording_injection_in_value_is_literal(self):
        rid = db_utils.create_recording(self.conn, ("u.wav", "/p/u.wav", "t", "00:01"))
        payload = "'; DROP TABLE recordings; --"
        db_utils.update_recording(self.conn, rid, raw_transcript=payload)
        cur = self.conn.cursor()
        cur.execute("SELECT raw_transcript FROM recordings WHERE id=?", (rid,))
        self.assertEqual(cur.fetchone()[0], payload)

    def test_update_nonexistent_id_succeeds_silently(self):
        # Arrange: Verify the ID doesn't exist
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM recordings WHERE id=?", (9999,))
        self.assertEqual(cur.fetchone()[0], 0, "ID 9999 should not exist")
        
        # Act: Update non-existent ID (should not raise)
        try:
            db_utils.update_recording(self.conn, 9999, filename="none.wav")
        except Exception as e:
            self.fail(f"update_recording should not raise for non-existent ID: {e}")
        
        # Assert: Verify no records were created or modified
        cur.execute("SELECT COUNT(*) FROM recordings")
        self.assertEqual(cur.fetchone()[0], 0, "No records should be created")

    def test_delete_nonexistent_id_succeeds(self):
        # Arrange: Verify the ID doesn't exist
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM recordings WHERE id=?", (9999,))
        self.assertEqual(cur.fetchone()[0], 0, "ID 9999 should not exist")
        
        # Act & Assert: Deleting a non-existent row should not raise
        try:
            db_utils.delete_recording(self.conn, 9999)
        except Exception as e:
            self.fail(f"delete_recording should not raise for non-existent ID: {e}")
        
        # Verify table still exists and is queryable
        cur.execute("SELECT COUNT(*) FROM recordings")
        self.assertIsNotNone(cur.fetchone(), "Table should still be accessible")


class TestDbUtilsQueries(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        db_utils.create_recordings_table(self.conn)

    def test_get_all_recordings(self):
        # Insert two records
        db_utils.create_recording(self.conn, ("x.wav", "/p/x.wav", "t", "00:01"))
        db_utils.create_recording(self.conn, ("y.wav", "/p/y.wav", "t", "00:02"))
        rows = db_utils.get_all_recordings(self.conn)
        self.assertEqual(len(rows), 2)

    def test_get_recording_by_id_none(self):
        rec = db_utils.get_recording_by_id(self.conn, 999)
        self.assertIsNone(rec)

    def test_get_recording_by_id_maps_fields(self):
        rid = db_utils.create_recording(
            self.conn,
            ("name.wav", "/p/name.wav", "2024-01-02T03:04:05", "00:10", "raw", "proc"),
        )
        # Manually update blob fields and original_source_identifier
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE recordings SET raw_transcript_formatted=?, processed_text_formatted=?, original_source_identifier=? WHERE id=?",
            (b"rf", b"pf", "orig", rid),
        )
        self.conn.commit()
        result = db_utils.get_recording_by_id(self.conn, rid)
        self.assertIsInstance(result, Recording)
        self.assertEqual(result.id, rid)
        self.assertEqual(result.filename, "name.wav")
        self.assertEqual(result.file_path, "/p/name.wav")
        self.assertEqual(result.duration, "00:10")
        self.assertEqual(result.raw_transcript, "raw")
        self.assertEqual(result.processed_text, "proc")
        self.assertEqual(result.raw_transcript_formatted, b"rf")
        self.assertEqual(result.processed_text_formatted, b"pf")
        self.assertEqual(result.original_source_identifier, "orig")

    def test_recording_exists_true_false(self):
        db_utils.create_recording(self.conn, ("a.wav", "/a", "t", "00:01"))
        self.assertTrue(db_utils.recording_exists(self.conn, "/a"))
        self.assertFalse(db_utils.recording_exists(self.conn, "/b"))

    def test_search_recordings(self):
        db_utils.create_recording(self.conn, ("hello.wav", "/p/h.wav", "t", "00:01", "raw term", ""))
        rows = db_utils.search_recordings(self.conn, "term")
        self.assertGreaterEqual(len(rows), 1)

    def test_get_recording_by_id_negative_returns_none(self):
        self.assertIsNone(db_utils.get_recording_by_id(self.conn, -1))

    def test_get_recording_by_id_pending_date_is_replaced(self):
        # Insert a row with 'pending' date to simulate corrupted/placeholder value
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO recordings(filename, file_path, date_created, duration) VALUES(?,?,?,?)",
            ("p.wav", "/p/p.wav", "pending", "00:01"),
        )
        rid = cur.lastrowid
        self.conn.commit()
        rec = db_utils.get_recording_by_id(self.conn, rid)
        self.assertIsNotNone(rec)
        self.assertNotEqual(rec.date_created, "pending")
        # Ensure it is ISO formatted
        from datetime import datetime
        datetime.fromisoformat(rec.date_created)

    def test_get_recording_by_id_missing_legacy_column_handled(self):
        # Simulate legacy schema by mocking fetchone to return 9 columns
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (
            1, "f.wav", "/p", "2024-01-01", "10:00", None, None, None, None
        )
        rec = db_utils.get_recording_by_id(mock_conn, 1)
        self.assertIsInstance(rec, Recording)
        self.assertIsNone(rec.original_source_identifier)

    def test_get_recording_by_id_sql_injection_in_id_is_literal(self):
        # Passing a malicious string should not cause injection; it should just return None
        db_utils.create_recording(self.conn, ("a.wav", "/p/a.wav", "t", "00:01"))
        result = db_utils.get_recording_by_id(
            self.conn, "1 OR 1=1; DROP TABLE recordings; --"  # type: ignore[arg-type]
        )
        self.assertIsNone(result)

    def test_recording_exists_with_special_chars(self):
        path = "/path/with'quotes\"and%wildcards_"
        db_utils.create_recording(self.conn, ("s.wav", path, "t", "00:01"))
        self.assertTrue(db_utils.recording_exists(self.conn, path))

    def test_search_empty_string_returns_all(self):
        # Insert a few records
        for i in range(3):
            db_utils.create_recording(self.conn, (f"f{i}.wav", f"/p/f{i}.wav", "t", "00:01"))
        rows = db_utils.search_recordings(self.conn, "")
        self.assertEqual(len(rows), 3)

    def test_search_unicode_term(self):
        db_utils.create_recording(self.conn, ("🎵 録音(レコーディング).wav", "/path/音楽", "2024-01-01", "10:00"))
        rows = db_utils.search_recordings(self.conn, "録音")
        self.assertGreaterEqual(len(rows), 1)


class TestEnsureDatabaseExists(unittest.TestCase):
    def setUp(self):
        """Set up common mocks for ensure_database_exists tests."""
        self.mock_conn = Mock()
        self.patches = [
            patch("app.db_utils.create_recordings_table"),
            patch("app.db_utils.create_folders_table"),
            patch("app.db_utils.create_recording_folders_table"),
            patch("app.db_utils.get_connection", return_value=self.mock_conn),
            patch("app.db_utils.get_config_path", return_value="/tmp/nonexistent/config.json"),
            patch("app.db_utils.create_config_file"),
        ]
        self.mocks = [p.start() for p in self.patches]
        (
            self.mock_create_recordings,
            self.mock_create_folders,
            self.mock_create_rf_table,
            self.mock_get_connection,
            self.mock_get_config_path,
            self.mock_create_config,
        ) = self.mocks

    def tearDown(self):
        """Stop all patches."""
        for p in self.patches:
            p.stop()

    def test_ensure_database_exists_creates_tables_and_config(self):
        # Act
        db_utils.ensure_database_exists()

        # Assert: tables created and config attempted
        self.mock_create_recordings.assert_called_once_with(self.mock_conn)
        self.mock_create_folders.assert_called_once_with(self.mock_conn)
        self.mock_create_rf_table.assert_called_once_with(self.mock_conn)
        self.mock_create_config.assert_called_once()
        self.mock_conn.close.assert_called_once()

    def test_ensure_database_exists_config_creation_failure_propagates(self):
        # Arrange: Mock config creation to fail
        with patch("app.db_utils.os.path.exists", return_value=False):
            self.mock_create_config.side_effect = PermissionError("Cannot write")
            
            # Act & Assert: PermissionError should propagate
            with self.assertRaises(PermissionError) as cm:
                db_utils.ensure_database_exists()
            
            # Assert: Error message is preserved
            self.assertIn("Cannot write", str(cm.exception))
            
            # Assert: Connection is still closed on error
            self.mock_conn.close.assert_called_once()


class TestConnectionAndErrors(unittest.TestCase):
    """Test database connection handling and error scenarios."""
    
    def _create_mock_connection_with_cursor(self, execute_side_effect=None):
        """Helper to create a mock connection with a cursor."""
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        if execute_side_effect:
            mock_cursor.execute.side_effect = execute_side_effect
        return mock_conn, mock_cursor
    def test_get_connection_locked_raises_runtimeerror_and_logs(self):
        with patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")), \
             patch("app.db_utils.get_database_path", return_value="/x/db.sqlite"), \
             patch("app.db_utils.os.path.dirname", return_value="/x"), \
             patch("app.db_utils.os.makedirs") as mk, \
             patch("app.db_utils.logger") as log:
            with self.assertRaises(RuntimeError):
                db_utils.get_connection()
            mk.assert_called_once()
            log.critical.assert_called()

    def test_get_connection_corrupted_raises_runtimeerror(self):
        with patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.DatabaseError("file is not a database")):
            with self.assertRaises(RuntimeError):
                db_utils.get_connection()

    def test_get_connection_permission_denied_propagates(self):
        with patch("app.db_utils.os.makedirs", side_effect=PermissionError("denied")), \
             patch("app.db_utils.sqlite3.connect") as conn:
            with self.assertRaises(PermissionError):
                db_utils.get_connection()
            conn.assert_not_called()

    def test_create_recording_not_null_violation_propagates(self):
        # Arrange: Mock connection with IntegrityError
        mock_conn, _ = self._create_mock_connection_with_cursor(
            sqlite3.IntegrityError("NOT NULL constraint failed: recordings.filename")
        )
        
        # Act & Assert: IntegrityError should propagate
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            db_utils.create_recording(mock_conn, (None, "/p/x", "t", "d"))
        self.assertIn("NOT NULL constraint failed", str(cm.exception))

    def test_delete_recording_integrity_error_propagates(self):
        # Arrange: Mock connection with IntegrityError
        mock_conn, _ = self._create_mock_connection_with_cursor(
            sqlite3.IntegrityError("FOREIGN KEY constraint failed")
        )
        
        # Act & Assert: IntegrityError should propagate
        with self.assertRaises(sqlite3.IntegrityError) as cm:
            db_utils.delete_recording(mock_conn, 1)
        self.assertIn("FOREIGN KEY constraint failed", str(cm.exception))

    def test_recording_exists_database_error_propagates(self):
        # Arrange: Mock connection with DatabaseError
        mock_conn, _ = self._create_mock_connection_with_cursor(
            sqlite3.DatabaseError("malformed")
        )
        
        # Act & Assert: DatabaseError should propagate
        with self.assertRaises(sqlite3.DatabaseError) as cm:
            db_utils.recording_exists(mock_conn, "/any")
        self.assertIn("malformed", str(cm.exception))

    def test_get_connection_success_sets_pragmas(self):
        mock_conn = Mock()
        with patch("app.db_utils.sqlite3.connect", return_value=mock_conn) as pconnect, \
             patch("app.db_utils.get_database_path", return_value="/x/db.sqlite"), \
             patch("app.db_utils.os.path.dirname", return_value="/x"), \
             patch("app.db_utils.os.makedirs"):
            conn = db_utils.get_connection()
            self.assertIs(conn, mock_conn)
            mock_conn.execute.assert_called_with("PRAGMA foreign_keys = ON")
            pconnect.assert_called_with(
                "/x/db.sqlite", timeout=30.0, isolation_level=None, check_same_thread=False
            )

    def test_create_recordings_table_success_commits_and_indexes(self):
        # Arrange: Create mock connection
        mock_conn, mock_cursor = self._create_mock_connection_with_cursor()
        
        # Act: Create recordings table
        db_utils.create_recordings_table(mock_conn)
        
        # Assert: Verify table creation and indexing
        self.assertGreaterEqual(mock_cursor.execute.call_count, 2, 
                                "Should execute CREATE TABLE and at least one CREATE INDEX")
        mock_conn.commit.assert_called_once()

    def test_create_recordings_table_sql_error_logs_and_raises(self):
        # Arrange: Mock connection with SQL error
        mock_conn, _ = self._create_mock_connection_with_cursor(
            sqlite3.OperationalError("near \"TABL\": syntax error")
        )
        
        # Act & Assert: Error should be logged and raised
        with patch("app.db_utils.logger") as log:
            with self.assertRaises(sqlite3.OperationalError) as cm:
                db_utils.create_recordings_table(mock_conn)
            
            # Verify error was logged
            log.error.assert_called()
            # Verify original error message is preserved
            self.assertIn("syntax error", str(cm.exception))

    def test_update_recording_locked_raises(self):
        # Arrange: Mock connection with locked database error
        mock_conn, _ = self._create_mock_connection_with_cursor(
            sqlite3.OperationalError("database is locked")
        )
        
        # Act & Assert: OperationalError should propagate
        with self.assertRaises(sqlite3.OperationalError) as cm:
            db_utils.update_recording(mock_conn, 1, filename="x")
        self.assertIn("database is locked", str(cm.exception))


    def test_create_config_file_dump_error_propagates(self):
        with patch("app.db_utils.get_config_path", return_value="/tmp/config.json"), \
             patch("builtins.open") as mock_open, \
             patch("app.db_utils.json.dump", side_effect=OSError("No space left on device")):
            mock_open.return_value.__enter__.return_value = Mock()
            with self.assertRaises(OSError):
                db_utils.create_config_file()

    def test_get_connection_disk_io_error_raises_runtimeerror(self):
        with patch("app.db_utils.sqlite3.connect", side_effect=sqlite3.OperationalError("disk I/O error")):
            with self.assertRaises(RuntimeError):
                db_utils.get_connection()

    def test_ensure_database_exists_connection_failure_short_circuits(self):
        with patch("app.db_utils.get_connection", side_effect=RuntimeError("connect fail")), \
             patch("app.db_utils.create_recordings_table") as cr, \
             patch("app.db_utils.create_folders_table") as cf, \
             patch("app.db_utils.create_recording_folders_table") as crf:
            with self.assertRaises(RuntimeError):
                db_utils.ensure_database_exists()
            cr.assert_not_called()
            cf.assert_not_called()
            crf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
