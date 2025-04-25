"""
Transcription-service module: local Whisper, MPS path, and OpenAI Whisper API.

Only change versus the prior version:
    • `_transcribe_with_api()` now has an explicit `base_url`
      parameter and enforces HTTPS on that value instead of
      mis-using `file_path` for the test harness.
"""

from __future__ import annotations

# ───────────────────────── imports ──────────────────────────
import os
import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import requests
import torch
from openai import OpenAI
from pyannote.audio import Pipeline
from transformers import (
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
    pipeline,
)

from ..utils import language_to_iso

# silence torchaudio backend warning
warnings.filterwarnings(
    "ignore",
    message="torchaudio._backend.set_audio_backend has been deprecated",
)

logger = logging.getLogger("transcribrr")


# ───────────────────── model-manager singleton ──────────────
class ModelManager:
    """Load & cache Transformer speech-seq-2-seq models."""

    _instance: "ModelManager | None" = None

    @classmethod
    def instance(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = ModelManager()
        return cls._instance

    # ------------------------------------------------------------------
    def __init__(self) -> None:
        from app.utils import ConfigManager

        cfg = ConfigManager.instance()
        self._models: Dict[str, Any] = {}
        self._processors: Dict[str, Any] = {}
        self.device = self._get_optimal_device(
            cfg.get("hardware_acceleration_enabled", True)
        )
        logger.info("ModelManager device: %s", self.device)

    # (unchanged helper methods:  _get_optimal_device, _get_free_gpu_memory,
    #                            get_model, get_processor, _load_model,
    #                            clear_cache, create_pipeline, release_memory)
    # ------------------------------------------------------------------
    # please keep existing bodies – omitted here for brevity
    # ------------------------------------------------------------------


# ───────────────────── transcription service ────────────────
class TranscriptionService:
    """Facade providing local or API transcription."""

    # ------------------------------------------------------
    def __init__(self) -> None:
        self.model_manager = ModelManager.instance()

    # (public method `transcribe_file` and local helpers
    #  `_transcribe_locally`, `_transcribe_with_mps`, `_add_speaker_detection`
    #  remain unchanged – omitted for brevity)
    # ------------------------------------------------------

    # ↓↓↓ UPDATED HELPER – full definition below ↓↓↓
    # ------------------------------------------------------
    def _transcribe_with_api(
        self,
        file_path: str,
        language: str,
        api_key: Optional[str],
        *,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        """
        Use OpenAI Whisper API for transcription.

        Args
        ----
        file_path : local audio file to send
        language  : human language name or ISO code
        api_key   : OpenAI key
        base_url  : override (mainly for tests).  Must be HTTPS.

        Returns
        -------
        dict  with at least `text` and `method`.
        """
        if not api_key:
            raise ValueError("OpenAI API transcription requires an API key")

        # default https endpoint
        if base_url is None:
            base_url = "https://api.openai.com/v1"

        # security: enforce HTTPS
        if not base_url.startswith("https://"):
            raise ValueError("API URL must use HTTPS for security")

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)

            with open(file_path, "rb") as audio_f:
                lang_iso = language_to_iso(language)
                logger.info("Sending audio to Whisper API (lang=%s)", lang_iso)

                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_f,
                    language=lang_iso,
                )

            if not resp or not resp.text:
                raise ValueError("OpenAI Whisper API returned empty response")

            return {"text": resp.text, "method": "api"}

        except Exception as exc:
            logger.error("OpenAI Whisper API error: %s", exc, exc_info=True)
            raise RuntimeError(
                f"OpenAI Whisper API transcription failed: {exc}"
            ) from exc
