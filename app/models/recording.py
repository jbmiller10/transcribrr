"""Recording model class."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Recording:
    """Data class for recording information."""

    id: int
    filename: str
    file_path: str
    date_created: str
    duration: float
    raw_transcript: Optional[str] = None
    processed_text: Optional[str] = None
    raw_transcript_formatted: Optional[str] = None
    processed_text_formatted: Optional[str] = None