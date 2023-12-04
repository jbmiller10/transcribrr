# Transcribrr
Transcribrr is a straightforward python desktop application that transcribes local audio/video files or youtube videos and then summarizes/transforms the output using a variety of preset prompts via OpenAI's GPT large language models. 

<img src="https://github.com/jbmiller10/transcribrr/blob/Screens/screenshot2.png" alt="drawing" width="600"/>


## Features

- Transcribe audio from local video/audio files or YouTube URLs via a simple GUI application
- fast, accurate, local transcription with optional speaker detection (via the excellent [whisperx](https://github.com/m-bain/whisperX) library)
- GPT-4 for transcript processing & summarization
- Manageable transcription quality settings
- Preset prompt management for GPT processing

## Installation

### Prerequisites

Before installing the application, ensure you have the following dependencies:

- Python 3.10 or higher
- [Cuda 11.8 or higher](https://docs.nvidia.com/cuda/cuda-quick-start-guide/index.html) (optional, though highly recommended, for hardware acceleration. Requires a supported Nvidia GPU.)
- [ffmpeg](https://ffmpeg.org/download.html)

### Clone the Repository

Clone the repository to your local machine:

```bash
git clone https://github.com/jbmiller10/transcribrr.git
cd transcribrr
```

### Create a Virtual Environment

#### Windows
```bash
python -m venv venv
.\venv\Scripts\activate
```
#### MacOS/Linux
```bash
python -m venv venv
source venv/bin/activate
```

### Install Dependencies

To install the required dependencies, run the following command in your terminal:

```bash
pip install -r requirements.txt
```

#### Install Torch w/ Cuda (optional, though highly recommended, for hardware acceleration. Requires an Nvidia GPU and cuda toolkit)
```bash
pip3 install torch~=2.0.0 torchaudio~=2.0.0 --index-url https://download.pytorch.org/whl/cu118
```

### Usage

Run the main script to start the application:

```bash
python main.py
```

## Configuration

Before usage, configure the application with your Hugging Face Access Token (optional, required for speaker detection/diarization) and OpenAI API keys through the 'Settings' menu.
ll
You can also adjust transcription quality, GPT model selection, max tokens, temperature, speaker detection settings, and your preset GPT prompts.

### Speaker Detection/Diarization

To **enable Speaker Detection**, you will need a Huggingface access token (generate [here](https://huggingface.co/settings/tokens)) that you can set in the settings menu. Additionally, you will need to accept the usage terms for the following models while logged into your huggingface account: [Segmentation](https://huggingface.co/pyannote/segmentation) and [Speaker-Diarization](https://huggingface.co/pyannote/speaker-diarization).


## How to Use

1. Choose the mode of transcription (File Upload or YouTube URL).
2. If using File Upload, select your video/audio file using the "Open Audio/Video File" button.
3. If using the YouTube URL mode, paste the YouTube link into the corresponding field.
4. Click the "Start Transcription" button to begin processing.
5. After transcription, you can process the text with GPT-4 using the "Process with GPT-4" button after setting your prompts.
