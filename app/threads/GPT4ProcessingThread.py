from PyQt6.QtCore import QThread, pyqtSignal
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError
import json
from threading import Lock  # Import Lock
from typing import List, Dict, Optional, Any, Union
import logging  # Use logging

logger = logging.getLogger("transcribrr")


class GPT4ProcessingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    # Constants
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2  # seconds
    API_ENDPOINT = "https://api.openai.com/v1/chat/completions"  # Always use HTTPS
    TIMEOUT = 120  # seconds (Increased timeout for potentially long responses)

    def __init__(
        self,
        transcript: str,
        prompt_instructions: str,
        gpt_model: str,
        max_tokens: int,
        temperature: float,
        openai_api_key: str,
        messages: Optional[List[Dict[str, str]]] = None,
        *args,
        **kwargs,
    ):
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
        # To potentially cancel the request
        self.current_request: Optional[requests.Session] = None
        self._session: Optional[requests.Session] = None
        self._response: Optional[requests.Response] = None

    def cancel(self):
        with self._lock:
            if not self._is_canceled:
                logger.info(
                    "Cancellation requested for GPT processing thread.")
                self._is_canceled = True
                self.requestInterruption()  # Use QThread's built-in interruption

                # Close the response first, then the session
                if self._response is not None:
                    try:
                        logger.debug("Closing active HTTP response.")
                        self._response.close()
                    except Exception as e:
                        logger.warning(f"Could not close response: {e}")
                    self._response = None

                if self._session is not None:
                    try:
                        logger.debug("Closing active HTTP session.")
                        self._session.close()
                    except Exception as e:
                        logger.warning(f"Could not close session: {e}")
                    self._session = None

                # Backward compatibility with existing code
                if self.current_request and hasattr(self.current_request, "close"):
                    try:
                        logger.debug(
                            "Attempting to close active HTTP session (legacy)."
                        )
                        self.current_request.close()
                    except Exception as e:
                        logger.warning(
                            f"Could not forcefully close request: {e}")

    def is_canceled(self):
        # Check both the custom flag and QThread's interruption status
        with self._lock:
            return self._is_canceled or self.isInterruptionRequested()

    def run(self):
        if self.is_canceled():
            self.update_progress.emit(
                "GPT processing cancelled before starting.")
            return

        try:
            self.update_progress.emit("GPT processing started...")

            # Validate API key before proceeding
            if not self.openai_api_key:
                raise ValueError(
                    "OpenAI API key is missing. Please add your API key in Settings."
                )

            # Construct messages if not provided
            if not self.messages:
                messages_to_send = [
                    {"role": "system", "content": self.prompt_instructions},
                    {"role": "user", "content": self.transcript},
                ]
            else:
                messages_to_send = self.messages

            if self.is_canceled():  # Check again before API call
                self.update_progress.emit("GPT processing cancelled.")
                return

            result = self._send_api_request(messages_to_send)

            if self.is_canceled():  # Check after API call returns
                self.update_progress.emit("GPT processing cancelled.")
            else:
                self.completed.emit(result)
                self.update_progress.emit("GPT processing finished.")

        except requests.exceptions.Timeout as e:
            if not self.is_canceled():
                error_message = "Request timed out. Check your internet connection or try again later."
                self.error.emit(error_message)
                from app.secure import redact

                logger.error(
                    f"GPT Processing timeout: {redact(str(e))}", exc_info=False)
            else:
                self.update_progress.emit(
                    "GPT processing cancelled during timeout.")

        except requests.exceptions.ConnectionError as e:
            if not self.is_canceled():
                error_message = "Connection error. Check your internet connection or OpenAI service status."
                self.error.emit(error_message)
                from app.secure import redact

                logger.error(
                    f"GPT Processing connection error: {redact(str(e))}", exc_info=False
                )
            else:
                self.update_progress.emit(
                    "GPT processing cancelled during connection error."
                )

        except requests.exceptions.RequestException as e:
            if not self.is_canceled():
                from app.secure import redact

                safe_msg = redact(str(e))
                error_message = f"Network request error: {safe_msg}"
                self.error.emit(error_message)
                logger.error(
                    f"GPT Processing request error: {safe_msg}", exc_info=False)
            else:
                self.update_progress.emit(
                    "GPT processing cancelled during request error."
                )

        except ValueError as e:
            if not self.is_canceled():
                # API key or configuration error
                error_message = str(e)
                self.error.emit(error_message)
                logger.error(
                    f"GPT Processing configuration error: {error_message}")
            else:
                self.update_progress.emit(
                    "GPT processing cancelled during configuration error."
                )

        except Exception as e:
            if not self.is_canceled():
                from app.secure import redact

                error_message = str(e)
                safe_msg = redact(error_message)

                # Refine error messages
                if "rate limit" in error_message.lower():
                    error_message = "Rate limit exceeded. Please wait or check your OpenAI plan limits."
                elif (
                    "invalid_api_key" in error_message.lower()
                    or "Incorrect API key" in error_message
                ):
                    error_message = (
                        "Invalid API key. Please check your OpenAI API key in Settings."
                    )
                elif (
                    "context_length_exceeded" in error_message.lower()
                    or "maximum context length" in error_message.lower()
                ):
                    error_message = "Input is too long for this model. Try a different model or shorten the text."
                elif (
                    "no api key" in error_message.lower()
                    or "api key not found" in error_message.lower()
                ):
                    error_message = "API key is missing. Please add your OpenAI API key in Settings."
                elif "authentication" in error_message.lower():
                    error_message = "Authentication failed. Please check your OpenAI API key in Settings."
                elif "insufficient_quota" in error_message.lower():
                    error_message = "Your OpenAI API quota has been exceeded. Please check your billing status."
                elif (
                    "not_found" in error_message.lower()
                    and "model" in error_message.lower()
                ):
                    error_message = "The requested model was not found. It may be deprecated or unavailable in your account."
                else:
                    # For all other errors, use a general message but log the full error
                    error_message = f"An error occurred: {safe_msg}"

                self.error.emit(error_message)
                logger.error(
                    f"GPT Processing error: {safe_msg}", exc_info=False)
            else:
                self.update_progress.emit(
                    "GPT processing cancelled during error handling."
                )
        finally:
            # Clean up any resources
            try:
                # Close the response first, then the session
                if self._response is not None:
                    try:
                        logger.debug("Closing HTTP response in finally block.")
                        self._response.close()
                    except Exception as e:
                        logger.warning(
                            f"Error closing response in finally block: {e}")
                    self._response = None

                if self._session is not None:
                    try:
                        logger.debug("Closing HTTP session in finally block.")
                        self._session.close()
                    except Exception as e:
                        logger.warning(
                            f"Error closing session in finally block: {e}")
                    self._session = None

                # Legacy cleanup
                if hasattr(self, "current_request") and self.current_request:
                    if hasattr(self.current_request, "close"):
                        try:
                            self.current_request.close()
                        except Exception as e:
                            logger.warning(
                                f"Error closing request in finally block: {e}"
                            )
                    self.current_request = None
            except Exception as cleanup_e:
                logger.warning(f"Error during resource cleanup: {cleanup_e}")
            logger.info("GPT processing thread finished execution.")

    def _send_api_request(self, messages: List[Dict[str, str]]) -> str:
        retry_count = 0
        last_error: Optional[Exception] = None
        session: Optional[requests.Session] = None

        while retry_count < self.MAX_RETRY_ATTEMPTS:
            if self.isInterruptionRequested() or self.is_canceled():
                return "[Cancelled]"

            try:
                self.update_progress.emit(
                    f"Sending request to OpenAI ({self.gpt_model})... Attempt {retry_count + 1}"
                )

                # Verify HTTPS is being used
                if not self.API_ENDPOINT.startswith("https://"):
                    raise ValueError("API URL must use HTTPS for security")

                data = {
                    "messages": messages,
                    "model": self.gpt_model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                }
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                }

                # Create a new session for each attempt to ensure clean state
                # This assignment ensures type is maintained for mypy
                self._session = requests.Session()
                prepared_request = requests.Request(
                    "POST", self.API_ENDPOINT, json=data, headers=headers
                ).prepare()
                self.current_request = (
                    self._session  # Store session for potential cancellation
                )

                # Check cancellation again before sending request
                if self.isInterruptionRequested() or self.is_canceled():
                    return "[Cancelled]"

                self._response = self._session.send(
                    prepared_request, timeout=self.TIMEOUT
                )
                self.current_request = None  # Request finished

                if self.isInterruptionRequested() or self.is_canceled():
                    # Check after potentially long request
                    return "[Cancelled]"

                # Raise HTTPError for bad responses (4xx or 5xx)
                self._response.raise_for_status()

                response_data = self._response.json()
                content: str = (
                    response_data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                logger.info(
                    f"Received successful response from OpenAI API. Choice 0 content length: {len(content)}"
                )
                return content

            except Timeout as e:
                last_error = e
                logger.warning(
                    f"Request timed out (Attempt {retry_count + 1}): {e}")
                # Fall through to retry logic

            except ConnectionError as e:
                # Don't retry connection errors usually
                logger.error(f"Connection error: {e}")
                raise Exception(f"Unable to connect to OpenAI API: {e}") from e

            except RequestException as e:  # Catches HTTPError, etc.
                last_error = e
                logger.warning(
                    f"RequestException (Attempt {retry_count + 1}): {e}. Status: {e.response.status_code if e.response else 'N/A'}"
                )
                error_info = (
                    self._parse_error_response(
                        e.response) if e.response else str(e)
                )
                status_code = (
                    e.response.status_code if e.response else 500
                )  # Assume server error if no response code

                if self._should_retry(status_code, error_info):
                    # Fall through to retry logic
                    pass
                else:
                    # Don't retry other client errors (e.g., 400 Bad Request, 401 Auth Error)
                    raise Exception(f"OpenAI API error: {error_info}") from e
            except Exception as e:
                # Catch any other unexpected errors
                last_error = e
                logger.error(
                    f"Unexpected error during API request (Attempt {retry_count + 1}): {e}",
                    exc_info=True,
                )
                # Don't retry unexpected errors
                raise  # Re-raise the original exception

            # --- Retry Logic ---
            retry_count += 1
            if retry_count < self.MAX_RETRY_ATTEMPTS:
                if self.isInterruptionRequested() or self.is_canceled():
                    return "[Cancelled]"
                retry_delay = self.RETRY_DELAY * (
                    2 ** (retry_count - 1)
                )  # Exponential backoff
                self.update_progress.emit(
                    f"Retrying in {retry_delay:.1f}s... (Attempt {retry_count + 1}/{self.MAX_RETRY_ATTEMPTS})"
                )

                # Check for interruption during sleep to ensure prompt return
                ms_delay = int(retry_delay * 1000)  # Convert to milliseconds
                step = 100  # Check every 100ms
                for _ in range(0, ms_delay, step):
                    if self.isInterruptionRequested():
                        return "[Cancelled]"
                    self.msleep(step)
            else:
                logger.error("Max retry attempts reached.")
                raise Exception(
                    f"Failed after {self.MAX_RETRY_ATTEMPTS} attempts. Last error: {last_error}"
                ) from last_error

        return "[Error: Max retries exceeded]"  # Should not be reached

    def _parse_error_response(self, response: requests.Response) -> str:
        try:
            error_data = response.json()
            if "error" in error_data and isinstance(error_data["error"], dict):
                msg = error_data["error"].get("message", "No message")
                etype = error_data["error"].get("type", "Unknown type")
                code = error_data["error"].get("code", "Unknown code")
                return f"{etype} ({code}): {msg}"
            elif "error" in error_data:  # Sometimes error is just a string
                return str(error_data["error"])
            return str(response.text)  # Fallback to raw text
        except json.JSONDecodeError:
            # Truncate long non-JSON errors
            return f"HTTP {response.status_code}: {response.text[:200]}..."

    def _should_retry(self, status_code: int, error_info: str) -> bool:
        # Retry on specific server errors and rate limits
        if status_code in [429, 500, 502, 503, 504]:
            logger.info(f"Retry condition met for status code {status_code}.")
            return True

        # Check specific error types from OpenAI that might be transient
        transient_error_codes = ["server_error", "rate_limit_exceeded"]
        if any(code in error_info.lower() for code in transient_error_codes):
            logger.info(
                f"Retry condition met for error info: {error_info[:100]}...")
            return True

        logger.warning(
            f"No retry condition met for status {status_code}, error: {error_info[:100]}..."
        )
        return False
