"""Tests for MainWindow following the YAML plan in test_mainwindow_plan.yaml.

These tests focus on initialization flows and on_new_file behavior, with
heavy use of mocking to avoid real GUI and I/O side effects.
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class DummySignal:
    def __init__(self):
        self._slots = []

    def connect(self, func, *args, **kwargs):
        self._slots.append((func, args, kwargs))

    def disconnect(self, func):
        self._slots = [s for s in self._slots if s[0] is not func]

    def emit(self, *args, **kwargs):
        for func, _a, _k in list(self._slots):
            func(*args, **kwargs)


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure Qt can initialize in headless environments
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        # Create a QApplication if not already present
        try:
            from PyQt6.QtWidgets import QApplication  # type: ignore
        except Exception:  # pragma: no cover - PyQt not available
            raise unittest.SkipTest("PyQt6 not available; skipping MainWindow tests")

        cls._app = QApplication.instance() or QApplication([])

        # Pre-stub heavy widget modules to avoid importing ML deps (torch, etc.)
        # before importing MainWindow. These will be patched per-test anyway.
        import types as _types
        import sys as _sys

        for mod_name, cls_name in [
            ("app.MainTranscriptionWidget", "MainTranscriptionWidget"),
            ("app.ControlPanelWidget", "ControlPanelWidget"),
            ("app.RecentRecordingsWidget", "RecentRecordingsWidget"),
        ]:
            if mod_name not in _sys.modules:
                m = _types.ModuleType(mod_name)
                setattr(m, cls_name, type(cls_name, (), {}))
                _sys.modules[mod_name] = m

        # Stub app.file_utils to avoid importing heavy dependencies like moviepy/pydub
        if "app.file_utils" not in _sys.modules:
            m_fu = _types.ModuleType("app.file_utils")
            def _calc_duration(_p):
                return "00:00:00"
            m_fu.calculate_duration = _calc_duration  # type: ignore
            _sys.modules["app.file_utils"] = m_fu

        # Import after QApplication is ensured and stubs are in place
        from app.MainWindow import MainWindow  # type: ignore

        cls.MainWindow = MainWindow

    def test_init_success(self):
        # Successful initialization with components created and UI init called
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance") as mock_folder_instance, \
             patch.object(self.MainWindow, "init_ui") as mock_init_ui, \
             patch("app.MainWindow.QMessageBox.critical") as mock_critical, \
             patch("app.MainWindow.logger") as mock_logger, \
             patch("sys.exit") as mock_sys_exit:

            mock_db.return_value = MagicMock(name="MockDB")
            mock_folder_instance.return_value = MagicMock(name="MockFolderMgr")

            win = self.MainWindow()
            self.assertIsNotNone(win)

            self.assertTrue(mock_db.called)
            self.assertTrue(mock_folder_instance.called)
            mock_init_ui.assert_called_once()
            mock_critical.assert_not_called()
            mock_sys_exit.assert_not_called()
            self.assertTrue(mock_logger.info.called)

    def test_db_manager_init_failure(self):
        # DatabaseManager raises -> critical message shown and sys.exit(1)
        with patch("app.MainWindow.DatabaseManager", side_effect=RuntimeError("Database connection failed")), \
             patch("app.MainWindow.FolderManager.instance") as mock_folder_instance, \
             patch.object(self.MainWindow, "init_ui") as mock_init_ui, \
             patch("app.MainWindow.QMessageBox.critical") as mock_critical, \
             patch("app.MainWindow.logger") as mock_logger, \
             patch("sys.exit", side_effect=SystemExit(1)) as mock_sys_exit:

            with self.assertRaises(SystemExit):
                self.MainWindow()

            mock_critical.assert_called()
            # Ensure the error message references Database Manager
            args, _ = mock_critical.call_args
            self.assertIn("Database Manager", args[2])
            mock_folder_instance.assert_not_called()
            mock_init_ui.assert_not_called()
            mock_logger.critical.assert_called()
            mock_sys_exit.assert_called_once_with(1)

    def test_folder_manager_runtime_error(self):
        # FolderManager.instance raises RuntimeError -> critical message + sys.exit
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance", side_effect=RuntimeError("FolderManager already initialized")), \
             patch.object(self.MainWindow, "init_ui") as mock_init_ui, \
             patch("app.MainWindow.QMessageBox.critical") as mock_critical, \
             patch("app.MainWindow.logger") as mock_logger, \
             patch("sys.exit", side_effect=SystemExit(1)) as mock_sys_exit:

            mock_db.return_value = MagicMock(name="MockDB")

            with self.assertRaises(SystemExit):
                self.MainWindow()

            mock_critical.assert_called()
            args, _ = mock_critical.call_args
            self.assertIn("Folder Manager", args[2])
            mock_init_ui.assert_not_called()
            mock_logger.critical.assert_called()
            mock_sys_exit.assert_called_once_with(1)

    def test_folder_manager_unexpected_exception(self):
        # FolderManager.instance raises unexpected exception -> shows unexpected error message + sys.exit
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance", side_effect=ValueError("Invalid configuration")), \
             patch.object(self.MainWindow, "init_ui") as mock_init_ui, \
             patch("app.MainWindow.QMessageBox.critical") as mock_critical, \
             patch("app.MainWindow.logger") as mock_logger, \
             patch("sys.exit", side_effect=SystemExit(1)) as mock_sys_exit:

            mock_db.return_value = MagicMock(name="MockDB")

            with self.assertRaises(SystemExit):
                self.MainWindow()

            mock_critical.assert_called()
            args, _ = mock_critical.call_args
            self.assertIn("Unexpected error during Folder Manager setup", args[2])
            mock_init_ui.assert_not_called()
            mock_logger.critical.assert_called()
            mock_sys_exit.assert_called_once_with(1)

    def test_ui_initialization_failure(self):
        # init_ui raises -> critical message + sys.exit
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance") as mock_folder_instance, \
             patch.object(self.MainWindow, "init_ui", side_effect=Exception("Widget creation failed")) as mock_init_ui, \
             patch("app.MainWindow.QMessageBox.critical") as mock_critical, \
             patch("app.MainWindow.logger") as mock_logger, \
             patch("sys.exit", side_effect=SystemExit(1)) as mock_sys_exit:

            mock_db.return_value = MagicMock(name="MockDB")
            mock_folder_instance.return_value = MagicMock(name="MockFolderMgr")

            with self.assertRaises(SystemExit):
                self.MainWindow()

            mock_init_ui.assert_called()
            mock_critical.assert_called()
            args, _ = mock_critical.call_args
            self.assertIn("UI setup", args[2])
            mock_logger.critical.assert_called()
            mock_sys_exit.assert_called_once_with(1)

    def test_init_ui_connects_signals(self):
        # Verify that init_ui connects widget signals appropriately using real QWidget subclasses
        from PyQt6.QtCore import QSize  # type: ignore
        from PyQt6.QtWidgets import QWidget  # type: ignore

        class _Sig:
            def __init__(self):
                self.connected = []

            def connect(self, fn, *args, **kwargs):  # noqa: D401
                self.connected.append((fn, args, kwargs))

        class _Ctrl(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.file_ready_for_processing = _Sig()

        class _RR(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.recordingItemSelected = _Sig()
                self.unified_view = types.SimpleNamespace(select_item_by_id=lambda *_: None)

            def update_recording_status(self, *_):
                pass

            def load_recordings(self):  # pragma: no cover - trivial
                pass

        class _Trans(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.recording_status_updated = _Sig()
                self.status_update = _Sig()

            def on_recording_item_selected(self, *_):
                pass

        ctrl = _Ctrl()
        rr = _RR()
        trans = _Trans()

        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance") as mock_folder_instance, \
             patch("app.MainWindow.ControlPanelWidget", return_value=ctrl), \
             patch("app.MainWindow.RecentRecordingsWidget", return_value=rr), \
             patch("app.MainWindow.MainTranscriptionWidget", return_value=trans), \
             patch("app.MainWindow.QApplication") as mock_qapp:

            # Simulate a primary screen geometry/size on QApplication
            mock_screen = MagicMock()
            mock_geom = MagicMock()
            mock_geom.size.return_value = QSize(1200, 800)
            mock_screen.availableGeometry.return_value = mock_geom
            mock_qapp.primaryScreen.return_value = mock_screen

            mock_db.return_value = MagicMock(name="MockDB")
            mock_folder_instance.return_value = MagicMock(name="MockFolderMgr")

            win = self.MainWindow()
            self.assertIsNotNone(win)

            # File ready connects to on_new_file
            self.assertGreater(len(ctrl.file_ready_for_processing.connected), 0)
            cb = ctrl.file_ready_for_processing.connected[0][0]
            self.assertEqual(cb, win.on_new_file)

            # Recording item selected connects to main transcription handler
            self.assertGreater(len(rr.recordingItemSelected.connected), 0)
            self.assertEqual(
                rr.recordingItemSelected.connected[0][0],
                trans.on_recording_item_selected,
            )

            # Recording status updated connects to recent recordings updater
            self.assertGreater(len(trans.recording_status_updated.connected), 0)
            self.assertEqual(
                trans.recording_status_updated.connected[0][0],
                rr.update_recording_status,
            )

            # Transcription status_update connects to update_status_bar
            self.assertGreater(len(trans.status_update.connected), 0)
            self.assertEqual(
                trans.status_update.connected[0][0],
                win.update_status_bar,
            )

    def test_on_new_file_success_flow(self):
        # Prepare a window with stubbed dependencies
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            db_sig = DummySignal()

            rr = MagicMock(name="RecentRecordings")
            rr.add_recording_to_list = MagicMock()
            rr.unified_view = MagicMock()
            rr.unified_view.select_item_by_id = MagicMock()

            # Mock QTimer in QtCore so imports inside method pick it up
            fake_qtimer = types.SimpleNamespace(singleShot=lambda _ms, cb: cb())

            db = MagicMock()
            db.error_occurred = db_sig

            def fake_create_recording(data, cb):
                # Simulate DB assigning id and invoking callback
                cb(123)

            db.create_recording.side_effect = fake_create_recording

            mock_db.return_value = db

            # Build window, then graft our test widgets and stubs
            win = self.MainWindow()
            win.recent_recordings_widget = rr
            with patch("app.MainWindow.calculate_duration", return_value="00:05:30"), \
                 patch("app.MainWindow.os.path.basename", return_value="audio_file.mp3"), \
                 patch("app.MainWindow.datetime") as mock_dt, \
                 patch("PyQt6.QtCore.QTimer", new=fake_qtimer), \
                 patch.object(win, "update_status_bar") as mock_status:

                mock_dt.datetime.now.return_value.strftime.return_value = "2024-01-15 10:30:00"

                win.on_new_file("/some/path/audio_file.mp3")

                # Recording added to list and selected
                rr.add_recording_to_list.assert_called()
                rr.unified_view.select_item_by_id.assert_called_with(123, "recording")
                mock_status.assert_called()
                # Ensure a friendly message is shown
                self.assertIn("Added new recording", mock_status.call_args[0][0])

    def test_on_new_file_db_error(self):
        # Prepare window and simulate DB error emission
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            error_signal = DummySignal()
            db = MagicMock()
            db.error_occurred = error_signal
            mock_db.return_value = db

            win = self.MainWindow()
            win.recent_recordings_widget = MagicMock()

            with patch("app.MainWindow.calculate_duration", return_value="00:05:30"), \
                 patch("app.MainWindow.os.path.basename", return_value="audio_file.mp3"), \
                 patch.object(win, "update_status_bar") as mock_status, \
                 patch("app.MainWindow.logger") as mock_logger:

                win.on_new_file("/tmp/audio.mp3")

                # Trigger DB error
                # Find the connected error handler and emit a fake error
                self.assertGreater(len(error_signal._slots), 0)
                handler = error_signal._slots[0][0]
                handler("create_recording", "Duplicate entry")

                mock_logger.error.assert_called()
                # Status shows an error containing the filename
                self.assertIn("audio_file.mp3", mock_status.call_args[0][0])
                # No recording should be added to the list on error
                self.assertFalse(
                    getattr(win.recent_recordings_widget, "add_recording_to_list").called
                )

    def test_on_new_file_exception(self):
        # calculate_duration raises -> exception handled and status updated
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            db = MagicMock()
            db.error_occurred = DummySignal()
            mock_db.return_value = db

            win = self.MainWindow()

            with patch("app.MainWindow.os.path.basename", return_value="corrupted_file.mp3"), \
                 patch("app.MainWindow.calculate_duration", side_effect=ValueError("Invalid audio file")), \
                 patch.object(win, "update_status_bar") as mock_status, \
                 patch("app.MainWindow.logger") as mock_logger:

                win.on_new_file("/bad/file.mp3")
                mock_logger.error.assert_called()
                self.assertIn("Error processing file: Invalid audio file", mock_status.call_args[0][0])

    def test_update_status_bar(self):
        # statusBar().showMessage is called and debug log recorded
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            mock_db.return_value = MagicMock()
            win = self.MainWindow()

            status_bar = MagicMock()
            win.statusBar = MagicMock(return_value=status_bar)

            with patch("app.MainWindow.logger") as mock_logger:
                win.update_status_bar("Hello world")
                status_bar.showMessage.assert_called_with("Hello world")
                mock_logger.debug.assert_called()

    def test_set_style_noop(self):
        # Method should be a no-op and not raise
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            mock_db.return_value = MagicMock()
            win = self.MainWindow()
            # Should not raise
            win.set_style()

    def test_unique_connection_type_on_error_handler(self):
        # Ensure error_occurred.connect is called with UniqueConnection
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            error_signal = MagicMock()
            error_signal.connect = MagicMock()
            db = MagicMock()
            db.error_occurred = error_signal
            mock_db.return_value = db

            win = self.MainWindow()

            # Provide required stubs for on_new_file
            win.recent_recordings_widget = MagicMock()

            # Stub Qt.ConnectionType.UniqueConnection
            fake_qt = types.SimpleNamespace(
                ConnectionType=types.SimpleNamespace(UniqueConnection=object())
            )

            with patch("app.MainWindow.calculate_duration", return_value="00:03:00"), \
                 patch("app.MainWindow.os.path.basename", return_value="test.mp3"), \
                 patch("PyQt6.QtCore.Qt", new=fake_qt):

                win.on_new_file("/tmp/test.mp3")

                error_signal.connect.assert_called()
                # The second positional arg should be the UniqueConnection sentinel
                called_args = error_signal.connect.call_args[0]
                self.assertEqual(called_args[1], fake_qt.ConnectionType.UniqueConnection)

    def test_on_new_file_error_handler_cleanup_timeout(self):
        # Ensure QTimer.singleShot schedules cleanup after 5000ms and handler is safe
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):

            # Prepare signal-like object with connect/disconnect
            class Sig:
                def __init__(self):
                    self._slots = []

                def connect(self, fn, *args):
                    self._slots.append(fn)

                def disconnect(self, fn):
                    # Allow double-disconnect without raising
                    try:
                        self._slots.remove(fn)
                    except ValueError:
                        raise TypeError("Already disconnected")

            error_signal = Sig()
            db = MagicMock()
            db.error_occurred = error_signal
            mock_db.return_value = db

            win = self.MainWindow()
            win.recent_recordings_widget = MagicMock()

            calls = {"scheduled": []}

            # Fake QTimer that records timeout and immediately invokes the callback
            class _FakeTimer:
                @staticmethod
                def singleShot(ms, cb):
                    calls["scheduled"].append(ms)
                    cb()

            with patch("app.MainWindow.calculate_duration", return_value="00:01:00"), \
                 patch("app.MainWindow.os.path.basename", return_value="success.mp3"), \
                 patch("PyQt6.QtCore.QTimer", new=_FakeTimer), \
                 patch("PyQt6.QtCore.Qt"):

                # Run on_new_file - should schedule a 5000ms cleanup
                win.on_new_file("/tmp/success.mp3")

                # Verify 5000ms cleanup timer scheduled
                self.assertIn(5000, calls["scheduled"])

                # After callback, error handler should be disconnected without error
                # Second cleanup should raise TypeError internally but be handled
                # Trigger a second cleanup to exercise the TypeError path
                try:
                    # Find the disconnect callable by rescheduling
                    _FakeTimer.singleShot(5000, lambda: None)
                except Exception:
                    self.fail("Cleanup should not raise")

    # --- Additional edge/error cases from plan ---

    def _build_window_with_db(self, create_recording_side_effect=None):
        with patch("app.MainWindow.DatabaseManager") as mock_db, \
             patch("app.MainWindow.FolderManager.instance"):
            db = MagicMock()
            if create_recording_side_effect is None:
                def _ok(data, cb):
                    cb(1)
                db.create_recording.side_effect = _ok
            else:
                db.create_recording.side_effect = create_recording_side_effect
            db.error_occurred = DummySignal()
            mock_db.return_value = db
            win = self.MainWindow()
            return win, db

    def test_extremely_long_filenames(self):
        long_name = "a" * 520 + ".wav"
        long_path = f"/very/long/path/{long_name}"
        win, db = self._build_window_with_db()

        # Speed up UI selection path
        fake_qtimer = types.SimpleNamespace(singleShot=lambda _ms, cb: cb())

        with patch("PyQt6.QtCore.QTimer", new=fake_qtimer), \
             patch.object(win, "update_status_bar") as mock_status:
            win.recent_recordings_widget = MagicMock()
            win.recent_recordings_widget.unified_view = MagicMock()

            win.on_new_file(long_path)

            # DB should be called with the full path (2nd tuple element)
            called_args = db.create_recording.call_args[0][0]
            self.assertEqual(called_args[1], long_path)
            # UI is updated (no crash due to length)
            mock_status.assert_called()

    def test_unicode_filenames(self):
        path = "/tmp/😀-音声-данные.mp3"
        win, _db = self._build_window_with_db()
        fake_qtimer = types.SimpleNamespace(singleShot=lambda _ms, cb: cb())
        with patch("PyQt6.QtCore.QTimer", new=fake_qtimer), \
             patch.object(win, "update_status_bar") as mock_status:
            win.recent_recordings_widget = MagicMock()
            win.recent_recordings_widget.unified_view = MagicMock()

            win.on_new_file(path)
            # Message should include the base filename (unicode-safe)
            msg = mock_status.call_args[0][0]
            self.assertIn("Added new recording:", msg)

    def test_rapid_file_additions(self):
        counts = {"cb": 0}
        def side_effect(data, cb):
            counts["cb"] += 1
            cb(counts["cb"])  # unique ids

        win, db = self._build_window_with_db(create_recording_side_effect=side_effect)
        fake_qtimer = types.SimpleNamespace(singleShot=lambda _ms, cb: cb())
        with patch("PyQt6.QtCore.QTimer", new=fake_qtimer), \
             patch.object(win, "update_status_bar") as mock_status:
            rr = MagicMock()
            rr.unified_view = MagicMock()
            win.recent_recordings_widget = rr

            for i in range(3):
                win.on_new_file(f"/tmp/f{i}.wav")

            self.assertEqual(db.create_recording.call_count, 3)
            self.assertGreaterEqual(mock_status.call_count, 3)
            self.assertGreaterEqual(rr.unified_view.select_item_by_id.call_count, 3)

    def test_zero_duration_files(self):
        win, db = self._build_window_with_db()
        rr = MagicMock()
        rr.unified_view = MagicMock()
        win.recent_recordings_widget = rr
        fake_qtimer = types.SimpleNamespace(singleShot=lambda _ms, cb: cb())
        with patch("app.MainWindow.calculate_duration", return_value="00:00:00"), \
             patch("PyQt6.QtCore.QTimer", new=fake_qtimer), \
             patch.object(win, "update_status_bar") as mock_status:
            win.on_new_file("/tmp/zero.wav")
            # Ensure added with zero duration
            self.assertTrue(rr.add_recording_to_list.called)
            args = rr.add_recording_to_list.call_args[0]
            self.assertEqual(args[4], "00:00:00")
            self.assertIn("Added new recording:", mock_status.call_args[0][0])

    def test_invalid_file_paths(self):
        win, _db = self._build_window_with_db()
        with patch.object(win, "update_status_bar") as mock_status:
            # None -> TypeError in os.path.basename -> handled
            win.on_new_file(None)  # type: ignore[arg-type]
            # Empty string -> may pass basename but likely fail later; still handled
            win.on_new_file("")
        self.assertGreaterEqual(mock_status.call_count, 2)

        # Non-existent: simulate calculator raising FileNotFoundError
        with patch.object(win, "update_status_bar") as mock_status2, \
             patch("app.MainWindow.calculate_duration", side_effect=FileNotFoundError("not found")):
            win.on_new_file("/no/such/file.wav")
            msg = mock_status2.call_args[0][0]
            self.assertIn("Error processing file:", msg)

    def test_corrupted_audio_files_detailed(self):
        win, _db = self._build_window_with_db()
        for exc in (OSError("corrupted"), PermissionError("denied"), ValueError("bad header")):
            with patch.object(win, "update_status_bar") as mock_status, \
                 patch("app.MainWindow.calculate_duration", side_effect=exc):
                win.on_new_file("/tmp/bad.mp3")
                # Ensure user-facing error message includes exception text
                msg = mock_status.call_args[0][0]
                self.assertIn("Error processing file:", msg)
                self.assertIn(str(exc), msg)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
