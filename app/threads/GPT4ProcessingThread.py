from PyQt6.QtCore import QThread, pyqtSignal
import requests
import traceback
import json
import time
from threading import Lock # Import Lock
from typing import List, Dict, Any, Optional, Union
import logging # Use logging

logger = logging.getLogger('transcribrr')

class GPT4ProcessingThread(QThread):
    """Thread for processing text with OpenAI's GPT models."""
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    # Constants
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2  # seconds
    API_ENDPOINT = 'https://api.openai.com/v1/chat/completions'
    TIMEOUT = 120  # seconds (Increased timeout for potentially long responses)

    def __init__(self,
                transcript: str,
                prompt_instructions: str,
                gpt_model: str,
                max_tokens: int,
                temperature: float,
                openai_api_key: str,
                messages: Optional[List[Dict[str, str]]] = None,
                *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transcript = transcript
        self.prompt_instructions = prompt_instructions
        self.gpt_model = gpt_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.openai_api_key = openai_api_key
        self.messages = messages

        # Cancellation flag
        self._is_canceled = False
        self._lock = Lock()
        self.current_request = None # To potentially cancel the request

    def cancel(self):
        """Request cancellation of the GPT processing."""
        with self._lock:
            if not self._is_canceled:
                logger.info("Cancellation requested for GPT processing thread.")
                self._is_canceled = True
                # Attempt to abort the network request if possible
                # Note: This might not always work cleanly depending on `requests` state
                if self.current_request and hasattr(self.current_request, 'close'):
                     try:
                          # This is a bit hacky - requests doesn't have a formal cancel.
                          # Closing might raise errors, we'll handle them.
                          logger.debug("Attempting to close active HTTP request.")
                          # Find the connection object and close it? Difficult.
                          # A simpler approach is just to ignore the result if cancelled.
                     except Exception as e:
                          logger.warning(f"Could not forcefully close request: {e}")


    def is_canceled(self):
        """Check if cancellation has been requested."""
        with self._lock:
            return self._is_canceled

    def run(self):
        """Execute the thread to process text with GPT."""
        if self.is_canceled():
            self.update_progress.emit("GPT processing cancelled before starting.")
            return

        try:
            self.update_progress.emit('GPT processing started...')

            # Construct messages if not provided
            if not self.messages:
                messages_to_send = [
                    {'role': 'system', 'content': self.prompt_instructions},
                    {'role': 'user', 'content': self.transcript}
                ]
            else:
                messages_to_send = self.messages

            if self.is_canceled(): # Check again before API call
                self.update_progress.emit("GPT processing cancelled.")
                return

            result = self._send_api_request(messages_to_send)

            if self.is_canceled(): # Check after API call returns
                self.update_progress.emit("GPT processing cancelled.")
            else:
                self.completed.emit(result)
                self.update_progress.emit('GPT processing finished.')

        except Exception as e:
            if not self.is_canceled():
                error_message = str(e)
                # Refine error messages
                if "rate limit" in error_message.lower():
                    error_message = "Rate limit exceeded. Please wait or check your OpenAI plan limits."
                elif "invalid_api_key" in error_message.lower() or "Incorrect API key" in error_message:
                    error_message = "Invalid API key. Please check your OpenAI API key in Settings."
                elif "context_length_exceeded" in error_message.lower():
                    error_message = "Input is too long for this model. Try a different model or shorten the text."
                elif isinstance(e, requests.exceptions.Timeout):
                     error_message = "Request timed out. Check connection or try again."
                elif isinstance(e, requests.exceptions.ConnectionError):
                     error_message = "Connection Error. Check internet or OpenAI service status."

                self.error.emit(error_message)
                logger.error(f"GPT Processing error: {e}", exc_info=True) # Log full traceback
            else:
                 self.update_progress.emit("GPT processing cancelled during error handling.")
        finally:
             logger.info("GPT processing thread finished execution.")


    def _send_api_request(self, messages: List[Dict[str, str]]) -> str:
        """Send a request to the OpenAI API and handle retries."""
        retry_count = 0
        last_error = None

        while retry_count < self.MAX_RETRY_ATTEMPTS:
            if self.is_canceled(): return "[Cancelled]"

            try:
                self.update_progress.emit(f'Sending request to OpenAI ({self.gpt_model})... Attempt {retry_count + 1}')
                data = {'messages': messages, 'model': self.gpt_model,
                        'max_tokens': self.max_tokens, 'temperature': self.temperature}
                headers = {'Authorization': f'Bearer {self.openai_api_key}',
                           'Content-Type': 'application/json'}

                # Store request object - limited utility for cancellation
                session = requests.Session()
                prepared_request = requests.Request('POST', self.API_ENDPOINT, json=data, headers=headers).prepare()
                # self.current_request = session # session doesn't directly help cancel flight

                response = session.send(prepared_request, timeout=self.TIMEOUT)
                self.current_request = None # Request finished

                if self.is_canceled(): return "[Cancelled]" # Check after potentially long request

                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                response_data = response.json()
                content = response_data.get('choices', [{}])[0].get('message', {}).get('content', '')
                logger.info(f"Received successful response from OpenAI API. Choice 0 content length: {len(content)}")
                return content

            except requests.exceptions.Timeout as e:
                 last_error = e
                 logger.warning(f"Request timed out (Attempt {retry_count + 1}): {e}")
                 # Fall through to retry logic

            except requests.exceptions.ConnectionError as e:
                 # Don't retry connection errors usually
                 logger.error(f"Connection error: {e}")
                 raise Exception(f"Unable to connect to OpenAI API: {e}") from e

            except requests.exceptions.RequestException as e: # Catches HTTPError, etc.
                 last_error = e
                 logger.warning(f"RequestException (Attempt {retry_count + 1}): {e}. Status: {e.response.status_code if e.response else 'N/A'}")
                 error_info = self._parse_error_response(e.response) if e.response else str(e)
                 status_code = e.response.status_code if e.response else 500 # Assume server error if no response code

                 if self._should_retry(status_code, error_info):
                     # Fall through to retry logic
                     pass
                 else:
                     # Don't retry other client errors (e.g., 400 Bad Request, 401 Auth Error)
                     raise Exception(f"OpenAI API error: {error_info}") from e
            except Exception as e:
                 # Catch any other unexpected errors
                 last_error = e
                 logger.error(f"Unexpected error during API request (Attempt {retry_count + 1}): {e}", exc_info=True)
                 # Don't retry unexpected errors
                 raise # Re-raise the original exception

            # --- Retry Logic ---
            retry_count += 1
            if retry_count < self.MAX_RETRY_ATTEMPTS:
                if self.is_canceled(): return "[Cancelled]"
                retry_delay = self.RETRY_DELAY * (2 ** (retry_count - 1)) # Exponential backoff
                self.update_progress.emit(f"Retrying in {retry_delay:.1f}s... (Attempt {retry_count + 1}/{self.MAX_RETRY_ATTEMPTS})")
                self.sleep(int(retry_delay)) # Use QThread's sleep
            else:
                 logger.error("Max retry attempts reached.")
                 raise Exception(f"Failed after {self.MAX_RETRY_ATTEMPTS} attempts. Last error: {last_error}") from last_error

        return "[Error: Max retries exceeded]" # Should not be reached


    def _parse_error_response(self, response: requests.Response) -> str:
        try:
            error_data = response.json()
            if 'error' in error_data and isinstance(error_data['error'], dict):
                msg = error_data['error'].get('message', 'No message')
                etype = error_data['error'].get('type', 'Unknown type')
                code = error_data['error'].get('code', 'Unknown code')
                return f"{etype} ({code}): {msg}"
            elif 'error' in error_data: # Sometimes error is just a string
                 return str(error_data['error'])
            return response.text # Fallback to raw text
        except json.JSONDecodeError:
            return f"HTTP {response.status_code}: {response.text[:200]}..." # Truncate long non-JSON errors

    def _should_retry(self, status_code: int, error_info: str) -> bool:
        """Determine if a retry should be attempted."""
        # Retry on specific server errors and rate limits
        if status_code in [429, 500, 502, 503, 504]:
            logger.info(f"Retry condition met for status code {status_code}.")
            return True

        # Check specific error types from OpenAI that might be transient
        transient_error_codes = ['server_error', 'rate_limit_exceeded']
        if any(code in error_info.lower() for code in transient_error_codes):
             logger.info(f"Retry condition met for error info: {error_info[:100]}...")
             return True

        logger.warning(f"No retry condition met for status {status_code}, error: {error_info[:100]}...")
        return False
