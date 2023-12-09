from PyQt6.QtCore import QThread, pyqtSignal
import requests
import traceback

class GPT4ProcessingThread(QThread):
    update_progress = pyqtSignal(str)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, transcript, prompt_instructions, gpt_model, max_tokens, temperature, openai_api_key, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Simplified super() call
        self.transcript = transcript
        self.prompt_instructions = prompt_instructions
        self.gpt_model = gpt_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.openai_api_key = openai_api_key

    def run(self):
        try:
            self.update_progress.emit('GPT-4 processing started...')
            # Call the standalone function ask_openai from within the run method.
            result = self.ask_openai()
            self.completed.emit(result)
            self.update_progress.emit('GPT-4 processing finished.')
        except Exception as e:
            self.error.emit(str(e))
            traceback.print_exc()

    def ask_openai(self):
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
        print(response)
        return response.json().get('choices', [{}])[0].get('message', {}).get('content', '')