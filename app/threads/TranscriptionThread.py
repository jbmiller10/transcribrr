from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Optional
import os
import time
import logging
from threading import Lock # Import Lock
from app.services.transcription_service import TranscriptionService, ModelManager

# Configure logging
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Configured in main
logger = logging.getLogger('transcribrr')


class TranscriptionThread(QThread):
    """Transcription thread."""
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self,
                file_path: str,
                transcription_quality: str,
                speaker_detection_enabled: bool,
                hf_auth_key: Optional[str],
                language: str = 'English',
                transcription_method: str = 'local',
                openai_api_key: Optional[str] = None,
                hardware_acceleration_enabled: bool = True,
                *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path

        # Store parameters explicitly
        self.transcription_quality = transcription_quality
        self.speaker_detection_enabled = speaker_detection_enabled
        self.transcription_method = transcription_method
        self.hf_auth_key = hf_auth_key
        self.openai_api_key = openai_api_key
        self.language = language
        self.hardware_acceleration_enabled = hardware_acceleration_enabled
        
        # API file size limit in MB
        self.api_file_size_limit = 25  # OpenAI's limit

        # Cancellation flag
        self._is_canceled = False
        self._lock = Lock() # For thread-safe access to the flag

        # Initialize the transcription service
        self.transcription_service = TranscriptionService()
        
        # Temporary files that may be created during processing
        self.temp_files = []

        # Initial validation
        try:
            self._validate_file(self.file_path)
        except (FileNotFoundError, ValueError) as e:
             # Emit error immediately if validation fails in constructor
             self.error.emit(str(e))
             self._is_canceled = True # Prevent run() from executing


    def _validate_file(self, file_path: str):
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
        with self._lock:
            if not self._is_canceled:
                logger.info("Cancellation requested for transcription thread.")
                self._is_canceled = True
                self.requestInterruption()  # Use QThread's built-in interruption
                # Note: Cannot easily interrupt underlying model inference once started.
                # Cancellation primarily prevents starting new steps or chunks.

    def is_canceled(self):
        # Check both the custom flag and QThread's interruption status
        with self._lock:
            return self._is_canceled or self.isInterruptionRequested()

    def run(self):
        if self.is_canceled():
             self.update_progress.emit('Transcription cancelled before starting.')
             return # Exit if validation failed or cancelled early

        start_time = time.time()
        transcript = ""

        try:
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
            try:
                # Always attempt to release resources regardless of cancellation state
                self.update_progress.emit('Cleaning up transcription resources...')
                ModelManager.instance().release_memory()
            except Exception as cleanup_error:
                logger.error(f"Error during transcription resource cleanup: {cleanup_error}", exc_info=True)
            logger.info("Transcription thread finished execution.")

    def _create_temporary_chunks(self, file_path: str) -> List[str]:
        """Create temporary chunks for API-based transcription of large files."""
        from pydub import AudioSegment
        import tempfile
        
        self.update_progress.emit("File exceeds API size limit. Creating temporary chunks...")
        
        # Load the audio file
        try:
            audio = AudioSegment.from_file(file_path)
            duration_ms = len(audio)
            
            # Calculate appropriate chunk size based on file size
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            num_chunks = max(2, int(file_size_mb / self.api_file_size_limit) + 1)
            chunk_duration_ms = duration_ms // num_chunks
            
            logger.info(f"Creating {num_chunks} temporary chunks for API transcription")
            self.update_progress.emit(f"Creating {num_chunks} temporary chunks for API transcription...")
            
            # Create temporary files for the chunks
            temp_files = []
            
            for i in range(num_chunks):
                if self.is_canceled():
                    # Clean up any temporary files already created
                    self._cleanup_temp_files()
                    return []
                
                start_ms = i * chunk_duration_ms
                end_ms = min((i + 1) * chunk_duration_ms, duration_ms)
                
                # Create a chunk
                chunk = audio[start_ms:end_ms]
                
                # Create a temporary file
                fd, temp_path = tempfile.mkstemp(suffix='.wav', prefix=f'temp_chunk_{i+1}_')
                os.close(fd)  # Close file descriptor, we'll use the path
                
                # Export chunk to the temporary file
                self.update_progress.emit(f"Exporting temporary chunk {i+1}/{num_chunks}...")
                chunk.export(temp_path, format="wav")
                
                # Track the temporary file
                temp_files.append(temp_path)
                self.temp_files.append(temp_path)
            
            self.update_progress.emit(f"Created {len(temp_files)} temporary chunks.")
            return temp_files
            
        except Exception as e:
            logger.error(f"Error creating temporary chunks: {e}", exc_info=True)
            self.error.emit(f"Failed to create temporary chunks: {e}")
            # Clean up any temporary files that were created
            self._cleanup_temp_files()
            return []
    
    def _cleanup_temp_files(self):
        """Delete any temporary files created during processing."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.debug(f"Removed temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_file}: {e}")
        
        # Clear the list after cleanup
        self.temp_files = []
        
    def _process_temporary_chunks(self, temp_files: List[str], start_time: float) -> str:
        """Process temporary chunks for API transcription and combine results."""
        if not temp_files:
            return "[No chunks to process]"
            
        chunk_results = []
        total_chunks = len(temp_files)
        
        try:
            for i, chunk_path in enumerate(temp_files):
                if self.is_canceled():
                    logger.info(f"Temporary chunk processing cancelled at chunk {i+1}/{total_chunks}")
                    return "[Transcription Cancelled]"
                    
                self.update_progress.emit(f"Transcribing temporary chunk {i+1}/{total_chunks}...")
                
                # Process this chunk with API method
                result = self.transcription_service._transcribe_with_api(
                    file_path=chunk_path,
                    language=self.language,
                    api_key=self.openai_api_key
                )
                
                # Get the transcription text
                if 'text' in result:
                    chunk_results.append(result['text'])
                else:
                    chunk_results.append(f"[Error in Chunk {i+1}]")
                
                # Update progress percentage
                progress_pct = int((i + 1) / total_chunks * 100)
                self.update_progress.emit(f"Progress: {progress_pct}% ({i+1}/{total_chunks} chunks processed)")
            
            # Combine results
            combined_transcript = " ".join(chunk_results)
            self.update_progress.emit("Combining temporary chunk transcriptions...")
            
            return combined_transcript
            
        except Exception as e:
            logger.error(f"Error processing temporary chunks: {e}", exc_info=True)
            return "[Error processing chunks]"
        finally:
            # Always clean up the temporary files
            self._cleanup_temp_files()

    def process_single_file(self,
                           file_path: str,
                           start_time: float,
                           chunk_label: str = "") -> str:
        if self.is_canceled(): return "[Cancelled]"

        task_label = f"{os.path.basename(file_path)}"
        logger.info(f"Starting processing for: {task_label}")
        self.update_progress.emit(f'Processing: {task_label}...')

        # Check if using API method and if file exceeds API size limit
        method = self.transcription_method.lower()
        if method == 'api':
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > self.api_file_size_limit:
                self.update_progress.emit(f'File size ({file_size_mb:.1f}MB) exceeds API limit ({self.api_file_size_limit}MB)')
                
                # Disable speaker detection for chunked API processing
                original_speaker_detection = self.speaker_detection_enabled
                if original_speaker_detection:
                    self.update_progress.emit('Speaker detection is disabled for chunked API processing')
                
                # Create temporary chunks for processing
                temp_chunks = self._create_temporary_chunks(file_path)
                if not temp_chunks:
                    return "[Failed to create temporary chunks for API processing]"
                
                # Process the temporary chunks
                result = self._process_temporary_chunks(temp_chunks, time.time())
                
                end_time = time.time()
                runtime = end_time - start_time
                logger.info(f"Finished temporary chunk processing in {runtime:.2f}s")
                self.update_progress.emit(f"Finished API transcription with temporary chunks in {runtime:.2f}s")
                
                return result
            else:
                self.update_progress.emit('Using OpenAI API for transcription')
        elif method == 'local':
            device = ModelManager.instance().device
            self.update_progress.emit(f'Using device: {device}')
            if device == 'cuda':
                try:
                    gpu_mem = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                    self.update_progress.emit(f'GPU Memory: {gpu_mem:.2f}GB')
                except Exception:
                    pass # Ignore if props fail

        # Check before the potentially long call
        if self.is_canceled(): return "[Cancelled]"

        try:
            # Process file with normal transcription
            result = self.transcription_service.transcribe_file(
                file_path=file_path,
                model_id=self.transcription_quality,
                language=self.language,
                method=self.transcription_method,
                openai_api_key=self.openai_api_key,
                hf_auth_key=self.hf_auth_key if self.speaker_detection_enabled else None,
                speaker_detection=self.speaker_detection_enabled,
                hardware_acceleration_enabled=self.hardware_acceleration_enabled
            )

            # Process Result
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
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}", exc_info=True)
            self.error.emit(f"Error processing file: {e}")
            return f"[Error: {str(e)}]"