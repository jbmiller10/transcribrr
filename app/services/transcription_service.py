import os
import torch
import logging
import warnings
from typing import Optional, List, Dict, Any, Union, Tuple
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
from pyannote.audio import Pipeline

# Filter torchaudio warning about set_audio_backend
warnings.filterwarnings("ignore", message="torchaudio._backend.set_audio_backend has been deprecated")
from torchaudio import functional as F

import numpy as np
import requests
from openai import OpenAI
from ..utils import language_to_iso

# Configure logging
logger = logging.getLogger('transcribrr')


class ModelManager:
    """
    Manages loading and caching of machine learning models for transcription.
    Implements lazy loading to improve startup performance.
    """
    
    _instance = None
    
    @classmethod
    def instance(cls) -> 'ModelManager':
        """Get the singleton instance of ModelManager."""
        if cls._instance is None:
            cls._instance = ModelManager()
        return cls._instance
    
    def __init__(self):
        """Initialize the model manager with empty caches."""
        self._models: Dict[str, Any] = {}  # Cache for loaded models
        self._processors: Dict[str, Any] = {}  # Cache for loaded processors
        
        # Track current device
        self.device = self._get_optimal_device()
        logger.info(f"ModelManager initialized with device: {self.device}")
        
    def _get_optimal_device(self) -> str:
        """Determine the best available device for inference."""
        if torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            # Check available GPU memory before setting device to cuda
            free_memory = self._get_free_gpu_memory()
            if free_memory > 2.0:  # If at least 2GB is available
                return "cuda"
            else:
                logger.warning(f"Insufficient GPU memory. Available: {free_memory:.2f}GB. Using CPU instead.")
                return "cpu"
        else:
            return "cpu"
    
    def _get_free_gpu_memory(self) -> float:
        """Get free GPU memory in GB."""
        try:
            if torch.cuda.is_available():
                # This is an approximate way to get free memory
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)  # Convert to GB
                allocated = torch.cuda.memory_allocated(0) / (1024 ** 3)  # Convert to GB
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
        if model_id not in self._processors:
            logger.info(f"Loading processor: {model_id}")
            self._processors[model_id] = AutoProcessor.from_pretrained(model_id)
        return self._processors[model_id]
        
    def _load_model(self, model_id: str) -> Any:
        """
        Load a model from the transformers library.
        
        Args:
            model_id: The identifier of the model to load
            
        Returns:
            The loaded model
        """
        try:
            model = AutoModelForSpeechSeq2Seq.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if self.device != "cpu" else torch.float32,
                low_cpu_mem_usage=True,
                use_safetensors=True
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
            
    def create_pipeline(self, model_id: str, language: str = "english", 
                        chunk_length_s: int = 30) -> Any:
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
        
    def transcribe_file(self, 
                        file_path: str, 
                        model_id: str, 
                        language: str = "english",
                        method: str = "local",
                        openai_api_key: Optional[str] = None,
                        hf_auth_key: Optional[str] = None,
                        speaker_detection: bool = False) -> Dict[str, Any]:
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
            
        Returns:
            Dictionary with transcription results
        """
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
            
        # Choose transcription method - normalize to lowercase for consistent comparison
        method_norm = method.lower().strip()
        
        if method_norm == "api":
            logger.info(f"Using API method for transcription of {os.path.basename(file_path)}")
            return self._transcribe_with_api(file_path, language, openai_api_key)
        else:
            logger.info(f"Using local method for transcription of {os.path.basename(file_path)}")
            return self._transcribe_locally(file_path, model_id, language, 
                                          speaker_detection, hf_auth_key)
    
    def _transcribe_locally(self, 
                           file_path: str, 
                           model_id: str, 
                           language: str,
                           speaker_detection: bool,
                           hf_auth_key: Optional[str]) -> Dict[str, Any]:
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
                    return self._add_speaker_detection(file_path, result, hf_auth_key)
                except Exception as e:
                    logger.error(f"Speaker detection failed, returning normal transcript: {e}")
                    return result
            
            return result
            
        except Exception as e:
            logger.error(f"Local transcription error: {e}")
            raise RuntimeError(f"Failed to transcribe audio: {e}")
    
    def _transcribe_with_api(self, 
                            file_path: str, 
                            language: str,
                            api_key: Optional[str]) -> Dict[str, Any]:
        """
        Transcribe using OpenAI Whisper API.
        
        Args:
            file_path: Path to the audio file
            language: Language of the audio
            api_key: OpenAI API key
            
        Returns:
            Dictionary with transcription results
        """
        if not api_key:
            raise ValueError("OpenAI API transcription requires an API key")
            
        try:
            client = OpenAI(api_key=api_key)
            with open(file_path, 'rb') as audio_file:
                language_code = language_to_iso(language)
                logger.info(f"Sending file to OpenAI Whisper API (language: {language_code})")
                
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language_code
                )
                
                if not response or not response.text:
                    raise ValueError("OpenAI API returned empty response")
                    
                # Format response to match local transcription format
                return {
                    "text": response.text,
                    "method": "api"
                }
                
        except Exception as e:
            logger.error(f"OpenAI Whisper API error: {e}")
            raise RuntimeError(f"OpenAI Whisper API transcription failed: {e}")
    
    def _add_speaker_detection(self, 
                              file_path: str, 
                              result: Dict[str, Any],
                              hf_auth_key: str) -> Dict[str, Any]:
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
                "pyannote/speaker-diarization", 
                use_auth_token=hf_auth_key
            )
            
            # Process the audio file
            logger.info("Running speaker diarization")
            diarization = diarization_pipeline(file_path)
            
            # Extract speaker segments
            segments = []
            for segment, track, label in diarization.itertracks(yield_label=True):
                segments.append({
                    'segment': {
                        'start': segment.start,
                        'end': segment.end
                    },
                    'track': track,
                    'label': label
                })
                
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
                    speaker_segments.append({
                        "segment": {
                            "start": prev_segment["segment"]["start"],
                            "end": cur_segment["segment"]["start"]
                        },
                        "speaker": prev_segment["label"],
                    })
                    prev_segment = cur_segment
                    
            # Add the last segment
            speaker_segments.append({
                "segment": {
                    "start": prev_segment["segment"]["start"],
                    "end": segments[-1]["segment"]["end"]
                },
                "speaker": prev_segment["label"],
            })
            
            # Align with transcription chunks
            transcript_chunks = result.get("chunks", [])
            if not transcript_chunks:
                # Create chunks from the main text
                transcript_chunks = [{"text": result.get("text", ""), "timestamp": (0, 0)}]
                
            # Assign speakers to transcript chunks
            for chunk in transcript_chunks:
                # Find the speaker segment that contains this chunk
                chunk_start = chunk.get("timestamp", (0, 0))[0]
                chunk_end = chunk.get("timestamp", (0, 0))[1]
                
                for speaker_segment in speaker_segments:
                    segment_start = speaker_segment["segment"]["start"]
                    segment_end = speaker_segment["segment"]["end"]
                    
                    # Check if chunk is within this speaker segment
                    if (chunk_start >= segment_start and chunk_start < segment_end) or \
                       (chunk_end > segment_start and chunk_end <= segment_end):
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