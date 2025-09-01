"""Focused tests for Recording model business behavior."""

import unittest

import math
from unittest import mock

from app.models.recording import Recording, _format_seconds


class TestRecordingModel(unittest.TestCase):
    def test_recording_creation(self):
        """Test Recording creation with valid data."""
        r = Recording(
            id=1,
            filename="test.mp3",
            file_path="/path/to/test.mp3",
            date_created="2024-01-15 10:30:00",
            duration=120.5,
            raw_transcript="Test transcript",
        )
        self.assertEqual(r.id, 1)
        self.assertEqual(r.filename, "test.mp3")
        self.assertIsNone(r.processed_text)

    def test_invalid_duration_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            Recording.validate_duration(-30.5)
        self.assertIn("Duration must be non-negative", str(ctx.exception))

    def test_empty_filename_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            Recording.validate_filename("")
        self.assertIn("Filename cannot be empty", str(ctx.exception))

    def test_invalid_file_path(self):
        with self.assertRaises(ValueError) as ctx:
            Recording.validate_file_path("../../../etc/passwd")
        self.assertIn("Invalid file path", str(ctx.exception))

    def test_recording_with_pending_transcription(self):
        r = Recording(1, "pending.mp3", "/path/pending.mp3", "2024-01-15", 60.0)
        self.assertIsNone(r.raw_transcript)
        self.assertFalse(r.is_transcribed())
        self.assertEqual(r.get_status(), "pending")

    def test_recording_with_completed_transcription(self):
        r = Recording(
            1,
            "complete.mp3",
            "/path/complete.mp3",
            "2024-01-15",
            60.0,
            raw_transcript="Raw",
            processed_text="Processed",
        )
        self.assertTrue(r.is_transcribed())
        self.assertTrue(r.is_processed())
        self.assertEqual(r.get_status(), "completed")

    def test_to_database_tuple(self):
        r = Recording(1, "test.mp3", "/path/test.mp3", "2024-01-15", 60.0)
        db_tuple = r.to_database_tuple()
        self.assertEqual(len(db_tuple), 10)
        self.assertEqual(db_tuple[0], 1)
        self.assertEqual(db_tuple[1], "test.mp3")

    def test_from_database_row(self):
        row = (1, "test.mp3", "/path/test.mp3", "2024-01-15", 60.0,
               "Raw", "Processed", None, None, "source_1")
        r = Recording.from_database_row(row)
        self.assertEqual(r.id, 1)
        self.assertEqual(r.raw_transcript, "Raw")

    def test_missing_required_fields(self):
        with self.assertRaises(TypeError):
            Recording(filename="test.mp3")  # type: ignore[call-arg]

    def test_malformed_date_format(self):
        with self.assertRaises(ValueError) as ctx:
            Recording.validate_date_format("not-a-date")
        self.assertIn("Invalid date format", str(ctx.exception))

    def test_recording_equality(self):
        r1 = Recording(1, "test.mp3", "/path", "2024-01-15", 60.0)
        r2 = Recording(1, "test.mp3", "/path", "2024-01-15", 60.0)
        r3 = Recording(2, "test.mp3", "/path", "2024-01-15", 60.0)
        self.assertEqual(r1, r2)
        self.assertNotEqual(r1, r3)

    def test_get_display_duration(self):
        r = Recording(1, "test.mp3", "/path", "2024-01-15", 125.5)
        self.assertEqual(r.get_display_duration(), "2:05")
        r2 = Recording(2, "test.mp3", "/path", "2024-01-15", 3665.0)
        self.assertEqual(r2.get_display_duration(), "1:01:05")

    def test_get_file_size_estimate(self):
        r = Recording(1, "test.mp3", "/path", "2024-01-15", 60.0)
        self.assertAlmostEqual(r.estimate_file_size(), 960000, delta=1000)

    def test_update_transcript(self):
        r = Recording(1, "test.mp3", "/path", "2024-01-15", 60.0)
        self.assertIsNone(r.raw_transcript)
        r.update_transcript("New transcript")
        self.assertEqual(r.raw_transcript, "New transcript")
        self.assertIsNotNone(r.transcribed_at)

    def test_update_processed_text(self):
        r = Recording(1, "test.mp3", "/path", "2024-01-15", 60.0, raw_transcript="Raw")
        r.update_processed_text("Processed")
        self.assertEqual(r.processed_text, "Processed")
        self.assertIsNotNone(r.processed_at)

    # --- Additional boundary and edge case tests (per plan) ---
    def test_validate_duration_allows_zero_and_infinity_and_nan(self):
        Recording.validate_duration(0.0)  # no exception
        Recording.validate_duration(float("inf"))  # no exception
        # NaN comparisons are falsey; our validator only checks < 0
        Recording.validate_duration(float("nan"))  # no exception

    def test_validate_filename_whitespace_only_rejected(self):
        with self.assertRaises(ValueError):
            Recording.validate_filename(" \t\n ")

    def test_validate_file_path_encoded_traversal_not_decoded(self):
        # Literal '...'
        Recording.validate_file_path("/safe/.../path")
        # Encoded '.%2e' treated literally, allowed by validator
        Recording.validate_file_path("/.%2e/dir/file")

    def test_validate_file_path_long_and_reserved_names(self):
        long_path = "/" + ("a" * 5000)
        Recording.validate_file_path(long_path)
        Recording.validate_file_path("CON")  # allowed by validator

    def test_validate_date_format_invalid_month_and_timezone(self):
        with self.assertRaises(ValueError):
            Recording.validate_date_format("2024-13-01")
        with self.assertRaises(ValueError):
            Recording.validate_date_format("2024-01-15T10:30:00Z")

    def test_format_seconds_boundaries_and_fractional(self):
        self.assertEqual(_format_seconds(-1), "0:00")
        self.assertEqual(_format_seconds(59.999), "0:59")
        self.assertEqual(_format_seconds(60), "1:00")
        self.assertEqual(_format_seconds(3600.5), "1:00:00")

    def test_get_display_duration_infinity_raises(self):
        r = Recording(1, "t.mp3", "/p", "2024-01-15", float("inf"))
        with self.assertRaises(OverflowError):
            r.get_display_duration()

    def test_estimate_file_size_edge_cases(self):
        r = Recording(1, "t.mp3", "/p", "2024-01-15", 60.0)
        self.assertEqual(r.estimate_file_size(bitrate_kbps=0), 0)
        self.assertEqual(r.estimate_file_size(bitrate_kbps=1), int(60 * (1000 / 8)))
        self.assertEqual(r.estimate_file_size(bitrate_kbps=100000), int(60 * (100000 * 1000 / 8)))
        rneg = Recording(2, "t.mp3", "/p", "2024-01-15", -10.0)
        self.assertEqual(rneg.estimate_file_size(), 0)

    def test_update_transcript_allows_empty_and_sets_timestamp(self):
        r = Recording(1, "t.mp3", "/p", "2024-01-15", 1.0)
        with mock.patch("app.models.recording.datetime") as mdt:
            mdt.utcnow.return_value.isoformat.return_value = "2024-01-15T10:30:00"
            r.update_transcript("")
        self.assertEqual(r.raw_transcript, "")
        self.assertEqual(r.transcribed_at, "2024-01-15T10:30:00")

    def test_update_processed_text_without_raw_transcript(self):
        r = Recording(1, "t.mp3", "/p", "2024-01-15", 1.0)
        with mock.patch("app.models.recording.datetime") as mdt:
            mdt.utcnow.return_value.isoformat.return_value = "2024-01-15T10:31:00"
            r.update_processed_text("proc")
        self.assertEqual(r.processed_text, "proc")
        self.assertEqual(r.processed_at, "2024-01-15T10:31:00")

    def test_status_with_whitespace_is_completed(self):
        r = Recording(1, "t.mp3", "/p", "2024-01-15", 1.0, raw_transcript="   ", processed_text="\n\t")
        self.assertEqual(r.get_status(), "completed")

    def test_is_transcribed_empty_vs_none(self):
        r1 = Recording(1, "t.mp3", "/p", "2024-01-15", 1.0, raw_transcript="")
        r2 = Recording(2, "t.mp3", "/p", "2024-01-15", 1.0, raw_transcript=None)
        self.assertFalse(r1.is_transcribed())
        self.assertFalse(r2.is_transcribed())

    def test_from_database_row_wrong_lengths(self):
        short = (1, "f", "/p", "2024-01-01", 1.0, None, None, None, None)  # 9 elements
        with self.assertRaises(IndexError):
            Recording.from_database_row(short)
        long = (1, "f", "/p", "2024-01-01", 1.0, None, None, None, None, None, "extra")
        r = Recording.from_database_row(long)
        self.assertEqual(r.id, 1)

    def test_from_database_row_wrong_types(self):
        row = ("1", 123, 456, 789, "sixty", [], {}, b"rf", b"pf", 0)
        r = Recording.from_database_row(row)  # type: ignore[arg-type]
        self.assertEqual(r.id, "1")
        self.assertEqual(r.filename, 123)

    def test_recording_unhashable(self):
        r = Recording(1, "f", "/p", "2024-01-01", 1.0)
        with self.assertRaises(TypeError):
            {r: "value"}


if __name__ == "__main__":
    unittest.main()
