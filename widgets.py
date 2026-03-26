import os
import pstats
import sys
import tempfile
import webbrowser
from pathlib import Path
from pstats import SortKey
from typing import Any, List, Type

from PyQt5 import uic
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QComboBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from qgis.core import QgsApplication
from qgis.gui import QgsDevToolWidget, QgsDevToolWidgetFactory
from qgis.utils import findPlugins, plugins

from .gadgets import get_sizof_log, memory_usage_psutil, writeProfileToCsv
from .profilers import (
    MyProfiler,
    OxProfiler,
    ProfilerAdapter,
    PyinstrumentProfiler,
    cProfileProfiler,
)

pluginPath = os.path.dirname(__file__)
WIDGET, BASE = uic.loadUiType(os.path.join(pluginPath, "forms", "inspector_widget.ui"))


class InspectorWidget(BASE, WIDGET):
    btnInvestigate: QPushButton
    cmbPlugins: QComboBox
    txtLog: QPlainTextEdit
    treeObjects: QTreeWidget

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setupUi(self)
        self._profilers: List[ProfilerAdapter] = []
        self.profilePath = QgsApplication.qgisSettingsDirPath()
        self.pluginPath = os.path.join(self.profilePath, "python", "plugins")
        self.pluginMetadata = findPlugins(self.pluginPath)

        for name, info in self.pluginMetadata:
            if name in plugins:
                self.cmbPlugins.addItem(name, info)

        self.btnInvestigate.clicked.connect(self.inspect)
        self.mActionProfiler.triggered.connect(self.toggleProfiler)
        self.mActionClear.triggered.connect(self.clear)

        # self.registerProfiler(PyinstrumentProfiler)
        # self.registerProfiler(cProfileProfiler)
        # self.registerProfiler(OxProfiler)
        self.registerProfiler(MyProfiler)

    def registerProfiler(self, profilerType: Type[ProfilerAdapter]):
        if profilerType.canActivate():
            self._profilers.append(profilerType())

    def clear(self):
        self.txtLog.clear()
        self.treeObjects.clear()

    def toggleProfiler(self, checked: bool):
        if checked:
            self.startProfilers()
        else:
            self.stopProfilers()

    def startProfilers(self):
        self.mActionProfiler.setToolTip("Stop profiler")
        for profiler in self._profilers:
            profiler.start()

        from pyinstrument import Profiler

        self.profiler = Profiler()
        self.profiler.start()

    def stopProfilers(self):
        self.mActionProfiler.setToolTip("Start profiler")
        for profiler in self._profilers:
            profiler.stop()

        HTML_PATH = os.path.join(os.getcwd(), "pyinstrument_profile.html")
        self.profiler.stop()
        self.profiler.write_html(HTML_PATH)
        url = "file://" + os.path.realpath(HTML_PATH)
        webbrowser.open(url, new=2)  # open in new tab

    def inspect(self):
        suspectName = self.cmbPlugins.currentText()
        suspectConfig = self.cmbPlugins.currentData()
        suspectVersion = suspectConfig.get("general", "version")
        pluginInstance = plugins[suspectName]

        self.treeObjects.clear()
        self.fillTree(pluginInstance)

    def getTextLog(self, pluginInstance) -> str:
        txt = ""
        # # Log metadata
        # for section in suspectConfig.sections():
        #     self.txtLog.appendPlainText(section)
        #     for k, v in dict(suspectConfig[section]).items():
        #         self.txtLog.appendPlainText('\t' + k + ' : ' + v)
        #     self.txtLog.appendHtml('<br>')

        # Log some instance vars
        # self.txtLog.appendPlainText(f'Vars of main plugin class "{pluginInstance.__class__.__name__}" ')
        # for key, var in vars(pluginInstance).items():
        #     if hasattr(var, '__dict__'):
        #         self.txtLog.appendPlainText('\t' + str(key) + ' : ' + str(var.__class__.__name__))
        #     else:
        #         self.txtLog.appendPlainText('\t' + str(key) + ' : ' + str(var))
        txt += str(f"total mem usage {memory_usage_psutil()} MB\n")
        txt += get_sizof_log()
        return txt

    def fillTree(self, pluginInstance):
        rootItem = self.treeObjects.invisibleRootItem()
        self.recursiveInspection(
            rootItem, pluginInstance, [pluginInstance.__class__.__name__]
        )
        self.treeObjects.addTopLevelItem(rootItem)
        rootItem.setExpanded(True)

    def recursiveInspection(self, parent: QTreeWidgetItem, obj: Any, path: List[str]):
        """appends a QTreewidgetItem to the given parent"""
        try:
            item = QTreeWidgetItem(
                parent, [path[-1], str(obj), str(sys.getsizeof(obj))], 0
            )
        except Exception as ex:
            print("couldnt create an item", ex)
            item = QTreeWidgetItem(parent, ["", "", ""], 0)
        item.setExpanded(True)
        if (
            (obj != None)
            and (not isinstance(obj, (str, float, int, list, dict, set)))
            and hasattr(obj, "__dict__")
        ):
            for attr, val in obj.__dict__.items():
                temp_path = path[:]
                temp_path.append(attr)
                try:
                    self.recursiveInspection(item, getattr(obj, attr), temp_path)
                except:
                    pass


class InspectorDevTool(QgsDevToolWidget, InspectorWidget):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)


class InspectorFactory(QgsDevToolWidgetFactory):
    def __init__(self, title: str = "", icon: QIcon = QIcon()):
        super().__init__(title, icon)

    def createWidget(self, parent: QWidget = None):
        return InspectorDevTool()
