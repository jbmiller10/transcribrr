"""Focused tests for Recording model business behavior."""

import unittest

from app.models.recording import Recording


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


if __name__ == "__main__":
    unittest.main()

