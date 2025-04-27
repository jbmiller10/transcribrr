from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Recording:
    id: int
    filename: str
    file_path: str
    date_created: datetime
    duration: Optional[float] = None
    raw_transcript: Optional[str] = None
    processed_text: Optional[str] = None
    raw_transcript_formatted: Optional[str] = None
    processed_text_formatted: Optional[str] = None
    original_source_identifier: Optional[str] = None

    def has_raw(self) -> bool:
        """Check if this recording has a raw transcript."""
        return bool(self.raw_transcript)

    def has_processed(self) -> bool:
        """Check if this recording has processed text."""
        return bool(self.processed_text)
