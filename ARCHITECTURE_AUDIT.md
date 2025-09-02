# Transcribrr Architecture Audit (2025‑09‑02)

This document captures a full‑repo architecture review of non‑test code, with issues ranked by criticality and expected ROI to fix. It focuses on runtime behavior, boundaries, testability, and maintainability.

## Critical Issues (Fix First)

- get_api_key returns fake keys: `app/secure.py`
  - Impact: Always returns `"fake-api-key"` for OPENAI/HF keys in all environments, breaking real requests and hiding credential problems.
  - Fix: Only return fake keys in tests via an explicit guard (e.g., `TRANSCRIBRR_TESTING=1`) or remove entirely and rely on DI/mocking in tests; otherwise read from OS keyring.
  - ROI: Very high (1–2h). Unblocks real API use and avoids confusing failures.

- Duplicated entrypoint logic: `app/__main__.py`
  - Impact: `run_application` (and `cleanup_application`) logic appears twice, inviting drift and subtle startup/exit bugs.
  - Fix: Keep one implementation; delete duplicate.
  - ROI: Very high (0.5–1h). Removes a class of hard‑to‑trace issues.

- Service boundary breach (thread calls service internals): `TranscriptionThread` → `TranscriptionService._transcribe_with_api`
  - Impact: Thread calls a private method and implements API chunking locally; duplicates service concerns and increases coupling.
  - Fix: Move chunked‑API flow into `TranscriptionService` as a public code path; make `transcribe_file` fully own method selection and size limits.
  - ROI: High (0.5–1 day). Centralizes transcription logic; simplifies threads.

- Redaction coverage in error logs
  - Impact: Redaction filter covers `record.msg`/`args`, but many places log stack traces (`exc_info=True`) whose text can still include sensitive substrings.
  - Fix: Wrap exception strings with `secure.redact(...)` before logging or avoid echoing raw exception strings alongside `exc_info`; ensure the `SensitiveLogFilter` is attached once, very early.
  - ROI: High (1–2h). Strong security hygiene; low risk.

## High Priority

- Heavy imports at module import time: `torch`, `transformers`, `pyannote`, `torchaudio`
  - Impact: Slower startup, brittle headless/CI behavior, higher memory footprint.
  - Fix: Lazy import heavy libs inside the functions that use them; prune unused imports; show clear guidance if missing at runtime.
  - ROI: High (1–3h). Faster startup, fewer env issues.

- FFmpeg checks duplicated: `ensure_ffmpeg_available` vs `check_ffmpeg`
  - Impact: Divergent behavior and PATH mutations across places.
  - Fix: Consolidate into one resolver that returns `(ok, message, path)`, used in a single startup check.
  - ROI: High (1–2h). Reduces surprises/support load.

- User data dir in dev mode: `app/constants.get_user_data_dir`
  - Impact: Dev runs write to repo root (`logs/`, DB, config), causing clutter and permission issues.
  - Fix: Always use `appdirs.user_data_dir` unless `TRANSCRIBRR_USER_DATA_DIR` is set; optionally migrate existing files once.
  - ROI: High (1–2h). Cleaner dev ergonomics.

- Thread cancellation realism
  - Impact: `requestInterruption()` does not stop HuggingFace inference; terminate fallback is harsh.
  - Fix: Process in smaller chunks with periodic cancel checks; propagate cancellation tokens into the service; keep terminate as last resort.
  - ROI: High (1–2 days). Better UX and shutdown behavior.

- Bootstrap duplication (config/presets): `db_utils.ensure_database_exists` vs `__main__`
  - Impact: Multiple places initialize defaults → drift risk.
  - Fix: Create a single Bootstrap service to seed DB/config/prompts and call it during startup.
  - ROI: Med‑High (2–4h). Simplifies startup path.

## Medium Priority

- Logging setup in two places: `app/utils.py` and `app/__main__.py`
  - Impact: Competing `basicConfig` calls are fragile; handler duplication is easy.
  - Fix: Centralize in `logging_utils.configure_logging()`; call it at app start.
  - ROI: Medium (1–2h). Predictable logs.

