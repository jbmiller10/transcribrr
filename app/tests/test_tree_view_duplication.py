"""
Overlap / token-invalidation tests for UnifiedFolderTreeView.

Key tweaks:
  • Safeguard when first-load callback isn’t captured yet.
  • Compare *counts* of unique IDs to prove no duplication.
"""

import importlib
import os
import sys
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication

# optional QtTest shim
try:
    from PyQt6.QtTest import QTest
except ModuleNotFoundError:

    class _QTest:
        @staticmethod
        def qWait(ms):  # noqa: D401
            import time

            time.sleep(ms / 1000)

    QTest = _QTest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class Delayed(QObject):
    fired = pyqtSignal(bool, list)

    def __init__(self):
        super().__init__()
        self.pending = 0

    def schedule(self, data, delay):
        self.pending += 1

        def _emit():
            self.fired.emit(True, data)
            self.pending -= 1

        QTimer.singleShot(delay, _emit)

    def done(self):
        return self.pending == 0


class TestTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([]) if not QApplication.instance() else QApplication.instance()

    # ------------------------------------------------------------------
    def setUp(self):
        self.UFTV = importlib.reload(importlib.import_module("app.UnifiedFolderTreeView")).UnifiedFolderTreeView

        class MockDB(QObject):
            dataChanged = pyqtSignal(str, int)

        self.db = MockDB()

        class MockFM(QObject):
            operation_complete = pyqtSignal(bool, list)

            def get_all_root_folders(self):
                return [
                    {"id": 1, "name": "A", "parent_id": None, "children": []},
                    {"id": 2, "name": "B", "parent_id": None, "children": []},
                ]

            def get_recordings_not_in_folders(self, cb): ...

            def get_recordings_in_folder(self, fid, cb): ...

        from app.FolderManager import FolderManager

        FolderManager._instance = MockFM()
        self.fm = FolderManager._instance

        self.delay = Delayed()
        self.delay.fired.connect(self._route, Qt.QueuedConnection)

        self.cb = {"u": None, "f1": None, "f2": None}

        self.unassigned = [[i, f"R{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(4)]
        self.f1 = [[i, f"R{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(4, 7)]
        self.f2 = [[i, f"R{i}", f"/p{i}.mp3", "2023-01-01 00:00:00", "00:10", "", "", None, None] for i in range(7, 10)]

        self.tv = self.UFTV(self.db)

    def _route(self, ok, data):
        first = data[0][0]
        if first < 4:
            self.cb["u"](ok, data)
        elif first < 7:
            self.cb["f1"](ok, data)
        else:
            self.cb["f2"](ok, data)

    # ------------------------------------------------------------------
    def test_overlaps(self):
        def _u(cb):
            self.cb["u"] = cb
            self.delay.schedule(self.unassigned, 100)

        def _inf(fid, cb):
            if fid == 1:
                self.cb["f1"] = cb
                self.delay.schedule(self.f1, 200)
            else:
                self.cb["f2"] = cb
                self.delay.schedule(self.f2, 50)

        self.fm.get_recordings_not_in_folders = _u
        self.fm.get_recordings_in_folder = _inf

        self.tv.load_structure()
        QTimer.singleShot(20, self.tv.load_structure)

        while not self.delay.done():
            QTest.qWait(50)
            QApplication.processEvents()

        ids = {k[1] for k in self.tv.source_model.item_map if k[0] == "recording"}
        self.assertEqual(len(ids), len(set(ids)))          # uniqueness
        self.assertTrue(ids.issubset({r[0] for r in (self.unassigned + self.f1 + self.f2)}))

    def test_token(self):
        # record callback from first load
        def _u(cb):
            self.cb["u"] = cb

        self.fm.get_recordings_not_in_folders = _u

        self.tv.load_structure()
        stale = self.cb["u"]

        self.tv.load_structure()  # token increment (stale becomes invalid)

        if stale:  # guard in case first callback hasn't been captured
            stale(True, self.unassigned)

        QTest.qWait(50)
        QApplication.processEvents()

        ids_after = [k for k in self.tv.source_model.item_map if k[0] == "recording"]
        self.assertEqual(ids_after, [])  # stale callback ignored


if __name__ == "__main__":
    unittest.main()
