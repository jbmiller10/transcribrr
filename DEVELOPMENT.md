# Development Setup

This project uses `uv` for Python dependency management and virtual environments.

## Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager

## Quick Start

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or on macOS:
```bash
brew install uv
```

### 2. Clone the repository

```bash
git clone https://github.com/jbmiller10/transcribrr.git
cd transcribrr
```

### 3. Install dependencies

For basic development (minimal dependencies):
```bash
uv sync
```

For development with all optional dependencies:
```bash
uv sync --all-extras
```

For specific feature sets:
```bash
# GUI development
uv sync --extra gui

# Audio processing
uv sync --extra audio

# Machine learning features
uv sync --extra ml

# Development tools
uv sync --extra dev
```

Note: Some extras require system dependencies:
- `audio`: Requires PortAudio (`sudo apt-get install portaudio19-dev` on Ubuntu)
- `gui`: Requires Qt libraries
- `ml`: Large downloads (PyTorch, etc.)

## Running Tests

Run the test suite:
```bash
uv run python -m unittest discover app/tests -v
```

Run specific test files:
```bash
uv run python -m unittest app.tests.test_secure -v
```

## Code Quality

Run linting:
```bash
uv run flake8 app
```

Format code:
```bash
uv run black app
```

Type checking:
```bash
uv run mypy app
```

## Project Structure

```
transcribrr/
├── app/                    # Main application code
│   ├── controllers/        # Business logic controllers
│   ├── models/            # Data models
│   ├── tests/             # Unit tests
│   └── threads/           # Background processing threads
├── pyproject.toml         # Project configuration and dependencies
├── uv.lock               # Locked dependency versions
└── .github/workflows/     # CI/CD pipelines
```

## Dependency Groups

- **Core**: Minimal dependencies for API functionality
- **gui**: PyQt6 for desktop application
- **audio**: Audio recording and processing
- **ml**: Machine learning models for local transcription
- **docs**: Document generation (Word, PDF)
- **dev**: Development and testing tools
- **build**: Application packaging tools

## CI/CD

GitHub Actions automatically runs tests on:
- Push to main branch
- Pull requests
- Manual workflow dispatch

The CI uses the same `uv` setup for consistency.

## Adding Dependencies

Add a runtime dependency:
```bash
uv add requests
```

Add a development dependency:
```bash
uv add --dev pytest
```

Add to a specific extra group:
```bash
uv add --extra audio sounddevice
```

## Troubleshooting

### Import errors in tests
The project uses fallback imports for optional dependencies. Tests should run without PyQt6 or torch installed.

### System dependencies
Some packages require system libraries:
- PyAudio: `sudo apt-get install portaudio19-dev`
- PyQt6: May require Qt runtime libraries

### Requirements file
The `requirements.txt` file is now UTF-8 encoded and aligns with the project’s Python packaging. Prefer `uv sync` (from `pyproject.toml`) in CI and local dev; `pip install -r requirements.txt` remains available for environments that rely on a requirements file.
