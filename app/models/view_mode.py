"""View mode enum for transcript view."""

from enum import Enum, auto


class ViewMode(Enum):
    """Enum for different transcript view modes."""

    RAW = auto()
    PROCESSED = auto()