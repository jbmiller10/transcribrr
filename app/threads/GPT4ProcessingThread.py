from PyQt6.QtCore import QThread, pyqtSignal
import requests
import traceback
import json
import time


class GPT4ProcessingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    # Constants
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2  # seconds

    def __init__(self, transcript, prompt_instructions, gpt_model, max_tokens, temperature, openai_api_key,
                 messages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transcript = transcript
        self.prompt_instructions = prompt_instructions
        self.gpt_model = gpt_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.openai_api_key = openai_api_key
        self.messages = messages  # Accept custom messages
        self.retry_count = 0

    def run(self):
        try:
            self.update_progress.emit('GPT processing started...')
            if self.messages:
                result = self.ask_openai_with_messages()
            else:
                result = self.ask_openai()
            self.completed.emit(result)
            self.update_progress.emit('GPT processing finished.')
        except Exception as e:
            error_message = str(e)
            if "rate limit" in error_message.lower():
                error_message = "Rate limit exceeded. Please wait a moment before trying again."
            elif "invalid_api_key" in error_message.lower():
                error_message = "Invalid API key. Please check your OpenAI API key in the settings."
            elif "context_length_exceeded" in error_message.lower():
                error_message = "The transcript is too long for this model. Try reducing the text length or using a model with larger context window."

            self.error.emit(error_message)
            traceback.print_exc()

    def ask_openai(self):
        """Send a request to the OpenAI API and handle potential errors."""
        while self.retry_count < self.MAX_RETRY_ATTEMPTS:
            try:
                self.update_progress.emit(f'Sending request to OpenAI ({self.gpt_model})...')
                data = {
                    'messages': [
                        {
                            'role': 'system',
                            'content': self.prompt_instructions
                        },
                        {
                            'role': 'user',
                            'content': self.transcript
                        }
                    ],
                    'model': self.gpt_model,
                    'max_tokens': self.max_tokens,
                    'temperature': self.temperature
                }
                headers = {
                    'Authorization': f'Bearer {self.openai_api_key}',
                    'Content-Type': 'application/json'
                }

                response = requests.post(
                    'https://api.openai.com/v1/chat/completions',
                    json=data,
                    headers=headers,
                    timeout=60  # Add timeout to prevent hanging indefinitely
                )

                # Check for HTTP errors
                if response.status_code != 200:
                    error_info = self.parse_error_response(response)
                    if self.should_retry(response.status_code, error_info):
                        self.retry_count += 1
                        retry_delay = self.RETRY_DELAY * self.retry_count
                        self.update_progress.emit(
                            f"Retrying in {retry_delay} seconds... (Attempt {self.retry_count}/{self.MAX_RETRY_ATTEMPTS})")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise Exception(f"OpenAI API error: {error_info}")

                response_data = response.json()
                return response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

            except requests.exceptions.Timeout:
                if self.retry_count < self.MAX_RETRY_ATTEMPTS - 1:
                    self.retry_count += 1
                    retry_delay = self.RETRY_DELAY * self.retry_count
                    self.update_progress.emit(
                        f"Request timed out. Retrying in {retry_delay} seconds... (Attempt {self.retry_count}/{self.MAX_RETRY_ATTEMPTS})")
                    time.sleep(retry_delay)
                else:
                    raise Exception("OpenAI API request timed out after multiple attempts. Please try again later.")

            except requests.exceptions.ConnectionError:
                raise Exception("Unable to connect to OpenAI API. Please check your internet connection.")

            except Exception as e:
                # For any other exceptions, don't retry
                raise e

        # If we've exhausted all retries
        raise Exception("Failed to get a response from OpenAI API after multiple attempts. Please try again later.")

    def ask_openai_with_messages(self):
        """Send a conversation to the OpenAI API using provided messages."""
        while self.retry_count < self.MAX_RETRY_ATTEMPTS:
            try:
                self.update_progress.emit(f'Sending conversation to OpenAI ({self.gpt_model})...')
                data = {
                    'messages': self.messages,
                    'model': self.gpt_model,
                    'max_tokens': self.max_tokens,
                    'temperature': self.temperature
                }

                headers = {
                    'Authorization': f'Bearer {self.openai_api_key}',
                    'Content-Type': 'application/json'
                }

                response = requests.post(
                    'https://api.openai.com/v1/chat/completions',
                    json=data,
                    headers=headers,
                    timeout=60
                )

                # Check for HTTP errors
                if response.status_code != 200:
                    error_info = self.parse_error_response(response)
                    if self.should_retry(response.status_code, error_info):
                        self.retry_count += 1
                        retry_delay = self.RETRY_DELAY * self.retry_count
                        self.update_progress.emit(
                            f"Retrying in {retry_delay} seconds... (Attempt {self.retry_count}/{self.MAX_RETRY_ATTEMPTS})")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise Exception(f"OpenAI API error: {error_info}")

                response_data = response.json()
                return response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

            except requests.exceptions.Timeout:
                if self.retry_count < self.MAX_RETRY_ATTEMPTS - 1:
                    self.retry_count += 1
                    retry_delay = self.RETRY_DELAY * self.retry_count
                    self.update_progress.emit(
                        f"Request timed out. Retrying in {retry_delay} seconds... (Attempt {self.retry_count}/{self.MAX_RETRY_ATTEMPTS})")
                    time.sleep(retry_delay)
                else:
                    raise Exception("OpenAI API request timed out after multiple attempts. Please try again later.")

            except requests.exceptions.ConnectionError:
                raise Exception("Unable to connect to OpenAI API. Please check your internet connection.")

            except Exception as e:
                # For any other exceptions, don't retry
                raise e

        # If we've exhausted all retries
        raise Exception("Failed to get a response from OpenAI API after multiple attempts. Please try again later.")

    def parse_error_response(self, response):
        """Parse error information from the API response."""
        try:
            error_data = response.json()
            if 'error' in error_data:
                error_message = error_data['error'].get('message', '')
                error_type = error_data['error'].get('type', '')
                return f"{error_type}: {error_message}"
            return response.text
        except json.JSONDecodeError:
            return f"HTTP {response.status_code}: {response.text}"

    def should_retry(self, status_code, error_info):
        """Determine if a retry should be attempted based on the error."""
        # Retry on rate limiting (429) or server errors (5xx)
        if status_code == 429 or (status_code >= 500 and status_code < 600):
            return True

        # Don't retry on client errors except rate limiting
        if status_code >= 400 and status_code < 500 and status_code != 429:
            return False

        # Check for specific error messages that might warrant retrying
        retry_phrases = ['rate_limit', 'server_error', 'timeout', 'overloaded']
        return any(phrase in error_info.lower() for phrase in retry_phrases)