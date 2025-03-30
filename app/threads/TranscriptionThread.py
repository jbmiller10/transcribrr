from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Optional, Union, Dict, Any
import os
import time
import logging
import concurrent.futures
from threading import Lock # Import Lock
from app.utils import language_to_iso
from app.services.transcription_service import TranscriptionService, ModelManager

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Configured in main
logger = logging.getLogger('transcribrr')


class TranscriptionThread(QThread):
    """Thread for handling audio transcription tasks."""
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self,
                file_path: Union[str, List[str]],
                transcription_quality: str,
                speaker_detection_enabled: bool,
                hf_auth_key: Optional[str],
                language: str = 'English',
                transcription_method: str = 'local',
                openai_api_key: Optional[str] = None,
                # files_are_chunks: bool = False, # Determined internally now
                *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        # Determine if input is chunks
        self.files_are_chunks = isinstance(file_path, list)

        # Store parameters explicitly
        self.transcription_quality = transcription_quality
        self.speaker_detection_enabled = speaker_detection_enabled
        self.transcription_method = transcription_method
        self.hf_auth_key = hf_auth_key
        self.openai_api_key = openai_api_key
        self.language = language

        # Cancellation flag
        self._is_canceled = False
        self._lock = Lock() # For thread-safe access to the flag

        # Initialize the transcription service (consider if it needs to be thread-local)
        # For now, assume ModelManager handles thread safety or models are used sequentially
        self.transcription_service = TranscriptionService()

        # Initial validation (moved here from run)
        try:
            if self.files_are_chunks:
                if not self.file_path: raise ValueError("Received empty list of chunks.")
                for path in self.file_path:
                    self._validate_file(path)
            else:
                self._validate_file(self.file_path)
        except (FileNotFoundError, ValueError) as e:
             # Emit error immediately if validation fails in constructor
             # Use QTimer to emit from the main thread's event loop if needed,
             # but emitting directly might be okay for constructor errors before start()
             self.error.emit(str(e))
             self._is_canceled = True # Prevent run() from executing


    def _validate_file(self, file_path: str):
        """Validate a single file path."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        # Check file size to prevent processing extremely large files
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        # Allow larger files if chunking occurs upstream (TranscodingThread)
        # Maybe check total size if it's a list? For now, check individual.
        MAX_SIZE = 500 # MB, adjust as needed
        if file_size_mb > MAX_SIZE:
            raise ValueError(f"File size too large: {file_size_mb:.1f}MB > {MAX_SIZE}MB limit ({os.path.basename(file_path)})")


    def cancel(self):
        """Request cancellation of the transcription process."""
        with self._lock:
            if not self._is_canceled:
                logger.info("Cancellation requested for transcription thread.")
                self._is_canceled = True
                # Note: Cannot easily interrupt underlying model inference once started.
                # Cancellation primarily prevents starting new steps or chunks.

    def is_canceled(self):
        """Check if cancellation has been requested."""
        with self._lock:
            return self._is_canceled

    def run(self):
        """Execute the transcription thread."""
        if self.is_canceled():
             self.update_progress.emit('Transcription cancelled before starting.')
             return # Exit if validation failed or cancelled early

        start_time = time.time()
        transcript = ""

        try:
            if self.files_are_chunks:
                self.update_progress.emit(f'Processing {len(self.file_path)} audio chunks...')
                transcript = self.process_chunked_files(start_time)
            else:
                self.update_progress.emit('Transcription started...')
                transcript = self.process_single_file(self.file_path, start_time)

            if self.is_canceled():
                self.update_progress.emit('Transcription cancelled.')
            else:
                self.completed.emit(transcript)
                self.update_progress.emit('Transcription finished successfully.')

        except FileNotFoundError as e:
            if not self.is_canceled(): self.error.emit(f"File error: {e}")
            self.update_progress.emit('Transcription failed: File not found')
        except ValueError as e:
             if not self.is_canceled(): self.error.emit(f"Configuration error: {e}")
             self.update_progress.emit('Transcription failed: Configuration issue')
        except RuntimeError as e:
            if not self.is_canceled(): self.error.emit(f"Processing error: {e}")
            self.update_progress.emit('Transcription failed: Processing issue')
        except Exception as e:
            if not self.is_canceled():
                self.error.emit(f"Unexpected error: {e}")
                logger.error(f"Transcription error: {e}", exc_info=True)
            self.update_progress.emit('Transcription failed: Unexpected error')
        finally:
            # Release memory if the thread wasn't cancelled mid-operation uncleanly
            if not self.is_canceled() or transcript: # Attempt cleanup even if cancelled late
                self.update_progress.emit('Cleaning up transcription resources...')
                ModelManager.instance().release_memory()
            logger.info("Transcription thread finished execution.")

    def process_chunked_files(self, start_time: float) -> str:
        """Process multiple audio chunks and combine the results."""
        chunk_results = [""] * len(self.file_path) # Pre-allocate for order
        total_chunks = len(self.file_path)
        self.update_progress.emit(f'Starting transcription of {total_chunks} chunks...')

        # --- Sequential processing for API or simplified local ---
        # Consider if parallel local processing is truly needed/stable.
        # Let's stick to sequential for now for stability.
        # If parallelism is desired, ThreadPoolExecutor is okay for I/O bound (API),
        # but ProcessPoolExecutor might be needed for CPU/GPU bound local tasks
        # to bypass GIL, adding complexity.

        for i, chunk_path in enumerate(self.file_path):
            if self.is_canceled():
                logger.info(f"Chunk processing cancelled at chunk {i+1}/{total_chunks}")
                return "[Transcription Cancelled]"

            self.update_progress.emit(f'Processing chunk {i+1}/{total_chunks}...')
            try:
                # Use the main process_single_file method
                chunk_transcript = self.process_single_file(chunk_path, time.time(), f"Chunk {i+1}")
                chunk_results[i] = chunk_transcript
            except Exception as e:
                logger.error(f"Error processing chunk {i+1} ({chunk_path}): {e}", exc_info=True)
                chunk_results[i] = f"[Error in Chunk {i+1}]"
                # Optionally emit an error signal here too, or just continue
                self.error.emit(f"Error processing chunk {i+1}: {e}")


        if self.is_canceled():
            return "[Transcription Cancelled]"

        # Combine results with clear separators
        combined_transcript = "\n\n--- End Chunk ---\n\n".join(filter(None, chunk_results)) # Filter out potential None results
        self.update_progress.emit('All chunks processed. Combined results.')
        return combined_transcript

    def process_single_file(self,
                           file_path: str,
                           start_time: float,
                           chunk_label: str = "") -> str:
        """Process a single audio file."""
        if self.is_canceled(): return "[Cancelled]"

        task_label = f"{os.path.basename(file_path)}{' (' + chunk_label + ')' if chunk_label else ''}"
        logger.info(f"Starting processing for: {task_label}")
        self.update_progress.emit(f'Processing: {task_label}...')

        # Check device for local method
        method = self.transcription_method.lower()
        if method == 'local':
            device = ModelManager.instance().device
            self.update_progress.emit(f'Using device: {device}')
            if device == 'cuda':
                 try:
                     gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                     self.update_progress.emit(f'GPU Memory: {gpu_mem:.2f}GB')
                 except Exception: pass # Ignore if props fail
        else:
            self.update_progress.emit(f'Using OpenAI API for transcription')

        # --- Call Transcription Service ---
        # Add a check before the potentially long call
        if self.is_canceled(): return "[Cancelled]"

        result = self.transcription_service.transcribe_file(
            file_path=file_path,
            model_id=self.transcription_quality,
            language=self.language,
            method=self.transcription_method,
            openai_api_key=self.openai_api_key,
            hf_auth_key=self.hf_auth_key if self.speaker_detection_enabled else None,
            speaker_detection=self.speaker_detection_enabled and not self.files_are_chunks # Disable speaker detect for individual chunks
        )

        # --- Process Result ---
        if self.is_canceled(): return "[Cancelled]"

        end_time = time.time()
        runtime = end_time - start_time
        logger.info(f"Finished processing {task_label} in {runtime:.2f}s")

        # Return formatted text if speaker detection was successful, otherwise plain text
        if self.speaker_detection_enabled and 'formatted_text' in result:
            self.update_progress.emit(f"Finished {task_label} with speakers in {runtime:.2f}s")
            return result['formatted_text']
        elif 'text' in result:
            self.update_progress.emit(f"Finished {task_label} in {runtime:.2f}s")
            return result['text']
        else:
            logger.warning(f"Transcription for {task_label} returned no text.")
            return "[No transcription generated]"