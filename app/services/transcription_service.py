from ..utils import language_to_iso
from openai import OpenAI
import os
import torch
import logging
import warnings
from typing import Optional, List, Dict, Any, Union, Tuple, Callable
try:
    from transformers import (  # type: ignore
        AutoModelForSpeechSeq2Seq,
        AutoProcessor,
        pipeline,
    )
except Exception:  # transformers may be excluded from packaged builds
    AutoModelForSpeechSeq2Seq = None  # type: ignore
    AutoProcessor = None  # type: ignore
    pipeline = None  # type: ignore

# Filter torchaudio warning about set_audio_backend
warnings.filterwarnings(
    "ignore", message="torchaudio._backend.set_audio_backend has been deprecated"
)


# Configure logging
logger = logging.getLogger("transcribrr")


def _torch_mps_available() -> bool:
    """Return True if torch backends.mps reports availability.

    This helper fetches the current torch module from sys.modules to avoid
    cross-test interference where a previous test may have replaced the
    module object after this file was imported.
    """
    try:
        import sys  # local import to avoid global side effects

        t = sys.modules.get("torch", torch)
        backends = getattr(t, "backends", None)
        mps = getattr(backends, "mps", None)
        is_avail = getattr(mps, "is_available", None)
        return bool(is_avail()) if callable(is_avail) else False
    except Exception:
        return False


def _torch_cuda_available() -> bool:
    """Return True if torch.cuda reports availability (robust to stubs)."""
    try:
        import sys

        t = sys.modules.get("torch", torch)
        cuda = getattr(t, "cuda", None)
        is_avail = getattr(cuda, "is_available", None)
        return bool(is_avail()) if callable(is_avail) else False
    except Exception:
        return False


