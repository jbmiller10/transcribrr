from PyQt6.QtCore import QThread, pyqtSignal
import requests
import traceback
import json
import time
from typing import List, Dict, Any, Optional, Union


class GPT4ProcessingThread(QThread):
    """Thread for processing text with OpenAI's GPT models."""
    
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    # Constants
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2  # seconds
    API_ENDPOINT = 'https://api.openai.com/v1/chat/completions'
    TIMEOUT = 60  # seconds

    def __init__(self, 
                transcript: str, 
                prompt_instructions: str, 
                gpt_model: str, 
                max_tokens: int, 
                temperature: float, 
                openai_api_key: str,
                messages: Optional[List[Dict[str, str]]] = None, 
                *args, **kwargs):
        """
        Initialize the GPT processing thread.
        
        Args:
            transcript: Text to process
            prompt_instructions: System prompt instructions
            gpt_model: GPT model to use (e.g., "gpt-4o")
            max_tokens: Maximum tokens for completion
            temperature: Temperature for generation
            openai_api_key: OpenAI API key
            messages: Optional list of custom message objects (for multi-turn conversations)
        """
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
        """Execute the thread to process text with GPT."""
        try:
            self.update_progress.emit('GPT processing started...')
            if self.messages:
                result = self._send_api_request(self.messages)
            else:
                # Create default messages with system prompt and user transcript
                messages = [
                    {
                        'role': 'system',
                        'content': self.prompt_instructions
                    },
                    {
                        'role': 'user',
                        'content': self.transcript
                    }
                ]
                result = self._send_api_request(messages)
                
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

    def _send_api_request(self, messages: List[Dict[str, str]]) -> str:
        """
        Send a request to the OpenAI API and handle potential errors.
        
        Args:
            messages: List of message objects to send to the API
            
        Returns:
            Completion text from the API
        """
        self.retry_count = 0
        
        while self.retry_count < self.MAX_RETRY_ATTEMPTS:
            try:
                self.update_progress.emit(f'Sending request to OpenAI ({self.gpt_model})...')
                
                # Prepare API request
                data = {
                    'messages': messages,
                    'model': self.gpt_model,
                    'max_tokens': self.max_tokens,
                    'temperature': self.temperature
                }
                
                headers = {
                    'Authorization': f'Bearer {self.openai_api_key}',
                    'Content-Type': 'application/json'
                }

                # Send the request
                response = requests.post(
                    self.API_ENDPOINT,
                    json=data,
                    headers=headers,
                    timeout=self.TIMEOUT
                )

                # Check for HTTP errors
                if response.status_code != 200:
                    error_info = self._parse_error_response(response)
                    if self._should_retry(response.status_code, error_info):
                        self.retry_count += 1
                        retry_delay = self.RETRY_DELAY * self.retry_count
                        self.update_progress.emit(
                            f"Retrying in {retry_delay} seconds... (Attempt {self.retry_count}/{self.MAX_RETRY_ATTEMPTS})")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise Exception(f"OpenAI API error: {error_info}")

                # Extract and return the response content
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

    def _parse_error_response(self, response: requests.Response) -> str:
        """
        Parse error information from the API response.
        
        Args:
            response: Response object from requests
            
        Returns:
            Formatted error message
        """
        try:
            error_data = response.json()
            if 'error' in error_data:
                error_message = error_data['error'].get('message', '')
                error_type = error_data['error'].get('type', '')
                return f"{error_type}: {error_message}"
            return response.text
        except json.JSONDecodeError:
            return f"HTTP {response.status_code}: {response.text}"

    def _should_retry(self, status_code: int, error_info: str) -> bool:
        """
        Determine if a retry should be attempted based on the error.
        
        Args:
            status_code: HTTP status code from the response
            error_info: Error information string
            
        Returns:
            Whether to retry the request
        """
        # Retry on rate limiting (429) or server errors (5xx)
        if status_code == 429 or (status_code >= 500 and status_code < 600):
            return True

        # Don't retry on client errors except rate limiting
        if status_code >= 400 and status_code < 500 and status_code != 429:
            return False

        # Check for specific error messages that might warrant retrying
        retry_phrases = ['rate_limit', 'server_error', 'timeout', 'overloaded']
        return any(phrase in error_info.lower() for phrase in retry_phrases)