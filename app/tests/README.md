# Transcribrr Tests

This directory contains unit tests for the Transcribrr application. 

## Test Suite Overview

### Core Database Tests
- `test_database_manager.py` - Tests the thread-safe operation, queueing mechanism, transaction handling, signal emission, and callback execution of the DatabaseManager and its DatabaseWorker.
- `test_thread_safe_db.py` - Tests concurrent database operations to ensure no locking errors occur.

### Configuration Management Tests
- `test_config_manager.py` - Tests loading, saving, default handling, and CRUD operations for the ConfigManager.
- `test_prompt_manager.py` - Tests loading, saving, default handling, CRUD operations, and signal emissions for the PromptManager.

### Folder Management Tests
- `test_folder_manager.py` - Tests the logic for managing folder hierarchy and recording associations.
- `test_create_folder.py` - Tests the specific behavior of folder creation and ID retrieval.

### Recording Model Tests
- `test_recording_folder_model.py` - Tests the data storage, role assignment, and filtering logic of the RecordingFolderModel and RecordingFilterProxyModel.
- `test_filter_null_transcript.py` - Tests handling of null transcript values in filtering.

### File Operations Tests
- `test_atomic_rename.py` - Tests the atomicity of the file rename and database update process.
- `test_path_utils.py` / `test_path_utils_simple.py` - Tests path resolution and utilities.
- `test_recording_duplicates.py` - Tests detection and handling of duplicate recordings.

### Transcription Tests
- `test_transcription_chunking.py` - Tests the chunking logic for transcribing large audio files.

## Running Tests

To run all tests:
```
python -m unittest discover
```

To run a specific test file:
```
python -m unittest app.tests.test_database_manager
```

To run a specific test case:
```
python -m unittest app.tests.test_database_manager.TestDatabaseManager
```

To run a specific test method:
```
python -m unittest app.tests.test_database_manager.TestDatabaseManager.test_manager_enqueues_operations_correctly
```

## Test Patterns

The tests follow these general patterns:

1. **Mock external dependencies** - Database access, filesystem operations, network requests, and GUI components are mocked when appropriate.

2. **Use setUp and tearDown** - Each test class sets up its own test environment and cleans it up afterwards.

3. **Isolate tests** - Each test is independent of the others and can be run in isolation.

4. **Test both success and failure paths** - Tests cover both normal operation and error handling.

5. **Use temporary files and directories** - Tests that require file system operations use temporary files and directories.

6. **Handle asynchronous operations** - Tests for asynchronous code properly wait for operations to complete.

7. **Focus on internal logic** - Tests focus on the internal logic of components rather than their interaction with the UI.

## Headless/CI Tips

- Set `QT_QPA_PLATFORM=offscreen` to run Qt-dependent tests without a display.
- Wrap test runs with a process timeout to avoid hangs during development/CI:
  - Linux/macOS: `timeout 5m python -m unittest discover -v`
  - With uv: `timeout 5m uv run python -m unittest discover -v`

## Manual Tests

The `manual/` directory contains test scripts that need to be run manually to verify UI interactions, database operations, and error handling. These tests include visual feedback and require user interaction.

To run a manual test:
```
python -m app.tests.manual.test_name
```

For example:
```
python -m app.tests.manual.test_duplicate_file
```

### Available Manual Tests:

- **test_db_injection.py** - Tests the injection of a single DatabaseManager instance into FolderManager, verifying thread safety.
- **test_batch_inserts.py** - Tests handling of rapid batch inserts and queuing of dataChanged events during tree refreshes.
- **test_duplicate_file.py** - Tests surfacing database errors to the UI, particularly for duplicate file paths.
- **test_duplicate_guard.py** - Tests preventing phantom refreshes when duplicate file paths are attempted.
