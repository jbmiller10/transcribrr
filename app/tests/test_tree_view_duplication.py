"""
Tree-view duplication prevention tests.

Only change: make the QTest import optional so CI runners that
have PyQt6 but not the QtTest wheel still execute the suite.
"""

import os
import sys
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

# ---- safe import of QTest ---------------------------------------------------
try:
    from PyQt6.QtTest import QTest
except ModuleNotFoundError:  # minimal stub
    class _QTest:
        @staticmethod
        def qWait(ms: int):  # noqa: D401
            import time

            time.sleep(ms / 1000)

    QTest = _QTest
# -----------------------------------------------------------------------------

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.UnifiedFolderTreeView import UnifiedFolderTreeView


class Delayed(QObject):
    trig = pyqtSignal(bool, list)

    def __init__(self):
        super().__init__()
        self.pending = 0

    def fire(self, data, delay):
        self.pending += 1

        def _cb():
            self.trig.emit(True, data)
            self.pending -= 1

        QTimer.singleShot(delay, _cb)

    def done(self):
        return self.pending == 0


class TestTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([]) if not QApplication.instance() else QApplication.instance()

    # ----------------------------------------------------------------------
    def setUp(self):
        class MockDB(QObject):
            dataChanged = pyqtSignal(str, int)

        self.db = MockDB()

        class MockFM(QObject):
            operation_complete = pyqtSignal(bool, list)

            def __init__(self):
                super().__init__()

            def get_all_root_folders(self):
                return [
                    {"id": 1, "name": "Folder1", "parent_id": None, "children": []},
                    {"id": 2, "name": "Folder2", "parent_id": None, "children": []},
                ]

            def get_recordings_not_in_folders(self, cb): pass

            def get_recordings_in_folder(self, fid, cb): pass

        from app.FolderManager import FolderManager
        FolderManager._instance = MockFM()
        self.fm = FolderManager._instance

        self.delayed = Delayed()
        self.delayed.trig.connect(self._dispatch, Qt.QueuedConnection)

        self.cb = {"u": None, "f1": None, "f2": None}

        # fabricate recordings
        self.unassigned = [[i, f"R{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(4)]
        self.f1 = [[i, f"R{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(4, 7)]
        self.f2 = [[i, f"R{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(7, 10)]

        self.tv = UnifiedFolderTreeView(self.db)

    # helper to route delayed callback
    def _dispatch(self, ok, data):
        first = data[0][0]
        if first < 4:
            self.cb["u"](ok, data)
        elif first < 7:
            self.cb["f1"](ok, data)
        else:
            self.cb["f2"](ok, data)

    # ----------------------------------------------------------------------
    def test_overlaps(self):
        def _u(cb):
            self.cb["u"] = cb
            self.delayed.fire(self.unassigned, 100)

        def _inf(fid, cb):
            if fid == 1:
                self.cb["f1"] = cb
                self.delayed.fire(self.f1, 200)
            else:
                self.cb["f2"] = cb
                self.delayed.fire(self.f2, 50)

        self.fm.get_recordings_not_in_folders = _u
        self.fm.get_recordings_in_folder = _inf

        self.tv.load_structure()
        QTimer.singleShot(20, self.tv.load_structure)

        while not self.delayed.done():
            QTest.qWait(50)
            QApplication.processEvents()

        QTest.qWait(200)
        QApplication.processEvents()

        ids = {k[1] for k in self.tv.source_model.item_map if k[0] == "recording"}
        expect = {r[0] for r in (self.unassigned + self.f1 + self.f2)}
        self.assertEqual(ids, expect)

    def test_token(self):
        def _u(cb): self.cb["u"] = cb
        def _inf(fid, cb):
            if fid == 1: self.cb["f1"] = cb
            else: self.cb["f2"] = cb

        self.fm.get_recordings_not_in_folders = _u
        self.fm.get_recordings_in_folder = _inf

        self.tv.load_structure()
        stale = self.cb["u"]
        self.tv.load_structure()  # token increment

        stale(True, self.unassigned)  # call stale
        QTest.qWait(50)
        QApplication.processEvents()

        self.assertEqual(
            [k for k in self.tv.source_model.item_map if k[0] == "recording"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
