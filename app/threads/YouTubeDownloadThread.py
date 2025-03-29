import yt_dlp
from PyQt6.QtCore import QThread, pyqtSignal
import traceback
from datetime import datetime
import os
import time
import logging # Use logging
from threading import Lock

logger = logging.getLogger('transcribrr')

class YouTubeDownloadThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str) # Emits single path of the final audio file
    error = pyqtSignal(str)

    def __init__(self, youtube_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.youtube_url = youtube_url
        self._is_canceled = False
        self._lock = Lock()
        self.ydl_instance = None # To potentially interrupt download

    def cancel(self):
        """Request cancellation of the download."""
        with self._lock:
             if not self._is_canceled:
                  logger.info("Cancellation requested for YouTube download thread.")
                  self._is_canceled = True
                  # Attempt to interrupt yt-dlp (might not always work)
                  # yt-dlp doesn't have a direct public API for interruption.
                  # We mostly rely on checking the flag between steps.


    def is_canceled(self):
        with self._lock:
            return self._is_canceled

    def run(self):
        if self.is_canceled():
             self.update_progress.emit("YouTube download cancelled before starting.")
             return

        try:
            self.update_progress.emit('Preparing YouTube download...')
            # Ensure Recordings directory exists
            recordings_dir = 'Recordings'
            os.makedirs(recordings_dir, exist_ok=True)

            # Define output template - use title and timestamp for uniqueness
            # Use a temporary placeholder name first
            temp_output_template = os.path.join(
                recordings_dir,
                f'youtube_temp_{datetime.now().strftime("%Y%m%d%H%M%S%f")}.%(ext)s'
            )

            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'wav', # Output WAV for transcription consistency
                    'preferredquality': '192',
                }],
                'outtmpl': temp_output_template,
                'quiet': False, # Set to False to potentially capture progress
                'noprogress': False,
                'progress_hooks': [self.ydl_progress_hook],
                'logger': logger, # Use our logger
                # 'verbose': True, # Enable for debugging download issues
                 'noplaylist': True, # Ensure only single video is downloaded
                 'socket_timeout': 30, # Add a socket timeout
            }

            if self.is_canceled(): return

            logger.info(f"Starting download for: {self.youtube_url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.ydl_instance = ydl # Store for potential (limited) interruption
                info_dict = ydl.extract_info(self.youtube_url, download=True)
                self.ydl_instance = None # Clear instance after use

                if self.is_canceled():
                     # Attempt to clean up partially downloaded file
                     self.cleanup_temp_file(temp_output_template, info_dict)
                     self.update_progress.emit("YouTube download cancelled.")
                     return

                # Construct final filename based on video title (sanitize it)
                video_title = info_dict.get('title', 'youtube_video')
                sanitized_title = "".join([c for c in video_title if c.isalnum() or c in (' ', '_', '-')]).rstrip()
                sanitized_title = sanitized_title[:100] # Limit length
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_filename_base = f'{sanitized_title}_{timestamp}'
                final_wav_path = os.path.join(recordings_dir, f"{final_filename_base}.wav")

                # Find the actual downloaded/processed file (yt-dlp might change extension)
                # The actual output path after postprocessing is tricky to get directly.
                # We know the *base* temp name and the final extension is wav.
                expected_temp_wav = temp_output_template.rsplit('.', 1)[0] + '.wav'

                if os.path.exists(expected_temp_wav):
                     logger.info(f"Renaming temporary file '{expected_temp_wav}' to '{final_wav_path}'")
                     os.rename(expected_temp_wav, final_wav_path)
                     self.completed.emit(final_wav_path)
                     self.update_progress.emit(f"Audio extracted: {os.path.basename(final_wav_path)}")
                else:
                     # Fallback if the exact temp wav name isn't found (shouldn't happen often)
                     logger.warning(f"Expected temp file '{expected_temp_wav}' not found after download. Emitting template path.")
                     # This might be incorrect if yt-dlp used a different name
                     self.error.emit("Failed to find downloaded audio file.")


        except yt_dlp.utils.DownloadError as e:
             # Handle common yt-dlp errors more specifically
             if "confirm your age" in str(e):
                  self.error.emit("Age-restricted video requires login (not supported).")
             elif "video is unavailable" in str(e).lower():
                  self.error.emit("Video is unavailable.")
             elif "private video" in str(e).lower():
                   self.error.emit("Cannot download private videos.")
             else:
                   self.error.emit(f"YouTube download failed: {e}")
             logger.error(f"yt-dlp DownloadError: {e}", exc_info=True)
        except Exception as e:
            if not self.is_canceled():
                self.error.emit(f"An error occurred: {e}")
                logger.error(f"YouTubeDownloadThread error: {e}", exc_info=True)
            else:
                 self.update_progress.emit("YouTube download cancelled during error.")
        finally:
             self.ydl_instance = None # Ensure cleared


    def ydl_progress_hook(self, d):
        """Progress hook for yt-dlp."""
        if self.is_canceled():
            # Attempt to signal yt-dlp to stop (may not work reliably)
            raise yt_dlp.utils.DownloadCancelled()

        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0.0%')
            speed_str = d.get('_speed_str', 'N/A')
            eta_str = d.get('_eta_str', 'N/A')
            self.update_progress.emit(f"Downloading: {percent_str} at {speed_str} (ETA: {eta_str})")
        elif d['status'] == 'finished':
            self.update_progress.emit("Download complete. Processing audio...")
        elif d['status'] == 'error':
             logger.error("yt-dlp reported an error during download/processing.")
             # Error will likely be raised by extract_info, but log here too


    def cleanup_temp_file(self, template, info_dict):
         """Attempt to remove temporary files if download is cancelled."""
         try:
              # Try to reconstruct the possible temp filename
              temp_base = template.rsplit('.', 1)[0]
              # Check for common extensions yt-dlp might use temporarily
              possible_exts = ['.' + info_dict.get('ext', 'tmp'), '.part', '.temp', '.wav']
              for ext in possible_exts:
                   temp_file = temp_base + ext
                   if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.info(f"Removed temporary download file: {temp_file}")
         except Exception as e:
              logger.warning(f"Could not clean up temporary download file: {e}")