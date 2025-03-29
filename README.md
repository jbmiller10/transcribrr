# Transcribrr

Transcribrr is a desktop application designed for converting audio into text and refining it using OpenAI's GPT models. It's a versatile tool that handles local audio or video files, YouTube videos through URL links, and recordings captured directly in the app. This is a personal project that I am continually developing in my spare time, so expect ongoing improvements.

![Transcribrr Screenshot](https://github.com/user-attachments/assets/b8336779-a554-424b-97ff-53e617bf7823)

## Features

- **Local Transcription**: Fast and accurate transcription using `whisperx` with optional speaker detection.
  - Alternatively, you may opt to use the OpenAI Whisper API.
- **GPT Processing**: Use OpenAI's GPT models for text processing, summarization, and refinement.
- **Transcription Management**: Adjust quality settings, manage preset prompts, and customize GPT processing parameters.
- **Multiple Input Options**: Support for local files, YouTube URLs, or direct recordings.
- **Recent Recordings**: Easily access and manage your previous transcriptions.
- **Text Editor**: Built-in rich text editor with formatting options for your transcripts.
- **Database Integration**: Improved storage and retrieval of transcriptions and settings.

## Installation

### Prerequisites

Ensure you have the following before installing the application:

- Python 3.10+
- [Cuda 11.8 or higher](https://docs.nvidia.com/cuda/cuda-quick-start-guide/index.html) (optional for GPU acceleration)
- [FFmpeg](https://ffmpeg.org/download.html)

### Clone the Repository

Clone the project repository to your local machine:

```bash
git clone https://github.com/jbmiller10/transcribrr.git
cd transcribrr
```

### Create a Virtual Environment

Create a virtual environment to manage dependencies:

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

#### Optional: Install Torch with Cuda for GPU

```bash
pip install torch~=2.0.0 torchaudio~=2.0.0 --index-url https://download.pytorch.org/whl/cu118
```

#### Install Required Packages

```bash
pip install -r requirements.txt
```

## Usage

To start the application, run:

```bash
python main.py
```

## Configuration

Before using Transcribrr, configure your OpenAI API keys through the 'Settings' menu. You can also adjust settings such as transcription quality, GPT model, max tokens, temperature, and manage your preset GPT prompts.

## How to Use

1. Select your transcription mode: File Upload, YouTube URL, or Direct Recording.
2. Upload a file or paste a YouTube URL into the app to begin.
3. Click "Start Transcription" to convert audio to text.
4. Utilize the "Process with GPT-4" button for refining transcripts with GPT settings.
5. Save and manage your transcriptions through the Recent Recordings panel.
6. Format and edit your transcripts using the built-in text editor.

## Project Status

This project is currently undergoing a major refactoring to improve:
- Database management with a dedicated DatabaseManager
- Service-oriented architecture with clear separation of concerns
- Enhanced UI components with better reusability
- Improved file and recording management

## Contributing

Contributions are welcome! Feel free to submit pull requests or open issues for bugs and feature requests.
