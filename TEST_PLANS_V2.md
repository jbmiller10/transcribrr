# Test Suite Audit (V2)

Scope: All Python tests under `app/tests/` reviewed for the following anti‑patterns:
1) Mockery, 2) Generous Leftovers, 3) Dodger, 4) Free Ride, 5) Conjoined Twins, 6) Happy Path Only, 7) Slow Poke, 8) Giant Tests, 9) Testing Implementation Details, 10) Leaky Mocks and Data.

Summary: The suite is predominantly behavior‑focused with solid negative‑path coverage. Main risks are: a) a few heavy payload/timeout choices that can slow runs, b) one global module stubbing that can leak across files, and c) a small number of assertions coupled to implementation details or private helpers.

---

## app/tests/test_busy_guard.py

- Classification: Unit, behavior‑focused (no real Qt; test doubles).
- Strengths: Broad coverage of UI busy state, spinner handling, progress dialog lifecycle, cancel behavior, exception cleanup, idempotency, and signal logging; covers KeyboardInterrupt/SystemExit paths.
- Findings:
  - Dodger: `test_handles_empty_ui_element_list` asserts `ui_busy is False or isinstance(..., bool)` inside the context, which doesn’t clearly validate expected behavior and is effectively a tautology. Consider clarifying or removing that in‑context assertion.
  - Testing Implementation Details: Asserts on `feedback.progress_states` and `is_open` via the stateful test double. This is acceptable because it’s a test helper abstraction, not production internals.
- Recommendations:
  - Replace the ambiguous assertion with an explicit expectation (e.g., UI not marked busy when no elements provided) and keep the post‑context assertion.
  - Prefer observable interactions through the BusyGuard public behavior (status/progress calls recorded via doubles) over inspecting helper-internal dicts where possible.

## app/tests/test_database_manager_behavior.py

- Classification: Behavior/Integration (real SQLite file via temp user data dir; worker thread involved).
- Strengths: Good breadth: create/update/delete, duplicate path handling, invalid tuples, NOT NULL violations, update/delete on missing IDs, empty searches, unicode, and literal SQL‑injection strings; uses temp dir + cache reset to isolate state; restores env/caches in tearDown.
- Findings:
  - Conjoined Twins: This is integration‑level by design (real DB + threaded worker). Acceptable, but should be clearly separated or marked so unit runs stay snappy.
  - Slow Poke: Relies on thread/event callbacks with `DEFAULT_TIMEOUT = 0.5`. If a callback fails, tests can hang for 0.5s per step. Normal execution should be fast, but failures inflate runtime.
  - Testing Implementation Details: Several assertions use direct SQL queries for verification. Functional, but couples tests to schema details.
- Recommendations:
  - Mark as integration (e.g., filename suffix `_integration.py` already used elsewhere; alternatively, group in an `integration` package or use a test label/env guard).
  - Consider reducing default wait to 0.2–0.3s and allow override with an env var (mirroring the approach in `test_folder_manager_behavior`).
  - Where possible, verify via DatabaseManager API callbacks instead of direct SQL; use direct SQL sparingly for checks not exposed by the API.

## app/tests/test_database_worker_integration.py

- Classification: Integration (in‑memory SQLite).
- Strengths: Exercises worker queue loop deterministically, real SQL, signal emissions, malformed operations, sequential duplicate handling, insert/update/select paths, and dataChanged semantics. Nicely isolates via in‑memory DB; no filesystem coupling.
- Findings:
  - Slow Poke: `test_extremely_large_data_reasonable` inserts ~1MB strings. This can push test runtime over typical unit thresholds (>100ms).
- Recommendations:
  - Reduce payload to ~128–256KB; still meaningful for boundary, faster to run.
  - Consider marking this single case as “slow” or moving to an integration/soak subset.

## app/tests/test_db_utils_unit.py

- Classification: Unit (in‑memory SQLite) with targeted mocking for error paths.
- Strengths: Validates CRUD, constraints, ignored fields, injection literals treated as data, pending date replacement, legacy schema tolerance, special/path characters, and connection/pragma behaviors. Mocks are used appropriately for I/O/error cases.
- Findings:
  - Slow Poke: `test_create_recording_large_fields` uses ~1MB text for raw/processed fields. Potentially slow on CI.
- Recommendations:
  - Reduce to ~256KB while keeping the intent; no behavioral loss.

## app/tests/test_feedback_manager.py

- Classification: Unit (Qt‑like mocks), behavior‑focused.
- Strengths: Covers UI busy/restore, operation tracking, progress lifecycle, spinner integration, resilience to element API quirks/exceptions, comprehensive cleanup, spinner toggling, and warning paths.
- Findings:
  - Testing Implementation Details (minor): Some assertions depend on the last call in `setEnabled.call_args_list`. This couples to call ordering but remains acceptable for this UI state manager.
- Recommendations:
  - Keep tests focused on observable behavior; minimize reliance on specific call ordering unless it’s a guaranteed contract.

## app/tests/test_folder_manager_behavior.py

- Classification: Behavior/Integration (real DB + DatabaseManager; FolderManager singleton).
- Strengths: Hierarchy creation, rename propagation, recording associations, delete + cascade, queries, export/import cycle, and singleton/edge cases with explicit tearDown cleanup; isolates state via temp dir + cache reset.
- Findings:
  - Testing Implementation Details: Tests reset private class attributes (`FolderManager._instance`, `._db_manager_attached`). Effective but brittle across refactors.
  - Slow Poke: `_Wait.wait` defaults to 3.0s (env‑overridable). Failures can significantly slow the suite.