class ModelManager:
    """Manage ML models for transcription."""

    _instance = None

    @classmethod
    def instance(cls) -> "ModelManager":
        """Return singleton ModelManager."""
        if cls._instance is None:
            cls._instance = ModelManager()
        return cls._instance

    def __init__(self):
        """Init ModelManager."""
        self._models: Dict[str, Any] = {}  # Cache for loaded models
        self._processors: Dict[str, Any] = {}  # Cache for loaded processors

        # Read config to get hardware acceleration setting
        from app.utils import ConfigManager

        config_manager = ConfigManager.instance()
        hw_accel_enabled = config_manager.get(
            "hardware_acceleration_enabled", True)

        # Track current device
        self.device = self._get_optimal_device(hw_accel_enabled)
        logger.info(f"ModelManager initialized with device: {self.device}")

    def _get_optimal_device(self, hw_acceleration_enabled: bool = True) -> str:
        """Return optimal device string."""
        if not hw_acceleration_enabled:
            logger.info(
                "Hardware acceleration disabled in settings. Using CPU.")
            return "cpu"

        if torch.cuda.is_available():
            # Check available GPU memory before setting device to cuda
            free_memory = self._get_free_gpu_memory()
            if free_memory > 2.0:  # If at least 2GB is available
                logger.info("CUDA device selected for acceleration")
                return "cuda"
            else:
                logger.warning(
                    f"Insufficient GPU memory. Available: {free_memory:.2f}GB. Using CPU instead."
                )
                return "cpu"
        elif torch.backends.mps.is_available():
            logger.info("MPS device selected for acceleration (Apple Silicon)")
            return "mps"
        else:
            logger.info("No hardware acceleration available. Using CPU.")
            return "cpu"

    def _get_free_gpu_memory(self) -> float:
        """Get free GPU memory in GB."""
        try:
            if torch.cuda.is_available():
                # This is an approximate way to get free memory
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (
                    1024**3
                )  # Convert to GB
                allocated = torch.cuda.memory_allocated(
                    0) / (1024**3)  # Convert to GB
                return gpu_memory - allocated
            return 0.0
        except Exception as e:
            logger.warning(f"Error checking GPU memory: {e}")
            return 0.0

    def get_model(self, model_id: str) -> Any:
        """
        Get a model, loading it if not already loaded.

        Args:
            model_id: The identifier of the model to load

        Returns:
            The loaded model
        """
        if model_id not in self._models:
            logger.info(f"Loading model: {model_id}")
            self._models[model_id] = self._load_model(model_id)
        return self._models[model_id]

    def get_processor(self, model_id: str) -> Any:
        """
        Get a processor for a model, loading it if not already loaded.

        Args:
            model_id: The identifier of the model processor to load

        Returns:
            The loaded processor
        """
        if AutoProcessor is None:
            raise RuntimeError(
                "Local transcription requires 'transformers'. This build doesn't include it."
            )
        if model_id not in self._processors:
            logger.info(f"Loading processor: {model_id}")
            self._processors[model_id] = AutoProcessor.from_pretrained(
                model_id)
        return self._processors[model_id]

    def _load_model(self, model_id: str) -> Any:
        """
        Load a model from the transformers library.

        Args:
            model_id: The identifier of the model to load

        Returns:
            The loaded model
        """
        if AutoModelForSpeechSeq2Seq is None:
            raise RuntimeError(
                "Local transcription requires 'transformers'. This build doesn't include it."
            )
        try:
            model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if self.device != "cpu" else torch.float32,
                low_cpu_mem_usage=True,
                use_safetensors=True,
            )
            model.to(self.device)
            return model
        except Exception as e:
            logger.error(f"Error loading model {model_id}: {e}")
            raise RuntimeError(f"Failed to load model {model_id}: {e}")

    def clear_cache(self, model_id: Optional[str] = None) -> None:
        """
        Clear model cache to free memory.

        Args:
            model_id: Specific model to clear, or all if None
        """
        if model_id:
            if model_id in self._models:
                del self._models[model_id]
                logger.info(f"Cleared model from cache: {model_id}")
            if model_id in self._processors:
                del self._processors[model_id]
                logger.info(f"Cleared processor from cache: {model_id}")
        else:
            self._models.clear()
            self._processors.clear()
            torch.cuda.empty_cache()
            logger.info("Cleared all models from cache")

    def create_pipeline(
        self, model_id: str, language: str = "english", chunk_length_s: int = 30
    ) -> Any:
        """
        Create a transcription pipeline using a cached model.

        Args:
            model_id: Model identifier
            language: Language for transcription
            chunk_length_s: Length of chunks in seconds

        Returns:
            A transcription pipeline
        """
        # Get or load the model and processor
        model = self.get_model(model_id)
        processor = self.get_processor(model_id)

        if pipeline is None:
            raise RuntimeError(
                "Local transcription requires 'transformers'. This build doesn't include it."
            )
        # Create pipeline
        pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            torch_dtype=torch.float16 if self.device != "cpu" else torch.float32,
            chunk_length_s=chunk_length_s,
            batch_size=8,
            return_timestamps=True,
            device=self.device,
            model_kwargs={"use_flash_attention_2": self.device == "cuda"},
            generate_kwargs={"language": language.lower()},
        )

        return pipe

    def release_memory(self) -> None:
        """Release memory by clearing caches and running garbage collection."""
        self.clear_cache()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        import gc

        gc.collect()
        logger.info("Released memory and ran garbage collection")


