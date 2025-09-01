# Testing Standards

This document defines shared standards for writing and maintaining tests in this repo. It complements the repo guidelines and aims to keep tests fast, reliable, and meaningful.

## Test Types and Boundaries
- Unit tests: Validate a component in process, fast (<100ms each). May use fakes/mocks for external boundaries only (network, filesystem, GPU/ML libs, Qt GUI). Prefer in‑memory resources.
- Integration tests: Exercise multiple components together with realistic I/O (e.g., SQLite via temp dirs, real queues/threads). Keep deterministic; avoid network.
- E2E/GUI smoke: Optional, offscreen, minimal. Use `QT_QPA_PLATFORM=offscreen` and keep runtime short.

## Mocking Guidelines
- Prefer behavior over implementation. Assert observable outcomes, not specific internal calls.
- Mock only at boundaries:
  - External services (HTTP, OpenAI, HF, etc.).
  - Heavy/optional dependencies (torch, transformers, torchaudio) via `patch.dict(sys.modules, …)` inside test setup.
  - OS/FS only when costly or non‑deterministic; otherwise use temp dirs/files.
- Avoid global module mutation:
  - Do not write to `sys.modules` at import time. Use `patch.dict(sys.modules, mapping)` in `setUp` and stop in `tearDown`.
- Stdlib mocking (e.g., `os.path`, `sys`) should be rare and scoped. Prefer real FS + tempdirs unless simulating specific environment detection logic.

## Singletons and Global State
- Provide explicit seams for tests:
  - Add `reset_for_tests()` and/or `create_for_testing()` for singletons (e.g., `ThreadManager`, `FolderManager`).
  - Do not mutate private attributes of singletons in tests.
- Tests must not depend on prior test order or leftover state.

## Signals and Callbacks
- Do not monkey‑patch framework signal methods (e.g., `.emit`) on production objects.
- Prefer injectable signal adapters (objects with `emit(...)`) or connect APIs.
- For Qt‑less environments, use small signal shims or adapters with the same contract.

## Performance and Timeouts
- Keep unit tests under ~100ms on a typical CI runner.
- Large payloads: cap to ≤256KB unless specifically testing limits.
- Timeouts: prefer event‑driven waits; default to 0.2–0.5s with an env override (e.g., `TEST_TIMEOUT`).

## Behavior vs Implementation
- Favor black‑box assertions of public APIs. Minimize reliance on private helpers or internal structures.
- Verifying method calls is acceptable only when the call is the public contract (e.g., UI state setters). Prefer asserting final visible state when practical.

## Determinism and Isolation
- Use `tempfile` for FS; clean up in `tearDown`.
- Avoid shared mutable globals. Use fixtures/helpers to create fresh state per test.
- Seed randomness if used; avoid time‑dependent flakiness.

## Naming and Structure
- `test_*.py` files; descriptive test names with behavior focus.
- Document preconditions in docstrings or Given/When/Then comments when helpful.
- Mark integration tests clearly (naming or folder) to allow quick unit‑only runs.

## Tools
- Use `uv run python -m unittest discover` for the suite.
- GUI/Qt tests should set `QT_QPA_PLATFORM=offscreen` when applicable.

## When to Refactor Tests
- Excessive mocking indicates missing seams: add DI points (e.g., signal adapters, factories).
- Manual cleanup of singletons indicates missing reset hooks: add `reset_for_tests()`/`create_for_testing()`.
- Fragile tests tied to private internals: move to public API assertions, or add thin public probes.

