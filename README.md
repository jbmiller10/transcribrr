## Features

- Transcribe audio from local video/audio files or YouTube URLs
- Audio extraction from video files
- local Transcription with optional 
- GPT-4 for transcript processing
- Manageable transcription quality settings
- Preset prompts management for GPT processing

## Installation

### Prerequisites

Before installing the application, ensure you have the following dependencies:

- Python 3.10 or higher
- Cuda 11.8 (for hardware acceleration)
- ffmpeg
- pyqt5

### Clone the Repository

Clone the repository to your local machine:

```bash
git clone https://github.com/jbmiller10/transcribrr.git
cd transcribrr
```

### Install Dependencies

To install the required dependencies, run the following command in your terminal:

```bash
pip install -r requirements.txt
```

### Install Torch w/ Cuda (optional, though recommended, for hardware acceleration)
```pip3 install torch~=2.0.0 torchaudio~=2.0.0 --index-url https://download.pytorch.org/whl/cu118```

### Usage

Run the main script to start the application:

```bash
python main.py
```

## Configuration

Before usage, configure the application with your Hugging Face Access Token (optional, required for speaker detection/diarization) and OpenAI API keys through the 'Settings' menu.

You can also adjust transcription quality, GPT model selection, max tokens, temperature, and speaker detection settings.

## How to Use

1. Choose the mode of transcription (File Upload or YouTube URL).
2. If using File Upload, select your video/audio file using the "Open Audio/Video File" button.
3. If using the YouTube URL mode, paste the YouTube link into the corresponding field.
4. Click the "Start Transcription" button to begin processing.
5. After transcription, you can process the text with GPT-4 using the "Process with GPT-4" button after setting your prompts.



---

For any questions, feature requests, or bug reports, feel free to create an issue on the repository or contact the maintainer directly.
