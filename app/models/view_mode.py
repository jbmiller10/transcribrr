"""View mode enum for transcript view."""

from enum import Enum, auto


class ViewMode(Enum):
    """Enum for different transcript view modes."""

    # Using explicit values (0, 1) to match the toggle switch values
    RAW = 0
    PROCESSED = 1