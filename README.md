# Transcribrr

<p align="center">
  <img src="https://github.com/user-attachments/assets/b8336779-a554-424b-97ff-53e617bf7823" alt="Transcribrr Screenshot" width="75%">
</p>

This is Transcribrr, a desktop tool I've been building for myself to turn audio into text and then clean it up using OpenAI's GPT models. It handles local audio/video files, YouTube links, and direct recordings from the microphone. I mostly use it for braindump-style brainstorming that I then have an LLM structure/organize so I'm able to refer back to it later.

It's primarily a **personal project** that I tinker with in my free time. If you happen to find it useful too, that's awesome! Just keep in mind it's developed by one person and might have rough edges.

## What it Can Do

*   **Transcribe Stuff:** Converts audio/video to text. You can use `whisperx` locally (faster, works offline, can detect speakers) or OpenAI's Whisper API (might be more accurate for some cases, needs internet/API key).
*   **Clean Up Text with AI:** Uses OpenAI's GPT models (like GPT-4o) to reformat, summarize, translate, or otherwise process the raw transcript based on prompts.
*   **Different Inputs:** Drop in local files, paste a YouTube URL, or record directly in the app.
*   **Manage Transcripts:** Keeps a list of recent recordings, lets you edit the text, and save your work.
*   **Settings:** You can tweak things like the transcription model, GPT settings, and manage custom prompts.

## Getting Started

**1. Installation (The Easy Way)**

The best way to try it out is using the pre-built installers. Grab the latest release from the [GitHub Releases](https://github.com/jbmiller10/transcribrr/releases) page:

*   **Windows:**
    *   `Transcribrr-windows-cpu-setup.exe` (CPU-only version)
    *   `Transcribrr-windows-cuda-setup.exe` (Needs an NVIDIA GPU for *much* faster local transcription. Bundled with CUDA Toolkit.)
*   **macOS:**
    *   `Transcribrr-macOS-*.dmg` (Download the DMG file)

**Important:** You'll likely still need **FFmpeg** installed on your system separately, as the app uses it for audio processing. You can usually get it from [ffmpeg.org/download.html](https://ffmpeg.org/download.html).

**2. API Key (Important!)**

To use the GPT processing features or the OpenAI Whisper API for transcription (if you opt to use the API for transcription rather than a local model,) you *need* an OpenAI API key.
*   Go to **Settings** within the app.
*   Enter your key in the "API Keys" tab. It's stored securely in your system's keychain/credential manager.
*   You can optionally add a HuggingFace token if you want to use speaker detection with local transcription.

**3. Using the App**

*   Choose your input method: File Upload, YouTube URL, or Direct Recording.
*   Once you have audio loaded (or recorded), hit "Start Transcription".
*   After transcription, you can use the "Process with GPT-4" button (or the other AI tools in the editor toolbar) to refine the text using the selected prompt.
*   Your recordings/transcripts show up in the left panel. Click one to load it into the editor.
*   Use the editor to make manual changes, format text, and save your progress.

## Manual Installation (If You Prefer)

If you want to run it from source:

**Prerequisites:**

*   Python >3.11,<3.12
*   [FFmpeg](https://ffmpeg.org/download.html) (needs to be in your system's PATH)
*   (Optional) NVIDIA GPU + [CUDA Toolkit](https://developer.nvidia.com/cuda-toolkit) (matching PyTorch's requirements, usually 11.8 or 12.1) for GPU acceleration.

**Steps:**

1.  **Clone:**
    ```bash
    git clone https://github.com/jbmiller10/transcribrr.git
    cd transcribrr
    ```
2.  **Set up a Virtual Environment:** (Recommended)
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate
    # macOS/Linux
    python -m venv venv
    source venv/bin/activate
    ```
3.  **Install Dependencies:**
    *   **(Optional) Install PyTorch with CUDA:** Find the correct command for your CUDA version on the [PyTorch website](https://pytorch.org/get-started/locally/). Example for CUDA 11.8:
        ```bash
        pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
        ```
    *   **Install other requirements:**
        ```bash
        pip install -r requirements.txt
        ```
4.  **Run:**
    ```bash
    python main.py
    ```
    

## Feedback & Ideas Welcome

If run into bugs or have ideas for improvements, feel free to:

*   **Open an Issue:** Report bugs or suggest features on the [GitHub Issues](https://github.com/jbmiller10/transcribrr/issues) page.
