from PyQt6.QtCore import QThread, pyqtSignal
import requests
import traceback

class GPT4ProcessingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, transcript, prompt_instructions, gpt_model, max_tokens, temperature, openai_api_key, messages=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transcript = transcript
        self.prompt_instructions = prompt_instructions
        self.gpt_model = gpt_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.openai_api_key = openai_api_key
        self.messages = messages  # Accept custom messages

    def run(self):
        try:
            self.update_progress.emit('GPT-4 processing started...')
            if self.messages:
                result = self.ask_openai_with_messages()
            else:
                result = self.ask_openai()
            self.completed.emit(result)
            self.update_progress.emit('GPT-4 processing finished.')
        except Exception as e:
            self.error.emit(str(e))
            traceback.print_exc()

    def ask_openai(self):
        print(self.gpt_model)
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
            'Authorization': f'Bearer {self.openai_api_key}'
        }
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            json=data,
            headers=headers
        )
        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.status_code} {response.text}")
        response_data = response.json()
        return response_data.get('choices', [{}])[0].get('message', {}).get('content', '')

    def ask_openai_with_messages(self):
        print(self.gpt_model)
        data = {
            'messages': self.messages,
            'model': self.gpt_model,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature
        }
        print(data)
        headers = {
            'Authorization': f'Bearer {self.openai_api_key}'
        }
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            json=data,
            headers=headers
        )
        if response.status_code != 200:
            raise Exception(f"OpenAI API error: {response.status_code} {response.text}")
        response_data = response.json()
        print(response_data)
        return response_data.get('choices', [{}])[0].get('message', {}).get('content', '')