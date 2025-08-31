"""Controllers package for managing application logic.

This package avoids importing heavyweight Qt or thread dependencies at
module import time (important for headless CI). Controllers are imported
on-demand via attribute access.
"""

__all__ = ["TranscriptionController", "GPTController"]


def __getattr__(name: str):  # pragma: no cover - trivial accessor
    if name == "TranscriptionController":
        from .transcription_controller import TranscriptionController

        return TranscriptionController
    if name == "GPTController":
        from .gpt_controller import GPTController

        return GPTController
    raise AttributeError(f"module 'app.controllers' has no attribute {name!r}")
