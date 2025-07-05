# Transcribrr

<p align="center">
  <img src="https://github.com/user-attachments/assets/b8336779-a554-424b-97ff-53e617bf7823" alt="Transcribrr Screenshot" width="75%">
</p>

This is Transcribrr, a desktop tool I've been building for myself to turn audio into text and then clean it up using OpenAI's GPT models. It handles local audio/video files, YouTube links, and direct recordings from the microphone. I mostly use it for braindump-style brainstorming that I then have an LLM structure/organize so I'm able to refer back to it later. 

It's primarily a **personal project** that I tinker with in my free time. If you happen to find it useful too, that's awesome! Just keep in mind it's developed by one person and might have rough edges. It is provided as-is.

## What it Can Do

*   **Transcribe Stuff:** Converts audio/video to text. You can use `whisperx` locally (faster, works offline, can detect speakers) or OpenAI's Whisper API (might be more accurate for some cases, needs internet/API key).
*   **Clean Up Text with AI:** Uses OpenAI's GPT models (like GPT-4o) to reformat, summarize, translate, or otherwise process the raw transcript based on prompts.
*   **Different Inputs:** Drop in local files, paste a YouTube URL, or record directly in the app.
*   **Manage Transcripts:** Keeps a list of recent recordings, lets you edit the text, and save your work.
*   **Settings:** You can tweak things like the transcription model, GPT settings, and manage custom prompts.

## Getting Started


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
