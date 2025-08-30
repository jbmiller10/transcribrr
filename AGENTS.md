# Repository Guidelines

## Project Structure & Module Organization
- Code: `app/` (Qt UI and logic). Key subpackages: `controllers/`, `services/`, `threads/`, `widgets/`, `models/`, `ui_utils/`.
- Entry points: `main.py` (dev launcher), `app/__main__.py` (packaged builds).
- Tests: `app/tests/` (unittest-style `test_*.py`).
- Assets: `icons/`, `preset_prompts.json`.
- Packaging: PyInstaller spec `transcribrr.spec` (Windows), Briefcase config in `pyproject.toml` (macOS). Windows installer scripts in `installer/`.

## Build, Test, and Development Commands
- Run locally: `python main.py`
- Install deps: `python -m pip install -r requirements.txt`
- Unit tests: `python -m unittest discover`
  - Example single test: `python -m unittest app.tests.test_busy_guard`
- Lint: `flake8 .` (syntax/errors enforced in CI)
- Type check: `mypy --no-strict-optional app/controllers app/widgets app/models`
- Package (Windows): `pyinstaller transcribrr.spec --noconfirm`
- Package (macOS): `briefcase create macOS && briefcase build macOS && briefcase package macOS`

## Coding Style & Naming Conventions
- Python 3.11; 4‑space indentation; UTF‑8.
- Use type hints where practical; keep mypy clean in checked dirs.
- Module naming: Qt widgets in `PascalCase` files (e.g., `MainWindow.py`); utilities in `snake_case` (e.g., `db_utils.py`).
- Tests: `test_*.py` under `app/tests/`.
- Logging: prefer `logging.getLogger("transcribrr")`; avoid `print()` in app code.

## Testing Guidelines
- Framework: `unittest`. Focus unit tests on non‑GUI logic; GUI tests may be skipped in CI.
- Headless hint (Qt): `QT_QPA_PLATFORM=offscreen` when needed.
- Keep tests deterministic and fast; mock network/FS/LLM calls.

## Commit & Pull Request Guidelines
- Commits: concise, imperative (“Refactor main window”), reference issues/PRs (e.g., `(#35)`).
- PRs: clear description, link issues, include screenshots for UI changes, list notable decisions.
- CI must pass: run `flake8`, `mypy`, and unit tests locally before opening.

## Security & Configuration Tips
- Never hard‑code or log secrets. Redaction is enforced via `app/secure.py` (`SensitiveLogFilter`).
- Store API keys via OS keyring (see `app/secure.py`), not in source or `.env` committed files.
- Ensure FFmpeg is available in PATH; see startup checks in `app/utils.py`.

