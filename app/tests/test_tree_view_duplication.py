import sys
import os
import unittest
from unittest.mock import patch
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

# repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.UnifiedFolderTreeView import UnifiedFolderTreeView


class DelayedCallbackGenerator(QObject):
    callback_triggered = pyqtSignal(bool, list)

    def __init__(self):
        super().__init__()
        self.pending = 0

    def schedule(self, data, delay_ms):
        self.pending += 1

        def fire():
            self.callback_triggered.emit(True, data)
            self.pending -= 1

        QTimer.singleShot(delay_ms, fire)

    def done(self):
        return self.pending == 0


class TestTreeViewDuplication(unittest.TestCase):
    """Verifies no duplicate items & token invalidation."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([]) if not QApplication.instance() else QApplication.instance()

    def setUp(self):
        # -------- mock DB manager (signal only) -----------
        class MockDB(QObject):
            dataChanged = pyqtSignal(str, int)

        self.dbm = MockDB()

        # -------- mock FolderManager singleton ------------
        class MockFolderManager(QObject):
            operation_complete = pyqtSignal(bool, list)      # bound signal

            def __init__(self):
                super().__init__()

            # lightweight folder tree
            def get_all_root_folders(self):
                return [
                    {"id": 1, "name": "Folder 1", "parent_id": None, "children": []},
                    {"id": 2, "name": "Folder 2", "parent_id": None, "children": []},
                ]

            # placeholders – filled by test
            def get_recordings_not_in_folders(self, cb): pass
            def get_recordings_in_folder(self, fid, cb): pass

        from app.FolderManager import FolderManager
        FolderManager._instance = MockFolderManager()
        self.fm = FolderManager._instance

        # storage for callbacks we’ll invoke manually
        self.cb = {"u": None, "f1": None, "f2": None}

        # fabricate recording rows
        self.unassigned = [[i, f"Rec{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(4)]
        self.f1 = [[i, f"Rec{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(4, 7)]
        self.f2 = [[i, f"Rec{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(7, 10)]

        self.delayer = DelayedCallbackGenerator()
        self.delayer.callback_triggered.connect(self._dispatch, Qt.QueuedConnection)

        self.tv = UnifiedFolderTreeView(self.dbm)

    # ------------- helpers -----------------
    def _dispatch(self, ok, data):
        first = data[0][0]
        if first < 4:
            self.cb["u"](ok, data)
        elif first < 7:
            self.cb["f1"](ok, data)
        else:
            self.cb["f2"](ok, data)

    # ------------- tests --------------------
    def test_overlapping_callbacks(self):
        # patch FolderManager query methods
        def unassigned(cb):
            self.cb["u"] = cb
            self.delayer.schedule(self.unassigned, 100)

        def infolder(fid, cb):
            if fid == 1:
                self.cb["f1"] = cb
                self.delayer.schedule(self.f1, 200)
            else:
                self.cb["f2"] = cb
                self.delayer.schedule(self.f2, 50)

        self.fm.get_recordings_not_in_folders = unassigned
        self.fm.get_recordings_in_folder = infolder

        # initial load + overlapping refresh
        self.tv.load_structure()
        QTimer.singleShot(20, self.tv.load_structure)

        while not self.delayer.done():
            QTest.qWait(50)
            QApplication.processEvents()

        QTest.qWait(200)
        QApplication.processEvents()

        ids = {k[1] for k in self.tv.source_model.item_map if k[0] == "recording"}
        expect = {r[0] for r in (self.unassigned + self.f1 + self.f2)}
        self.assertEqual(ids, expect)
        self.assertEqual(set(self.tv.id_to_widget.keys()), expect)

    def test_token_invalidation(self):
        # dummy no-op callbacks captured
        def unassigned(cb): self.cb["u"] = cb
        def infolder(fid, cb):
            if fid == 1: self.cb["f1"] = cb
            else: self.cb["f2"] = cb

        self.fm.get_recordings_not_in_folders = unassigned
        self.fm.get_recordings_in_folder = infolder

        tok0 = self.tv._load_token
        self.tv.load_structure()
        cb_old = self.cb["u"]
        self.tv.load_structure()                      # second load – token++

        # stale callback executed –
        cb_old(True, self.unassigned)
        QTest.qWait(50); QApplication.processEvents()

        ids = [k for k in self.tv.source_model.item_map if k[0] == "recording"]
        self.assertEqual(len(ids), 0)
        self.assertEqual(len(self.tv.id_to_widget), 0)


if __name__ == "__main__":
    unittest.main()