class TranscriptionService:
    """Service for transcribing audio files using various methods."""

    def __init__(self):
        """Initialize the transcription service."""
        self.model_manager = ModelManager.instance()

    def transcribe_file(
        self,
        file_path: str,
        model_id: str,
        language: str = "english",
        method: str = "local",
        openai_api_key: Optional[str] = None,
        hf_auth_key: Optional[str] = None,
        speaker_detection: bool = False,
        hardware_acceleration_enabled: bool = True,
        *,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        cancel_cb: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """
        Transcribe an audio file using the specified method.

        Args:
            file_path: Path to the audio file
            model_id: Model identifier for local transcription
            language: Language of the audio
            method: Transcription method ("local" or "api")
            openai_api_key: OpenAI API key for API transcription
            hf_auth_key: HuggingFace auth key for speaker detection
            speaker_detection: Whether to enable speaker detection
            hardware_acceleration_enabled: Whether to enable hardware acceleration

        Returns:
            Dictionary with transcription results
        """
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        # Choose transcription method - normalize to lowercase for consistent comparison
        method_norm = method.lower().strip()

        if method_norm == "api":
            # Speaker detection is not compatible with API method, log a warning if it was requested
            if speaker_detection:
                logger.warning(
                    "Speaker detection requested but not available with API method"
                )

            logger.info(
                f"Using API method for transcription of {os.path.basename(file_path)}"
            )
            # If file is larger than API limit, use chunked flow
            try:
                from app.constants import OPENAI_WHISPER_API_LIMIT_MB
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                if size_mb > OPENAI_WHISPER_API_LIMIT_MB:
                    logger.info(
                        f"File {os.path.basename(file_path)} is {size_mb:.1f}MB (> {OPENAI_WHISPER_API_LIMIT_MB}MB). Using chunked API transcription."
                    )
                    return self._transcribe_with_api_chunked(
                        file_path,
                        language,
                        openai_api_key,
                        limit_mb=OPENAI_WHISPER_API_LIMIT_MB,
                        progress_cb=progress_cb,
                        cancel_cb=cancel_cb,
                    )
            except Exception as e:
                logger.warning(f"Size check failed, proceeding without chunking: {e}")

            return self._transcribe_with_api(file_path, language, openai_api_key)

        # For local method, decide on hardware acceleration path
        is_mps_device = (
            hardware_acceleration_enabled
            and _torch_mps_available()
            and not _torch_cuda_available()
        )

        # Special case: MPS device with hardware acceleration and speaker detection
        # MPS and speaker detection don't work together, so we need to warn and choose a path
        if is_mps_device and speaker_detection:
            logger.warning(
                "Speaker detection is not compatible with MPS acceleration. Prioritizing your choice..."
            )

            # If user has explicitly enabled speaker detection despite having hardware acceleration,
            # we'll assume they prioritize speaker detection over hardware acceleration
            logger.info("Using CPU transcription to support speaker detection")
            return self._transcribe_locally(
                file_path, model_id, language, speaker_detection, hf_auth_key
            )

        # If MPS is available and hardware acceleration is enabled, use MPS path
        elif is_mps_device:
            logger.info(
                f"Using MPS-optimized method for transcription of {os.path.basename(file_path)}"
            )
            return self._transcribe_with_mps(file_path, model_id, language)

        # Otherwise use standard path with CUDA or CPU based on availability and settings
        else:
            device = self.model_manager._get_optimal_device(
                hardware_acceleration_enabled
            )
            logger.info(
                f"Using standard transcription with {device} for {os.path.basename(file_path)}"
            )
            return self._transcribe_locally(
                file_path, model_id, language, speaker_detection, hf_auth_key
            )

    def _transcribe_locally(
        self,
        file_path: str,
        model_id: str,
        language: str,
        speaker_detection: bool,
        hf_auth_key: Optional[str],
    ) -> Dict[str, Any]:
        """
        Transcribe using local models.

        Args:
            file_path: Path to the audio file
            model_id: Model identifier
            language: Language of the audio
            speaker_detection: Whether to enable speaker detection
            hf_auth_key: HuggingFace auth key for speaker detection

        Returns:
            Dictionary with transcription results
        """
        try:
            # Create pipeline using model manager
            pipe = self.model_manager.create_pipeline(model_id, language)

            # Process the file
            result = pipe(file_path)

            # If speaker detection is enabled and we have a HF key
            if speaker_detection and hf_auth_key:
                try:
                    result_with_speakers: Dict[str, Any] = self._add_speaker_detection(
                        file_path, result, hf_auth_key
                    )
                    return result_with_speakers
                except Exception as e:
                    logger.error(
                        f"Speaker detection failed, returning normal transcript: {e}"
                    )
                    # Ensure we return a dict[str, Any] type
                    return dict(result) if isinstance(result, dict) else {"text": str(result)}

            # Return properly typed dictionary result
            return dict(result) if isinstance(result, dict) else {"text": str(result)}

        except Exception as e:
            logger.error(f"Local transcription error: {e}")
            raise RuntimeError(f"Failed to transcribe audio: {e}")

    def _transcribe_with_mps(
        self, file_path: str, model_id: str, language: str
    ) -> Dict[str, Any]:
        """
        Transcribe using MPS-optimized approach for Apple Silicon.
        This implementation uses the approach from the mac_support branch.

        Args:
            file_path: Path to the audio file
            model_id: Model identifier
            language: Language of the audio

        Returns:
            Dictionary with transcription results
        """
        try:
            # SpeechToTextPipeline MPS implementation
            if _torch_mps_available():
                logger.info(
                    f"Using MPS device for transcription of {os.path.basename(file_path)}"
                )

                # Initialize model
                model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    model_id,
                    torch_dtype=torch.float16,
                    low_cpu_mem_usage=False,
                    use_safetensors=True,
                )

                # Set device to MPS
                device = "mps"
                model.to(device)

                # Load processor
                processor = AutoProcessor.from_pretrained(model_id)

                # Create pipeline
                pipe = pipeline(
                    "automatic-speech-recognition",
                    model=model,
                    tokenizer=processor.tokenizer,
                    feature_extractor=processor.feature_extractor,
                    torch_dtype=torch.float16,
                    chunk_length_s=15,
                    max_new_tokens=128,
                    batch_size=8,
                    return_timestamps=True,
                    device=device,
                    generate_kwargs={"language": language.lower()},
                )

                # Transcribe
                logger.info("Transcribing audio with MPS...")
                result = pipe(file_path)

                # Return result in standard format as a properly typed dict
                return dict(result) if isinstance(result, dict) else {"text": str(result)}

            else:
                # Fall back to regular transcription if MPS not available
                logger.warning(
                    "MPS requested but not available, falling back to standard transcription"
                )
                return self._transcribe_locally(
                    file_path, model_id, language, False, None
                )

        except Exception as e:
            logger.error(f"MPS transcription error: {e}", exc_info=True)
            raise RuntimeError(f"MPS transcription failed: {e}")

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
            raise RuntimeError(
                f"OpenAI Whisper API transcription failed: {exc}"
            ) from exc

    def _transcribe_with_api_chunked(
        self,
        file_path: str,
        language: str,
        api_key: Optional[str],
        *,
        limit_mb: int,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        cancel_cb: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Transcribe a large file by chunking and combining results.

        Splits the file into approximately even chunks based on size limit,
        transcribes each chunk via the OpenAI API, and concatenates text.
        """
        if not api_key:
            raise ValueError("OpenAI API transcription requires an API key")

        # Lazy import heavy dependency
        try:
            from pydub import AudioSegment  # type: ignore
        except Exception as e:  # pragma: no cover - exercised via integration
            raise RuntimeError(f"Chunked transcription requires pydub: {e}") from e

        import tempfile

        audio = AudioSegment.from_file(file_path)
        duration_ms = len(audio)
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        # at least 2 chunks if exceeding limit
        num_chunks = max(2, int(file_size_mb / float(limit_mb)) + 1)
        chunk_duration = max(1, duration_ms // num_chunks)

        pieces: List[str] = []

        for i in range(num_chunks):
            if cancel_cb and cancel_cb():
                if progress_cb:
                    progress_cb(0, "Chunked transcription cancelled.")
                return {"text": "[Cancelled]", "method": "api"}

            start_ms = i * chunk_duration
            end_ms = duration_ms if i == num_chunks - 1 else (i + 1) * chunk_duration
            segment = audio[start_ms:end_ms]

            # Status update
            if progress_cb:
                pct = int(((i) / num_chunks) * 100)
                progress_cb(pct, f"Transcribing chunk {i+1}/{num_chunks}...")

            # Export to a temp WAV and call the API
            fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix=f"temp_chunk_{i+1}_")
            os.close(fd)
            try:
                segment.export(tmp_path, format="wav")
                result = self._transcribe_with_api(tmp_path, language, api_key)
            finally:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            pieces.append(result.get("text", ""))

            if progress_cb:
                pct = int(((i + 1) / num_chunks) * 100)
                progress_cb(pct, f"Progress: {pct}% ({i+1}/{num_chunks})")

        combined = " ".join(pieces).strip()
        return {"text": combined, "method": "api"}

    def _add_speaker_detection(
        self, file_path: str, result: Dict[str, Any], hf_auth_key: str
    ) -> Dict[str, Any]:
        """
        Add speaker detection to transcription results.

        Args:
            file_path: Path to the audio file
            result: Base transcription result
            hf_auth_key: HuggingFace authentication key

        Returns:
            Enhanced transcription with speaker detection
        """
        from pyannote.audio import Pipeline

        try:
            # Initialize diarization pipeline
            logger.info("Initializing speaker diarization pipeline")
            diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization", use_auth_token=hf_auth_key
            )

            # Process the audio file
            logger.info("Running speaker diarization")
            diarization = diarization_pipeline(file_path)

            # Extract speaker segments
            segments = []
            for segment, track, label in diarization.itertracks(yield_label=True):
                segments.append(
                    {
                        "segment": {"start": segment.start, "end": segment.end},
                        "track": track,
                        "label": label,
                    }
                )

            # Combine segments with the same speaker
            speaker_segments = []
            if not segments:
                return result  # No segments found

            prev_segment = segments[0]
            for i in range(1, len(segments)):
                cur_segment = segments[i]

                # Check if the speaker has changed
                if cur_segment["label"] != prev_segment["label"]:
                    # Add the previous segment
                    speaker_segments.append(
                        {
                            "segment": {
                                "start": prev_segment["segment"]["start"],
                                "end": cur_segment["segment"]["start"],
                            },
                            "speaker": prev_segment["label"],
                        }
                    )
                    prev_segment = cur_segment

            # Add the last segment
            speaker_segments.append(
                {
                    "segment": {
                        "start": prev_segment["segment"]["start"],
                        "end": segments[-1]["segment"]["end"],
                    },
                    "speaker": prev_segment["label"],
                }
            )

            # Align with transcription chunks
            transcript_chunks = result.get("chunks", [])
            if not transcript_chunks:
                # Create chunks from the main text
                transcript_chunks = [
                    {"text": result.get("text", ""), "timestamp": (0, 0)}
                ]

            # Assign speakers to transcript chunks
            for chunk in transcript_chunks:
                # Find the speaker segment that contains this chunk
                chunk_start = chunk.get("timestamp", (0, 0))[0]
                chunk_end = chunk.get("timestamp", (0, 0))[1]

                for speaker_segment in speaker_segments:
                    segment_start = speaker_segment["segment"]["start"]
                    segment_end = speaker_segment["segment"]["end"]

                    # Check if chunk is within this speaker segment
                    if (chunk_start >= segment_start and chunk_start < segment_end) or (
                        chunk_end > segment_start and chunk_end <= segment_end
                    ):
                        chunk["speaker"] = speaker_segment["speaker"]
                        break
                else:
                    chunk["speaker"] = "Unknown"

            # Format the final result
            enhanced_result = result.copy()
            enhanced_result["chunks"] = transcript_chunks
            enhanced_result["has_speaker_detection"] = True

            # Create a formatted text with speaker labels
            formatted_text = ""
            for chunk in transcript_chunks:
                speaker = chunk.get("speaker", "Unknown")
                text = chunk.get("text", "").strip()
                if text:
                    formatted_text += f"{speaker}: {text}\n\n"

            enhanced_result["formatted_text"] = formatted_text

            return enhanced_result

        except Exception as e:
            logger.error(f"Speaker detection error: {e}")
            # Return original result if speaker detection fails
            return result
