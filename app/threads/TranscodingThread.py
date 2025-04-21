from PyQt6.QtCore import QThread, pyqtSignal
from pydub import AudioSegment
import os
from moviepy.editor import VideoFileClip
import traceback
import math
import logging
from threading import Lock
from app.utils import is_video_file, is_audio_file

# Configure logging
logger = logging.getLogger('transcribrr')

class TranscodingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, file_path=None, target_format='mp3', chunk_duration=10, chunk_enabled=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_path = file_path
        self.target_format = target_format
        self.recordings_dir = 'Recordings'  # Directory for storing the output
        self.chunk_duration = chunk_duration  # Chunk duration in minutes
        self.chunk_enabled = chunk_enabled  # Whether to enable chunking
        
        # Cancellation support
        self._is_canceled = False
        self._lock = Lock()

    def cancel(self):
        with self._lock:
            if not self._is_canceled:
                logger.info("Cancellation requested for transcoding thread.")
                self._is_canceled = True
                # Note: Can't easily interrupt underlying transcoding operations
                # This will primarily prevent starting new operations
                
    def is_canceled(self):
        with self._lock:
            return self._is_canceled
            
    def run(self):
        temp_files = [] # Track temporary files for cleanup in case of cancellation
        try:
            if self.is_canceled():
                self.update_progress.emit('Transcoding cancelled before starting.')
                return
                
            if is_audio_file(self.file_path):
                self.update_progress.emit('Transcoding audio file...')
                self.transcode_audio(self.file_path, self.recordings_dir)
            elif is_video_file(self.file_path):
                self.update_progress.emit('Extracting audio from video file...')
                self.extract_audio_from_video(self.file_path, self.recordings_dir)
            else:
                raise ValueError("Unsupported file type for transcoding.")
        except Exception as e:
            if not self.is_canceled():
                error_message = f'Error: {e}'
                self.handle_error(error_message)
            else:
                self.update_progress.emit('Transcoding cancelled.')
        finally:
            # Clean up any temporary files if thread was cancelled
            try:
                if self.is_canceled() and temp_files:
                    for temp_file in temp_files:
                        if os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                                logger.info(f"Cleaned up temporary file after cancellation: {temp_file}")
                            except Exception as cleanup_error:
                                logger.warning(f"Failed to clean up temporary file {temp_file}: {cleanup_error}")
            except Exception as e:
                logger.error(f"Error during post-cancellation cleanup: {e}")

    def transcode_audio(self, source_path, target_dir):
        self.update_progress.emit('Transcoding audio file...')
        target_file_path = self.generate_unique_target_path(target_dir, self.target_format)
        self.reencode_audio(source_path, target_file_path)
        
        # Optionally remove the original source file
        if os.path.exists(target_file_path):
            os.remove(source_path)
            
        # Check if we need to chunk the audio file
        if self.chunk_enabled:
            self.update_progress.emit('Checking audio duration for chunking...')
            audio = AudioSegment.from_file(target_file_path)
            duration_mins = len(audio) / (1000 * 60)  # Convert milliseconds to minutes
            
            if duration_mins > self.chunk_duration:
                self.update_progress.emit(f'Audio is {duration_mins:.1f} minutes long. Splitting into {self.chunk_duration}-minute chunks...')
                chunk_paths = self.chunk_audio(target_file_path, audio)
                self.update_progress.emit(f'Created {len(chunk_paths)} chunks')
                self.completed.emit(chunk_paths)
                return
                
        # If chunking is disabled or file is shorter than chunk duration
        self.completed.emit([target_file_path])

    def extract_audio_from_video(self, video_path, target_dir):
        self.update_progress.emit('Extracting audio from video...')
        audio_path = self.generate_unique_target_path(target_dir, 'mp3', audio_only=True)
        
        with VideoFileClip(video_path) as video:
            duration_mins = video.duration / 60  # Get duration in minutes
            video.audio.write_audiofile(audio_path)
            
        # Optionally remove the original video file
        if os.path.exists(audio_path):
            os.remove(video_path)
            
        # Check if we need to chunk the audio file
        if self.chunk_enabled:
            self.update_progress.emit('Checking video duration for chunking...')
            
            if duration_mins > self.chunk_duration:
                self.update_progress.emit(f'Video audio is {duration_mins:.1f} minutes long. Splitting into {self.chunk_duration}-minute chunks...')
                audio = AudioSegment.from_file(audio_path)
                chunk_paths = self.chunk_audio(audio_path, audio)
                self.update_progress.emit(f'Created {len(chunk_paths)} chunks')
                self.completed.emit(chunk_paths)
                return
                
        # If chunking is disabled or file is shorter than chunk duration
        self.completed.emit([audio_path])

    def generate_unique_target_path(self, target_dir, target_format, audio_only=False):
        base_name = os.path.basename(self.file_path)
        name, _ = os.path.splitext(base_name)
        if audio_only:
            name += "_extracted_audio"
        counter = 1
        target_file_path = os.path.join(target_dir, f"{name}.{target_format}")
        while os.path.exists(target_file_path):
            target_file_path = os.path.join(target_dir, f"{name}_{counter}.{target_format}")
            counter += 1
        return target_file_path

    def reencode_audio(self, source_path, target_path):
        self.update_progress.emit('Re-encoding audio...')
        audio = AudioSegment.from_file(source_path)
        audio.export(target_path, format=self.target_format)

    def chunk_audio(self, audio_path, audio):
        chunk_paths = []
        try:
            # Check for cancellation
            if self.is_canceled():
                self.update_progress.emit('Chunking cancelled.')
                return [audio_path]
                
            # Calculate chunk size in milliseconds
            chunk_size_ms = self.chunk_duration * 60 * 1000  # Convert minutes to milliseconds
            duration_ms = len(audio)
            num_chunks = math.ceil(duration_ms / chunk_size_ms)
            
            self.update_progress.emit(f'Splitting audio into {num_chunks} chunks of {self.chunk_duration} minutes each...')
            
            # Get base filename for chunks
            base_dir = os.path.dirname(audio_path)
            base_name = os.path.basename(audio_path)
            name, ext = os.path.splitext(base_name)
            
            # Process each chunk
            for i in range(num_chunks):
                # Check for cancellation before each chunk
                if self.is_canceled():
                    self.update_progress.emit(f'Chunking cancelled at chunk {i+1}/{num_chunks}.')
                    # Clean up partial chunks if cancelled
                    for path in chunk_paths:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                                logger.info(f"Cleaned up chunk file after cancellation: {path}")
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to clean up chunk file {path}: {cleanup_error}")
                    # Return original if cancellation occurred
                    return [audio_path]
                
                start_ms = i * chunk_size_ms
                end_ms = min((i + 1) * chunk_size_ms, duration_ms)
                
                chunk = audio[start_ms:end_ms]
                chunk_path = os.path.join(base_dir, f"{name}_chunk{i+1}{ext}")
                
                # Export the chunk
                self.update_progress.emit(f'Exporting chunk {i+1}/{num_chunks}...')
                chunk.export(chunk_path, format=self.target_format)
                chunk_paths.append(chunk_path)
                
                # Check if cancellation occurred while exporting (for long exports)
                if self.is_canceled():
                    self.update_progress.emit(f'Chunking cancelled after exporting chunk {i+1}/{num_chunks}.')
                    # Clean up partial chunks
                    for path in chunk_paths:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                                logger.info(f"Cleaned up chunk file after post-export cancellation: {path}")
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to clean up chunk file {path}: {cleanup_error}")
                    return [audio_path]
                
            # Return the list of completed chunk paths
            return chunk_paths
            
        except Exception as e:
            if not self.is_canceled():
                self.error.emit(f"Error chunking audio: {str(e)}")
                logger.error(f"Chunking error: {e}", exc_info=True)
            
            # Clean up any partial chunks on exception
            try:
                for path in chunk_paths:
                    if os.path.exists(path):
                        os.remove(path)
                        logger.info(f"Cleaned up chunk file after error: {path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up chunk files after error: {cleanup_error}")
                
            return [audio_path]  # Return original if chunking fails
    
    def handle_error(self, error_message):
        traceback.print_exc()
        self.error.emit(error_message)