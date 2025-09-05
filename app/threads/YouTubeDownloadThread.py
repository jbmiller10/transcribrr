from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime
import os
import requests
from app.constants import get_recordings_dir
import logging  # Use logging
from threading import Lock

logger = logging.getLogger("transcribrr")


class YouTubeDownloadThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)  # Emits single path of the final audio file
    error = pyqtSignal(str)

    def __init__(self, youtube_url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.youtube_url = youtube_url
        self._is_canceled = False
        self._lock = Lock()
        self.ydl_instance = None  # To potentially interrupt download
        self._temp_files = []  # Track temporary files for cleanup

    def cancel(self):
        with self._lock:
            if not self._is_canceled:
                logger.info(
                    "Cancellation requested for YouTube download thread.")
                self._is_canceled = True
                self.requestInterruption()  # Use QThread's built-in interruption
                # Attempt to interrupt yt-dlp (might not always work)
                # yt-dlp doesn't have a direct public API for interruption.
                # We mostly rely on checking the flag between steps.

    def is_canceled(self):
        # Check both the custom flag and QThread's interruption status
        with self._lock:
            return self._is_canceled or self.isInterruptionRequested()

    def run(self):
        if self.is_canceled():
            self.update_progress.emit(
                "YouTube download cancelled before starting.")
            return

        temp_files = []
        temp_output_template = None
        expected_temp_wav = None
        info_dict = None
        try:
            self.update_progress.emit("Preparing YouTube download...")

            # Validate YouTube URL format
            if not self.youtube_url or not self.youtube_url.strip():
                raise ValueError("YouTube URL is empty or invalid")

            if not (
                self.youtube_url.startswith("http://")
                or self.youtube_url.startswith("https://")
            ):
                raise ValueError(
                    "Invalid URL format. URL must start with http:// or https://"
                )

            if (
                "youtube.com" not in self.youtube_url
                and "youtu.be" not in self.youtube_url
            ):
                raise ValueError("URL doesn't appear to be a YouTube URL")

            # Ensure recordings directory exists
            recordings_dir = get_recordings_dir()
            try:
                os.makedirs(recordings_dir, exist_ok=True)
            except (PermissionError, OSError) as e:
                raise RuntimeError(f"Cannot create recordings directory: {e}")

            # Ensure we have write permission to the directory
            if not os.access(recordings_dir, os.W_OK):
                raise PermissionError(
                    f"No write permission to recordings directory: {recordings_dir}"
                )

            # Define output template - use title and timestamp for uniqueness
            # Use a temporary placeholder name first
            temp_output_template = os.path.join(
                recordings_dir,
                f'youtube_temp_{datetime.now().strftime("%Y%m%d%H%M%S%f")}.%(ext)s',
            )

            # Check cancellation before setting up options
            if self.is_canceled():
                self.update_progress.emit(
                    "YouTube download cancelled after preparing.")
                return

            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "wav",  # Output WAV for transcription consistency
                        "preferredquality": "192",
                    }
                ],
                "outtmpl": temp_output_template,
                "quiet": False,  # Set to False to potentially capture progress
                "noprogress": False,
                "progress_hooks": [self.ydl_progress_hook],
                "logger": logger,  # Use our logger
                # 'verbose': True, # Enable for debugging download issues
                "noplaylist": True,  # Ensure only single video is downloaded
                "socket_timeout": 30,  # Add a socket timeout
                "retries": 5,  # Add retry mechanism for transient network issues
                "ignoreerrors": False,  # Don't ignore errors
            }

            if self.is_canceled():
                self.update_progress.emit(
                    "YouTube download cancelled after initializing."
                )
                return

            # Lazy import yt_dlp
            ydl_mod = None
            try:
                import yt_dlp as ydl_mod  # type: ignore
            except ImportError:
                self.error.emit("yt-dlp library not available for YouTube downloads")
                return
                
            logger.info(f"Starting download for: {self.youtube_url}")
            with ydl_mod.YoutubeDL(ydl_opts) as ydl:
                # Store for potential (limited) interruption
                self.ydl_instance = ydl

                # Check cancellation one more time before the actual download starts
                if self.is_canceled():
                    self.update_progress.emit(
                        "YouTube download cancelled before extraction."
                    )
                    return

                # Start the actual download
                info_dict = ydl.extract_info(self.youtube_url, download=True)
                self.ydl_instance = None  # Clear instance after use

                if not info_dict:
                    raise ValueError(
                        "No information returned from YouTube. The video might be unavailable."
                    )

                if self.is_canceled():
                    # Attempt to clean up partially downloaded file
                    self.cleanup_temp_file(temp_output_template, info_dict)
                    self.update_progress.emit("YouTube download cancelled.")
                    return

                # Construct final filename based on video title (sanitize it)
                video_title = info_dict.get("title", "youtube_video")
                if not video_title or video_title.strip() == "":
                    video_title = "youtube_video"  # Fallback

                sanitized_title = "".join(
                    [c for c in video_title if c.isalnum() or c in (" ", "_", "-")]
                ).rstrip()
                sanitized_title = sanitized_title[:100]  # Limit length
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                final_filename_base = f"{sanitized_title}_{timestamp}"
                final_wav_path = os.path.join(
                    recordings_dir, f"{final_filename_base}.wav"
                )

                # Find the actual downloaded/processed file (yt-dlp might change extension)
                # The actual output path after postprocessing is tricky to get directly.
                # We know the *base* temp name and the final extension is wav.
                expected_temp_wav = temp_output_template.rsplit(".", 1)[
                    0] + ".wav"
                temp_files.append(expected_temp_wav)  # Track for cleanup

                # Check if we have the renamed file from the extractor
                if "filepath" in info_dict and os.path.exists(info_dict["filepath"]):
                    expected_temp_wav = info_dict["filepath"]
                    temp_files.append(expected_temp_wav)
                    logger.info(
                        f"Using filepath from info_dict: {expected_temp_wav}")

                # One final check before renaming and finishing
                if self.is_canceled():
                    self.cleanup_temp_file(temp_output_template, info_dict)
                    self.update_progress.emit(
                        "YouTube download cancelled before finalizing."
                    )
                    return

                if os.path.exists(expected_temp_wav):
                    logger.info(
                        f"Renaming temporary file '{expected_temp_wav}' to '{final_wav_path}'"
                    )
                    try:
                        os.rename(expected_temp_wav, final_wav_path)
                        # No longer need to clean up temp file since it was renamed
                        temp_files.clear()
                        self.completed.emit(final_wav_path)
                        self.update_progress.emit(
                            f"Audio extracted: {os.path.basename(final_wav_path)}"
                        )
                    except (PermissionError, OSError) as e:
                        raise RuntimeError(
                            f"Failed to rename temporary file: {e}")
                else:
                    # Try to find the file using more aggressive search
                    logger.warning(
                        f"Expected temp file '{expected_temp_wav}' not found. Searching for alternatives."
                    )
                    found_file = self._find_downloaded_file(
                        temp_output_template, info_dict
                    )

                    if found_file and os.path.exists(found_file):
                        logger.info(f"Found alternative file: {found_file}")
                        try:
                            os.rename(found_file, final_wav_path)
                            self.completed.emit(final_wav_path)
                            self.update_progress.emit(
                                f"Audio extracted: {os.path.basename(final_wav_path)}"
                            )
                        except (PermissionError, OSError) as e:
                            raise RuntimeError(
                                f"Failed to rename found file: {e}")
                    else:
                        # Fall back to reporting error
                        logger.error(
                            "Could not find any downloaded audio file")
                        self.error.emit(
                            "Failed to find downloaded audio file. The file may not have been downloaded correctly."
                        )

        except Exception as e:
            # Handle yt_dlp.utils.DownloadError if yt_dlp is available
            from app.secure import redact
            error_str = str(e).lower()
            safe_err = redact(error_str)
            
            is_download_error = False
            try:
                if 'ydl_mod' in locals() and ydl_mod is not None:
                    is_download_error = isinstance(e, ydl_mod.utils.DownloadError)
            except Exception:
                is_download_error = False

            if not is_download_error:
                # Not a yt_dlp error, handle as generic error
                if not self.is_canceled():
                    self.error.emit(f"Unexpected error: {safe_err}")
                    logger.error(f"Unexpected error in YouTube thread: {safe_err}", exc_info=True)
                return

            # Handle common yt-dlp errors more specifically
            if "confirm your age" in error_str:
                self.error.emit(
                    "Age-restricted video requires login (not supported).")
            elif "video is unavailable" in error_str:
                self.error.emit("Video is unavailable or has been removed.")
            elif "private video" in error_str:
                self.error.emit("Cannot download private videos.")
            elif "copyright" in error_str:
                self.error.emit(
                    "Video unavailable due to copyright restrictions.")
            elif "blocked" in error_str and "your country" in error_str:
                self.error.emit("This video is not available in your country.")
            elif "sign in" in error_str or "log in" in error_str:
                self.error.emit(
                    "This video requires a YouTube account to access.")
            elif "ffmpeg" in error_str:
                self.error.emit(
                    "Audio conversion failed. FFmpeg might be missing or misconfigured."
                )
            elif "unsupported url" in error_str:
                self.error.emit("The URL format is not supported.")
            elif (
                "network" in error_str
                or "connection" in error_str
                or "timeout" in error_str
            ):
                self.error.emit(
                    "Network error while downloading. Check your internet connection."
                )
            else:
                self.error.emit(f"YouTube download failed: {safe_err}")

            logger.error(f"yt-dlp DownloadError: {safe_err}")

        except requests.exceptions.RequestException as e:
            if not self.is_canceled():
                from app.secure import redact

                safe_err = redact(str(e))
                self.error.emit(f"Network error: {safe_err}")
                logger.error(
                    f"YouTube download network error: {safe_err}"
                )
            else:
                self.update_progress.emit(
                    "YouTube download cancelled during network operation."
                )

        except ValueError as e:
            if not self.is_canceled():
                self.error.emit(f"Invalid input: {e}")
                logger.error(
                    f"YouTube download value error: {e}")
            else:
                self.update_progress.emit(
                    "YouTube download cancelled during validation."
                )

        except (PermissionError, OSError) as e:
            if not self.is_canceled():
                self.error.emit(f"File system error: {e}")
                logger.error(
                    f"YouTube download file system error: {e}")
            else:
                self.update_progress.emit(
                    "YouTube download cancelled during file operation."
                )

        except RuntimeError as e:
            if not self.is_canceled():
                self.error.emit(f"Processing error: {e}")
                logger.error(
                    f"YouTube download runtime error: {e}")
            else:
                self.update_progress.emit(
                    "YouTube download cancelled during processing."
                )

        except Exception as e:
            if not self.is_canceled():
                from app.secure import redact

                safe_err = redact(str(e))
                self.error.emit(f"An unexpected error occurred: {safe_err}")
                logger.error(
                    f"YouTubeDownloadThread error: {safe_err}")
            else:
                self.update_progress.emit(
                    "YouTube download cancelled during error.")
        finally:
            # Clean up resources
            try:
                # Ensure the instance is cleared
                self.ydl_instance = None

                # Clean up any temporary files if they still exist and weren't renamed
                for temp_file in temp_files:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                            logger.info(
                                f"Cleaned up temporary file in finally block: {temp_file}"
                            )
                        except Exception as cleanup_error:
                            logger.warning(
                                f"Failed to clean up temporary file: {cleanup_error}"
                            )

                # Also try the cleanup method with our template and info
                if temp_output_template:
                    self.cleanup_temp_file(temp_output_template, info_dict)

                # Clean any tracked temporary files
                if hasattr(self, "_temp_files") and self._temp_files:
                    for temp_file in self._temp_files:
                        if temp_file and os.path.exists(temp_file):
                            try:
                                os.remove(temp_file)
                                logger.info(
                                    f"Cleaned up tracked temporary file: {temp_file}"
                                )
                            except Exception as cleanup_error:
                                logger.warning(
                                    f"Failed to clean up tracked temporary file: {cleanup_error}"
                                )
                    self._temp_files.clear()
            except Exception as cleanup_e:
                logger.error(
                    f"Error during cleanup in finally block: {cleanup_e}", exc_info=True
                )

            # Log completion
            logger.info("YouTube download thread finished execution.")

    def _find_downloaded_file(self, template_base, info_dict):
        """Try to find the downloaded file using various strategies."""
        # Extract the base part of the template without the extension
        if template_base:
            base_dir = os.path.dirname(template_base)
            base_name = os.path.basename(template_base.rsplit(".", 1)[0])

            # Look for files with this base name and any extension
            try:
                for filename in os.listdir(base_dir):
                    if filename.startswith(base_name):
                        full_path = os.path.join(base_dir, filename)
                        logger.info(
                            f"Found potential download file: {full_path}")
                        return full_path
            except Exception as e:
                logger.error(f"Error while searching for downloaded file: {e}")

        # If info_dict is available, try to use information from it
        if info_dict and "id" in info_dict:
            video_id = info_dict["id"]
            base_dir = (
                os.path.dirname(template_base)
                if template_base
                else get_recordings_dir()
            )

            try:
                for filename in os.listdir(base_dir):
                    # Look for files containing the video ID
                    if video_id in filename:
                        full_path = os.path.join(base_dir, filename)
                        logger.info(f"Found file with video ID: {full_path}")
                        return full_path
            except Exception as e:
                logger.error(
                    f"Error while searching for file with video ID: {e}")

        return None

    def ydl_progress_hook(self, d):
        # Check cancellation status frequently
        if self.is_canceled():
            # Attempt to signal yt-dlp to stop (may not work reliably)
            # This will raise an exception to interrupt the download
            logger.info("Raising DownloadCancelled exception in progress hook")
            # Raise cancellation error dynamically
            try:
                import yt_dlp
                raise yt_dlp.utils.DownloadCancelled("Download cancelled by user")
            except ImportError:
                raise Exception("Download cancelled by user")

        # Track the current temporary file path for possible cleanup
        if d.get("info_dict") and d.get("filename"):
            temp_filename = d.get("filename")
            if hasattr(self, "_temp_files") and isinstance(self._temp_files, list):
                if temp_filename not in self._temp_files:
                    self._temp_files.append(temp_filename)
                    logger.debug(f"Tracking temporary file: {temp_filename}")

        if d["status"] == "downloading":
            percent_str = d.get("_percent_str", "0.0%")
            speed_str = d.get("_speed_str", "N/A")
            eta_str = d.get("_eta_str", "N/A")
            self.update_progress.emit(
                f"Downloading: {percent_str} at {speed_str} (ETA: {eta_str})"
            )

            # Check cancellation periodically during download
            if self.is_canceled():
                logger.info(
                    "Cancellation detected during download progress update")
                # Raise cancellation error dynamically
                try:
                    import yt_dlp
                    raise yt_dlp.utils.DownloadCancelled(
                        "Download cancelled by user")
                except ImportError:
                    raise Exception("Download cancelled by user")
        elif d["status"] == "finished":
            self.update_progress.emit("Download complete. Processing audio...")
            # Check cancellation before post-processing starts
            if self.is_canceled():
                logger.info("Cancellation detected after download finished")
                # Raise cancellation error dynamically
                try:
                    import yt_dlp
                    raise yt_dlp.utils.DownloadCancelled(
                        "Download cancelled by user")
                except ImportError:
                    raise Exception("Download cancelled by user")
        elif d["status"] == "error":
            logger.error(
                "yt-dlp reported an error during download/processing.")
            # Error will likely be raised by extract_info, but log here too

    def cleanup_temp_file(self, template, info_dict):
        try:
            # Try to reconstruct the possible temp filename
            temp_base = template.rsplit(".", 1)[0]

            # Check for common extensions yt-dlp might use temporarily
            # Add more extensions that might be used during processing
            possible_exts = [
                ".tmp",
                ".part",
                ".temp",
                ".wav",
                ".ytdl",
                ".download",
                ".dl",
                ".webm",
                ".m4a",
                ".mp3",
                ".mp4",
            ]

            # Also add the extension from info_dict if available
            if info_dict and info_dict.get("ext"):
                possible_exts.append("." + info_dict.get("ext"))

            # Create a set of paths to check
            files_to_check = set()

            # Add variations with the template base
            for ext in possible_exts:
                files_to_check.add(temp_base + ext)

            # Check for any files that include the base name (for partial downloads)
            base_name = os.path.basename(temp_base)
            # Use configured recordings directory
            recordings_dir = get_recordings_dir()

            if os.path.exists(recordings_dir):
                for filename in os.listdir(recordings_dir):
                    # If filename contains our temp base and has a temp-looking extension
                    if base_name in filename:
                        for ext in possible_exts:
                            if filename.endswith(ext):
                                files_to_check.add(
                                    os.path.join(recordings_dir, filename)
                                )

            # Actually remove the files
            for temp_file in files_to_check:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(
                        f"Removed temporary download file: {temp_file}")

            return True
        except Exception as e:
            logger.warning(
                f"Could not clean up temporary download file: {e}", exc_info=True
            )
            return False