- Singleton proliferation vs DI
  - Impact: Singletons (`ThemeManager`, `ResponsiveUIManager`, `ThreadManager`, `ModelManager`, `ConfigManager`, `PromptManager`) ease use but entangle global state and tests.
  - Fix: Keep singletons for runtime but allow constructor injection in controllers/threads; resolve instances at UI boundary.
  - ROI: Medium (1–2 days incremental). Improves testability/decoupling.

- Database worker complexity: `app/DatabaseManager.py`
  - Impact: Large op switch with custom callback ID plumbing and duplicated error handling.
  - Fix: Map op types to small handler functions; wrap common try/except via a decorator; unify callback registry keyed by op IDs.
  - ROI: Medium (1–2 days). Stability, readability.

- UI/Controller coupling: `MainTranscriptionWidget`
  - Impact: View orchestrates workflows (busy guards, controller calls, DB writes). Harder to test and evolve.
  - Fix: Push more orchestration into controllers/services; UI subscribes to status updates.
  - ROI: Medium (incremental). Clearer separation of concerns.

- Model cache and memory management: `ModelManager.clear_cache()`
  - Impact: Always calls `torch.cuda.empty_cache()`; repeated device queries across modules.
  - Fix: Only empty when CUDA active; expose read‑only getters for device/memory from a single place.
  - ROI: Medium (1–2h). Small but clean.

- Startup UX with `StartupThread`
  - Impact: Mixed logs and warnings for missing deps; no single readiness object.
  - Fix: Return structured readiness with actionable guidance; consider fail‑fast for hard prereqs.
  - ROI: Medium (2–4h). Better first‑run experience.

## Lower Priority / Cleanups

- Remove unused imports and tighten surfaces (e.g., `requests`, `numpy`, `torchaudio.functional` where unused).
- Normalize constants/magic numbers (e.g., API upload limit 25MB → `constants.py`).
- Avoid writing to repo root on dev runs; assure log rotation consistently.
- Consider splitting `TextEditor` responsibilities (export/FindReplace) into helpers.

## Suggested Order of Work

1) Fix `secure.get_api_key` behavior; deduplicate `app/__main__.py` logic.
2) Centralize all transcription decisions/flows in `TranscriptionService` (local/API/chunking) with lazy imports.
3) Unify FFmpeg checks and logging setup; ensure redaction coverage for exception text.
4) Switch dev user data dir to `appdirs` and (optionally) migrate existing local artifacts once.
5) Improve cancellation granularity in local inference; chunk/poll for cancellation.
6) Gradually refactor DB worker and reduce singleton coupling by allowing DI.

## Strengths & Good Directions

- Qt shims/stubs keep modules import‑safe in headless CI; solid approach.
- `ThreadManager` registry with auto‑unregister is clean and helpful.
- Centralized `ConfigManager` & `PromptManager` with signals: good foundation.
- Error handling utilities and redaction exist; extend to cover all exception text.

## Notes by File/Area

- `app/secure.py`: Fix test‑only fake key behavior; keep redaction helpers; prefer explicit env gating for tests.
- `app/__main__.py`: Remove duplicate `run_application`/`cleanup_application`; keep one startup thread path.
- `app/services/transcription_service.py`: Move API chunking/public API handling here; lazy import heavy deps inside methods; remove unused imports.
- `app/threads/*`: Keep threads thin; use service for all operations; poll for cancellations at safe points.
- `app/utils.py`: Consolidate FFmpeg checking; avoid double logger configuration; keep GPU info shim but isolate torch references.
- `app/constants.py`: Use `appdirs` for user data dir in all modes unless overridden by env; move API upload limit here.
- `app/DatabaseManager.py`: Split op handlers; unify error logging; simplify callback binding.

---

If you want, I can implement the critical items (secure key retrieval, `__main__` dedup, transcription service boundary, lazy heavy imports) in a focused PR next.

