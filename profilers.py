import csv
import os
import pstats
import sys
import webbrowser
from abc import ABC, abstractmethod
from cProfile import Profile
from pathlib import Path
from pstats import SortKey

from PyQt5.QtCore import QObject, QSortFilterProxyModel, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QDialog, QTableView, QTextEdit, QVBoxLayout
from qgis.core import QgsApplication
from qgis.utils import iface

from .gadgets import writeProfileToCsv


class ProfilerAdapter(ABC):
    @classmethod
    @abstractmethod
    def canActivate(cls) -> bool:
        pass

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass


class PyinstrumentProfiler(ProfilerAdapter):
    HTML_PATH = os.path.join(os.getcwd(), "pyinstrument_profile.html")

    @classmethod
    def canActivate(cls) -> bool:
        try:
            from pyinstrument import Profiler
        except ImportError:
            return False
        return True

    def start(self):
        from pyinstrument import Profiler

        self.profiler = Profiler()
        self.profiler.start()

    def stop(self):
        self.profiler.stop()
        self.profiler.write_html(self.HTML_PATH)
        url = "file://" + os.path.realpath(self.HTML_PATH)
        webbrowser.open(url, new=2)  # open in new tab


class cProfileProfiler(ProfilerAdapter):
    PROF_PATH = os.path.join(QgsApplication.qgisSettingsDirPath(), "cProfile_dump.prof")
    STATS_PATH = os.path.join(QgsApplication.qgisSettingsDirPath(), "pstats_dump.txt")
    CSV_PATH = os.path.join(QgsApplication.qgisSettingsDirPath(), "plugin_profiler.csv")
    CSV_DELIMITER = ";"

    @classmethod
    def canActivate(cls) -> bool:
        return True

    def start(self):
        self.profile = Profile()
        self.profile.enable()

    def stop(self):
        self.profile.disable()

        # Write .prof file
        self.profile.dump_stats(self.PROF_PATH)

        # Write .txt file
        with open(self.STATS_PATH, "w") as file:
            ps = pstats.Stats(self.PROF_PATH, stream=file)
            ps.sort_stats(SortKey.CUMULATIVE)
            ps.print_stats()

        # Write .csv file
        txt = Path(self.STATS_PATH).read_text()
        writeProfileToCsv(txt, self.CSV_PATH, self.CSV_DELIMITER)
        self.showResult()
        # from snakeviz.stats import table_rows, json_stats
        # rows = table_rows(ps)
        # print(rows)
        # jsonstats = json_stats(ps)
        # print(jsonstats)

        try:
            import subprocess

            import snakeviz

            subprocess.Popen(["snakeviz", self.PROF_PATH], shell=False)
        except ImportError:
            print("snakeviz is not installed")

    def showResult(self):
        dlg = QDialog(iface.mainWindow())
        layout = QVBoxLayout()
        tableView = QTableView()
        tableView.setSortingEnabled(True)
        tableView.horizontalHeader().setVisible(True)
        tableView.horizontalHeader().setStretchLastSection(True)
        tableView.verticalHeader().setVisible(False)
        tableView.setModel(self.getModel())
        layout.addWidget(tableView)
        dlg.setLayout(layout)
        dlg.exec()

    def getModel(self):
        model = QStandardItemModel()
        with open(self.CSV_PATH) as fileInput:
            for i, row in enumerate(
                csv.reader(fileInput, delimiter=self.CSV_DELIMITER)
            ):
                if i == 0:
                    model.setHorizontalHeaderLabels([r.strip().strip('"') for r in row])
                else:
                    items = [QStandardItem(field.strip()) for field in row]
                    if any(row):
                        model.appendRow(items)

        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(model)
        return proxyModel


class OxProfiler(ProfilerAdapter):
    @classmethod
    def canActivate(cls) -> bool:
        try:
            import ox_profile
        except ImportError:
            return False
        return True

    def start(self) -> None:
        from ox_profile.core.launchers import SimpleLauncher
        from ox_profile.core.sampling import Sampler

        self.profiler = SimpleLauncher.launch()

    def stop(self) -> None:
        txt = self.profiler.show()
        self.showText(txt)
        self.profiler.cancel()

    def showText(self, txt: str):
        dlg = QDialog(iface.mainWindow())
        layout = QVBoxLayout()
        textEdit = QTextEdit()
        textEdit.setText(txt)
        layout.addWidget(textEdit)
        dlg.setLayout(layout)
        dlg.show()


class PySpyProfiler(ProfilerAdapter):
    pass


class MyProfiler(ProfilerAdapter):
    @classmethod
    def canActivate(cls) -> bool:
        return True

    def start(self) -> None:
        self.sampler = Sampler()
        self.sampler.sampledFrames.connect(self.showResult)
        self.sampler.start()

    def stop(self) -> None:
        self.sampler.stop()

    def showResult(self, frames: list):
        # pass
        print(frames)


class Sampler(QObject):
    sampledFrames = pyqtSignal(list)

    def __init__(self, interval: int = 10, parent: QObject = None):
        super().__init__(parent)
        self.frames = []
        self.timer = QTimer()
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.record)

    def start(self):
        self.frames.clear()
        self.timer.start()

    def record(self):
        interval_before = sys.getswitchinterval()
        sys.setswitchinterval(10000)
        self.frames.append(sys._current_frames().values())
        sys.setswitchinterval(interval_before)

    def stop(self):
        self.timer.stop()
        self.sampledFrames.emit(self.frames)
