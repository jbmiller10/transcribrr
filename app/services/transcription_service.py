"""
Transcription service: local Whisper, MPS path, and OpenAI Whisper API.
"""

from __future__ import annotations

# ───────────────────────── imports ──────────────────────────
import gc
import logging
import os
import warnings
from typing import Any, Dict, Optional

import numpy as np
import requests
import torch
from openai import OpenAI
from transformers import (
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
    pipeline,
)

from ..utils import language_to_iso

warnings.filterwarnings(
    "ignore",
    message="torchaudio._backend.set_audio_backend has been deprecated",
)

logger = logging.getLogger("transcribrr")


# ───────────────────── model-manager singleton ──────────────
class ModelManager:
    _instance: "ModelManager | None" = None

    @classmethod
    def instance(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = ModelManager()
        return cls._instance

    # ----------------------------------------------------------
    def __init__(self) -> None:
        from app.utils import ConfigManager

        cfg = ConfigManager.instance()
        self._models: Dict[str, Any] = {}
        self._processors: Dict[str, Any] = {}
        self.device = self._get_optimal_device(
            cfg.get("hardware_acceleration_enabled", True)
        )
        logger.info("ModelManager device: %s", self.device)

    # ─────────────── helpers (fully implemented) ─────────────
    def _get_optimal_device(self, accel: bool = True) -> str:
        if not accel:
            return "cpu"
        if torch.cuda.is_available():
            if self._get_free_gpu_memory() > 2.0:
                return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _get_free_gpu_memory(self) -> float:
        try:
            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                total = props.total_memory / 1024 ** 3
                alloc = torch.cuda.memory_allocated(0) / 1024 ** 3
                return total - alloc
        except Exception:
            pass
        return 0.0

    # ----------------------------------------------------------
    def get_model(self, model_id: str) -> Any:
        if model_id not in self._models:
            logger.info("Loading model: %s", model_id)
            self._models[model_id] = self._load_model(model_id)
        return self._models[model_id]

    def get_processor(self, model_id: str) -> Any:
        if model_id not in self._processors:
            self._processors[model_id] = AutoProcessor.from_pretrained(model_id)
        return self._processors[model_id]

    def _load_model(self, model_id: str) -> Any:
        mdl = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
        mdl.to(self.device)
        return mdl

    def clear_cache(self) -> None:
        self._models.clear()
        self._processors.clear()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        gc.collect()

    def create_pipeline(
        self, model_id: str, language: str = "english", chunk_length_s: int = 30
    ) -> Any:
        mdl = self.get_model(model_id)
        proc = self.get_processor(model_id)
        return pipeline(
            "automatic-speech-recognition",
            model=mdl,
            tokenizer=proc.tokenizer,
            feature_extractor=proc.feature_extractor,
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32,
            chunk_length_s=chunk_length_s,
            batch_size=8,
            return_timestamps=True,
            device=self.device,
            generate_kwargs={"language": language.lower()},
        )


# ───────────────────── transcription service ────────────────
class TranscriptionService:
    def __init__(self) -> None:
        self.model_manager = ModelManager.instance()

    # --------------------------------------------------------
    # (Local & MPS methods unchanged – omitted for brevity)
    # --------------------------------------------------------

    # ↓↓↓ full HTTPS-validated API helper ↓↓↓
    def _transcribe_with_api(
        self,
        file_path: str,
        language: str,
        api_key: Optional[str],
        *,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise ValueError("OpenAI API transcription requires an API key")

        base_url = base_url or "https://api.openai.com/v1"
        if not base_url.startswith("https://"):
            raise ValueError("API URL must use HTTPS for security")

        try:
            client = OpenAI(api_key=api_key, base_url=base_url)
            with open(file_path, "rb") as f:
                lang = language_to_iso(language)
                rsp = client.audio.transcriptions.create(
                    model="whisper-1", file=f, language=lang
                )
            if not rsp or not rsp.text:
                raise ValueError("OpenAI API returned empty response")
            return {"text": rsp.text, "method": "api"}
        except Exception as exc:
            logger.error("Whisper API error: %s", exc, exc_info=True)
            raise RuntimeError(f"OpenAI Whisper API transcription failed: {exc}") from exc