- Recommendations:
  - Provide a public `reset_for_tests()` or context manager on FolderManager to avoid touching private internals.
  - Lower default wait to ~0.5s and keep the env override for rare slow environments.

## app/tests/test_path_utils.py

- Classification: Unit (OS/sys mocking), behavior.
- Strengths: Exercises dev/pyinstaller/py2app path resolution, absolute vs relative joining, unicode and traversal strings, and logging. Mocking contained via context managers; no global leakage.
- Findings: None significant.
- Recommendations: None.

## app/tests/test_recording_model.py

- Classification: Unit, model behavior and validation.
- Strengths: Creation, equality, derived values, boundary/edge cases for duration/date/path, transcript updates with timestamping, status semantics, size estimation bounds, database row conversions, and error paths.
- Findings:
  - Testing Implementation Details: Directly tests `_format_seconds` (private). Low risk, but can break if internals refactor without changing public behavior.
- Recommendations:
  - Prefer validating via `get_display_duration()` for public behavior. Keeping a small, explicit private‑helper test is acceptable if it adds clarity.

## app/tests/test_thread_manager.py

- Classification: Unit (custom signal shim; no Qt runtime).
- Strengths: Singleton behavior, registration/auto‑unregister, duplicate registration warnings, cancel/wait semantics, missing `cancel()` warnings, mutation during cancel, and exception propagation from `isRunning`/`wait`. Clean setup/teardown ensures isolation.
- Findings: None significant.
- Recommendations: None.

## app/tests/test_transcription_service.py

- Classification: Unit with heavy dependency stubbing; mixed public and private method tests.
- Strengths: Wide coverage across API/local/MPS/CUDA paths, input validation, error wrapping (permissions, directory, invalid format, corrupted audio, API timeout/auth), speaker diarization labeling/formatting, and device selection logic. Makes good use of lightweight fakes and `ModelManager` stubbing.
- Findings:
  - Leaky Mocks and Data: `_ensure_stubbed_heavy_modules()` injects stubs into `sys.modules` at import time, globally affecting the interpreter. This can leak into other tests importing the same modules later.
  - Testing Implementation Details: Exercises private methods (`_transcribe_locally`, `_add_speaker_detection`, `_transcribe_with_api`). Useful for thoroughness but increases coupling to internals.
- Recommendations:
  - Isolate heavy module stubs using `patch.dict(sys.modules, {...})` in `setUp` and restore in `tearDown`, or use import‑time patching within a context when importing the service. Alternatively, rework the service to allow dependency injection (e.g., diarization/pipeline factories) so tests can pass fakes without global module mutations.
  - Keep private‑method tests but ensure public `transcribe_file` paths also cover the same branches end‑to‑end; favor public API where feasible.

---

## Suite‑Wide Observations

- Performance Risk (Slow Poke):
  - Large payloads (~1MB) in two tests and generous waits (0.5–3.0s) on failure can slow CI. Normal runs are fast, but failures become costly to triage.
  - Action: Reduce payload sizes to ≤256KB; lower default waits (0.2–0.5s) and keep env overrides.

- Integration vs Unit Separation (Conjoined Twins):
  - Several behavior tests intentionally use real SQLite. This is good coverage but should be clearly identified and optionally excluded from quick unit runs.
  - Action: Use naming (`*_integration.py`) or a folder tag; document how to include/exclude in local/CI runs.

- Global Stubbing (Leaky Mocks and Data):
  - Avoid module‑level mutation of `sys.modules` that persists across tests.
  - Action: Wrap in `patch.dict` contexts or provide dependency injection hooks to pass fakes per test.

- Implementation Coupling:
  - A few tests assert on helper internals or private functions.
  - Action: Prefer public APIs for behavior, keep private helper tests minimal and well‑justified.

---

## Concrete Fixes (Proposed PR check‑list)

- test_busy_guard.py
  - Replace ambiguous assertion in `test_handles_empty_ui_element_list` with explicit, behavior‑driven checks.

- test_database_manager_behavior.py
  - Lower default `_Wait` timeout and expose env override (align with `test_folder_manager_behavior`).
  - Prefer API‑level verification where possible; reserve direct SQL for checks not exposed by the API.

- test_database_worker_integration.py
  - Reduce `big` payload to 256KB, or mark the test as slow/integration.

- test_db_utils_unit.py
  - Reduce large text payload to <=256KB.

- test_folder_manager_behavior.py
  - Add a public `FolderManager.reset_for_tests()` to avoid touching private attributes. Lower default wait to ~0.5s.

- test_transcription_service.py
  - Move module stubbing into `setUp`/`tearDown` using `patch.dict(sys.modules, {...})` to prevent cross‑file leakage. Keep public API coverage alongside private method tests.

---

## Execution Notes

- CI/Local: Prefer `QT_QPA_PLATFORM=offscreen` for any GUI‑touching tests. Use `uv run python -m unittest discover` for the full suite; consider a make‑target or docs note for unit‑only vs integration runs.
- No test observed to create persistent on‑disk state beyond tempdirs/files that are cleaned in tearDown.
