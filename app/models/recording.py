"""Recording model class.

This dataclass originally only stored fields. To support more
meaningful tests and encapsulate common behaviors used across the app,
we add light validation helpers and convenience methods. These methods
are intentionally simple and fast, and do not introduce heavy runtime
dependencies.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple


def _format_seconds(total_seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS (flooring fractional seconds)."""
    seconds = int(total_seconds if total_seconds >= 0 else 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


@dataclass
class Recording:
    """Data class for recording information with light helpers."""

    id: int
    filename: str
    file_path: str
    date_created: str
    duration: float
    raw_transcript: Optional[str] = None
    processed_text: Optional[str] = None
    raw_transcript_formatted: Optional[str] = None
    processed_text_formatted: Optional[str] = None
    original_source_identifier: Optional[str] = None
    # Timestamps updated by helper methods; stored as ISO strings for simplicity
    transcribed_at: Optional[str] = None
    processed_at: Optional[str] = None

    # ---------- Validation helpers ----------
    @staticmethod
    def validate_duration(value: float) -> None:
        """Raise ValueError if duration is negative."""
        if value < 0:
            raise ValueError("Duration must be non-negative")

    @staticmethod
    def validate_filename(name: str) -> None:
        """Raise ValueError if filename is empty or whitespace."""
        if not name or not str(name).strip():
            raise ValueError("Filename cannot be empty")

    @staticmethod
    def validate_file_path(path: str) -> None:
        """Basic path validation to avoid traversal-like patterns.

        This is intentionally conservative for tests: reject paths that
        include ".." components that could escape directories.
        """
        if not path or not str(path).strip():
            raise ValueError("Invalid file path: empty")
        # Reject parent directory traversals common on POSIX/Windows
        if ".." in path.replace("\\", "/").split("/"):
            raise ValueError("Invalid file path")

    @staticmethod
    def validate_date_format(date_str: str) -> None:
        """Validate date format using common patterns.

        Accepts ISO-like formats: YYYY-MM-DD or YYYY-MM-DD HH:MM:SS.
        """
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                datetime.strptime(date_str, fmt)
                return
            except Exception:
                pass
        raise ValueError("Invalid date format")

    # ---------- Convenience/behavior helpers ----------
    def is_transcribed(self) -> bool:
        return bool(self.raw_transcript)

    def is_processed(self) -> bool:
        return bool(self.processed_text)

    def get_status(self) -> str:
        if self.is_processed():
            return "completed"
        if self.is_transcribed():
            return "transcribed"
        return "pending"

    def to_database_tuple(self) -> Tuple[object, ...]:
        """Return tuple in the DB column order used throughout the app."""
        return (
            self.id,
            self.filename,
            self.file_path,
            self.date_created,
            self.duration,
            self.raw_transcript,
            self.processed_text,
            self.raw_transcript_formatted,
            self.processed_text_formatted,
            self.original_source_identifier,
        )

    @classmethod
    def from_database_row(cls, row: Tuple[object, ...]) -> "Recording":
        """Create Recording from a database row tuple.

        Expected order:
        (id, filename, file_path, date_created, duration,
         raw_transcript, processed_text, raw_transcript_formatted,
         processed_text_formatted, original_source_identifier)
        """
        return cls(
            id=row[0],
            filename=row[1],
            file_path=row[2],
            date_created=row[3],
            duration=row[4],
            raw_transcript=row[5],
            processed_text=row[6],
            raw_transcript_formatted=row[7],
            processed_text_formatted=row[8],
            original_source_identifier=row[9],
        )

    def get_display_duration(self) -> str:
        """Return human-readable duration for display."""
        return _format_seconds(self.duration)

    def estimate_file_size(self, bitrate_kbps: int = 128) -> int:
        """Return estimated file size in bytes for typical MP3 bitrate.

        Default 128 kbps => 16,000 bytes per second.
        """
        bytes_per_sec = int((bitrate_kbps * 1000) / 8)
        return int(max(self.duration, 0) * bytes_per_sec)

    def update_transcript(self, text: str) -> None:
        """Update raw transcript and mark timestamp."""
        self.raw_transcript = text
        self.transcribed_at = datetime.utcnow().isoformat()

    def update_processed_text(self, text: str) -> None:
        """Update processed text and mark timestamp."""
        self.processed_text = text
        self.processed_at = datetime.utcnow().isoformat()
