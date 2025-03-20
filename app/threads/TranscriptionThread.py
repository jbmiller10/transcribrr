from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Optional, Union, Dict, Any
import os
import time
import logging
import concurrent.futures
from app.utils import language_to_iso
from app.services.transcription_service import TranscriptionService, ModelManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
                files_are_chunks: bool = False, 
                *args, **kwargs):
        """
        Initialize the transcription thread.
        
        Args:
            file_path: Path to audio file or list of paths for chunked files
            transcription_quality: Model ID for transcription
            speaker_detection_enabled: Whether to enable speaker detection
            hf_auth_key: HuggingFace authentication key
            language: Language of the audio
            transcription_method: Transcription method ("local" or "api")
            openai_api_key: OpenAI API key for API transcription
            files_are_chunks: Whether file_path contains chunks to be processed
        """
        super().__init__(*args, **kwargs)
        # If file_path is a list, it contains multiple chunks to process
        self.file_path = file_path
        self.files_are_chunks = files_are_chunks
        self.transcription_quality = transcription_quality
        self.speaker_detection_enabled = speaker_detection_enabled
        self.transcription_method = transcription_method
        self.hf_auth_key = hf_auth_key
        self.openai_api_key = openai_api_key
        self.language = language
        
        # Initialize the transcription service
        self.transcription_service = TranscriptionService()
        
        # Check if we're dealing with a single file or multiple chunks
        if isinstance(file_path, list):
            # We have multiple chunks
            for path in file_path:
                if not os.path.exists(path):
                    self.error.emit(f"Audio file not found: {path}")
                    return
                
                # Check each file size
                file_size_mb = os.path.getsize(path) / (1024 * 1024)  # Convert to MB
                if file_size_mb > 300:  # Limit to 300MB
                    self.error.emit(f"File size too large: {file_size_mb:.1f}MB. Maximum allowed is 300MB.")
                    return
        else:
            # Single file
            if not os.path.exists(file_path):
                self.error.emit(f"Audio file not found: {file_path}")
                return

            # Check file size to prevent processing extremely large files
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)  # Convert to MB
            if file_size_mb > 300:  # Limit to 300MB
                self.error.emit(f"File size too large: {file_size_mb:.1f}MB. Maximum allowed is 300MB.")
                return

    def run(self):
        """Execute the transcription thread."""
        try:
            start_time = time.time()
            
            # Check if we're processing a list of files (chunks) or a single file
            if isinstance(self.file_path, list):
                self.update_progress.emit(f'Processing {len(self.file_path)} audio chunks...')
                self.process_chunked_files()
            else:
                # Process single file (existing implementation)
                # Check if file exists
                if not os.path.exists(self.file_path):
                    raise FileNotFoundError(f"Audio file not found: {self.file_path}")

                self.update_progress.emit('Transcription started...')
                transcript = self.process_single_file(self.file_path, start_time)
                self.completed.emit(transcript)
                
            self.update_progress.emit('Transcription finished successfully.')
            
        except FileNotFoundError as e:
            self.error.emit(f"File error: {str(e)}")
            self.update_progress.emit('Transcription failed: File not found')
        except ValueError as e:
            self.error.emit(f"Configuration error: {str(e)}")
            self.update_progress.emit('Transcription failed: Configuration issue')
        except RuntimeError as e:
            self.error.emit(f"Processing error: {str(e)}")
            self.update_progress.emit('Transcription failed: Processing issue')
        except Exception as e:
            self.error.emit(f"Unexpected error: {str(e)}")
            self.update_progress.emit('Transcription failed: Unexpected error')
            logger.error(f"Transcription error: {e}", exc_info=True)
        finally:
            # Make sure to release memory, especially important for GPU
            self.update_progress.emit('Cleaning up resources...')
            ModelManager.instance().release_memory()
            
    def process_chunked_files(self):
        """Process multiple audio chunks and combine the results."""
        chunk_results = []
        
        # Log the number of chunks
        self.update_progress.emit(f'Starting transcription of {len(self.file_path)} audio chunks...')
        
        # For API transcription, we'll process chunks sequentially
        if self.transcription_method.lower() == 'api':
            for i, chunk_path in enumerate(self.file_path):
                self.update_progress.emit(f'Processing chunk {i+1}/{len(self.file_path)}...')
                chunk_transcript = self.process_single_file(chunk_path, time.time(), f"Chunk {i+1}")
                chunk_results.append(chunk_transcript)
        else:
            # For local transcription, we can use multithreading
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Start processing all chunks
                futures = []
                for i, chunk_path in enumerate(self.file_path):
                    self.update_progress.emit(f'Queuing chunk {i+1}/{len(self.file_path)}...')
                    future = executor.submit(
                        self.process_single_file_for_multiprocessing,
                        chunk_path,
                        time.time(),
                        f"Chunk {i+1}"
                    )
                    futures.append(future)
                
                # Collect results as they complete
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    try:
                        chunk_transcript = future.result()
                        self.update_progress.emit(f'Finished processing chunk {i+1}/{len(self.file_path)}')
                        chunk_results.append(chunk_transcript)
                    except Exception as e:
                        self.update_progress.emit(f'Error processing chunk: {str(e)}')
                        chunk_results.append(f"[Transcription error in chunk: {str(e)}]")
        
        # Combine all chunk results
        combined_transcript = "\n\n".join(chunk_results)
        self.update_progress.emit('All chunks processed. Combining results...')
        
        # Return the combined transcript
        self.completed.emit(combined_transcript)
        
    def process_single_file_for_multiprocessing(self, 
                                               file_path: str, 
                                               start_time: float, 
                                               chunk_label: str = "") -> str:
        """
        Process a single audio file for use with multithreading.
        This version doesn't use signals since they're not thread-safe across processes.
        
        Args:
            file_path: Path to the audio file
            start_time: Start time for timing
            chunk_label: Label for the chunk
            
        Returns:
            Transcript text
        """
        try:
            # Note: we can't use self.update_progress.emit here as it's not thread-safe
            result = self.transcription_service.transcribe_file(
                file_path=file_path,
                model_id=self.transcription_quality,
                language=self.language,
                method=self.transcription_method,
                openai_api_key=self.openai_api_key,
                hf_auth_key=self.hf_auth_key,
                speaker_detection=False  # Disable for chunks
            )
            
            if not result or not result.get('text'):
                return f"{chunk_label}: [No transcription produced]"
                
            return result['text']
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return f"{chunk_label}: [Error: {str(e)}]"
    
    def process_single_file(self, 
                           file_path: str, 
                           start_time: float, 
                           chunk_label: str = "") -> str:
        """
        Process a single audio file with the configured transcription method.
        
        Args:
            file_path: Path to the audio file
            start_time: Start time for timing
            chunk_label: Label for the chunk
            
        Returns:
            Transcript text
        """
        # Log device information
        if self.transcription_method.lower() == 'local':
            import torch
            self.update_progress.emit(f'Using local transcription with model: {self.transcription_quality}')
            
            # Check if CUDA is available
            if torch.cuda.is_available():
                self.update_progress.emit('CUDA is available, using GPU acceleration.')
                # Check GPU memory
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)  # Convert to GB
                self.update_progress.emit(f'GPU memory: {gpu_memory:.2f}GB')
            else:
                device = "MPS" if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() else "CPU"
                self.update_progress.emit(f'CUDA not available, using {device} for transcription.')

        # Start transcription
        self.update_progress.emit(f'Processing audio file{" " + chunk_label if chunk_label else ""}...')
        
        # Use the transcription service
        result = self.transcription_service.transcribe_file(
            file_path=file_path,
            model_id=self.transcription_quality,
            language=self.language,
            method=self.transcription_method,
            openai_api_key=self.openai_api_key,
            hf_auth_key=self.hf_auth_key if self.speaker_detection_enabled else None,
            speaker_detection=self.speaker_detection_enabled
        )
        
        # Calculate and log the elapsed time
        end_time = time.time()
        runtime = end_time - start_time
        
        if self.speaker_detection_enabled and 'formatted_text' in result:
            self.update_progress.emit(f"Transcription with speaker detection completed in {runtime:.2f} seconds.")
            return result['formatted_text']
        else:
            self.update_progress.emit(f"Transcription completed in {runtime:.2f} seconds.")
            return result.get('text', '')