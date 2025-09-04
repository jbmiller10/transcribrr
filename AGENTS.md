# Repository Guidelines

## Project Structure & Module Organization
- Code lives in `app/` (Qt UI + logic). Key subpackages: `controllers/`, `services/`, `threads/`, `widgets/`, `models/`, `ui_utils/`.
- Entry points: `main.py` (dev launcher) and `app/__main__.py` (packaged builds).
- Tests: `app/tests/` (unittest-style `test_*.py`).
- Assets: `icons/`, `preset_prompts.json`.
- Packaging: PyInstaller spec `transcribrr.spec` (Windows), Briefcase config in `pyproject.toml` (macOS). Windows installer scripts in `installer/`.

## Build, Test, and Development Commands (uv-first)
- Always use `uv` for environment, installs, and running commands. Avoid `pip`, `virtualenv`, or bare `python`.
- Use `uv run` for project tools; `uvx` for ad‑hoc tools not in deps.
```bash
# Create/refresh venv and install deps (uses pyproject.toml + uv.lock)
uv venv
uv sync

# Run locally (dev)
uv run python main.py

# Unit tests (all / single)
uv run python -m unittest discover
uv run python -m unittest app.tests.test_busy_guard

# Lint and type-check
uv run flake8 .          # or: uvx flake8 .
uv run mypy --no-strict-optional app/controllers app/widgets app/models

# Package (Windows/macOS)
uv run pyinstaller transcribrr.spec --noconfirm
uv run briefcase create macOS && uv run briefcase build macOS && uv run briefcase package macOS
```

## Coding Style & Naming Conventions
- Python 3.11; 4‑space indentation; UTF‑8.
- Use type hints where practical; keep mypy clean in checked dirs.
- Naming: Qt widgets in PascalCase files (e.g., `MainWindow.py`); utilities in `snake_case` (e.g., `db_utils.py`); tests `test_*.py`.
- Logging: use `logging.getLogger("transcribrr")`; avoid `print()` in app code.

## Testing Guidelines
- Framework: `unittest`. Keep tests deterministic and fast; mock network/FS/LLM calls.
- GUI: may be skipped in CI; set `QT_QPA_PLATFORM=offscreen` when needed.
- Place new tests under `app/tests/` and follow `test_*.py` naming.

## Commit & Pull Request Guidelines
- Commits: concise, imperative; reference issues/PRs (e.g., `Refactor main window (#35)`).
- PRs: clear description, link issues, include screenshots for UI changes, and list notable decisions.
- CI must pass: run `flake8`, `mypy`, and unit tests locally before opening.

## Security & Configuration Tips
- Never hard‑code or log secrets. See `app/secure.py` (`SensitiveLogFilter`). Store API keys via OS keyring.
- Ensure FFmpeg is available in `PATH`; startup checks live in `app/utils.py`.

## User Data Paths
- Use `get_user_data_dir()` (root) and `get_recordings_dir()` for recordings.
- Do not use `os.getcwd()` or absolute paths like `/Recordings`.
- Ensure parent dirs exist: `os.makedirs(os.path.dirname(path), exist_ok=True)`.
