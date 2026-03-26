import logging
import os
import sys
from typing import Any, List, Type

from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction,
    QComboBox,
    QFileDialog,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)
from qgis.core import QgsApplication
from qgis.gui import QgsDevToolWidget, QgsDevToolWidgetFactory
from qgis.utils import findPlugins, plugins

from .gadgets import sizeof_fmt
from .profilers import (
    ProfilerAdapter,
    PyinstrumentProfiler,
    cProfileProfiler,
)
from .dialogs import ProfilerSettingsDialog

logger = logging.getLogger(__name__)

pluginPath = os.path.dirname(__file__)
WIDGET, BASE = uic.loadUiType(os.path.join(pluginPath, "forms", "inspector_widget.ui"))
_PLACEHOLDER = "⏳ …"
_LAZY_DATA_ROLE = Qt.UserRole + 1


class InspectorWidget(BASE, WIDGET):
    btnInvestigate: QPushButton
    cmbPlugins: QComboBox
    txtLog: QPlainTextEdit
    treeObjects: QTreeWidget

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setupUi(self)

        # All known profiler classes (order matters for settings dialog)
        self._profiler_classes: List[Type[ProfilerAdapter]] = [
            PyinstrumentProfiler,
            cProfileProfiler,
        ]

        # Which profiler classes are enabled by the user (default: pyinstrument if available)
        self._enabled_profilers: List[Type[ProfilerAdapter]] = [
            cls for cls in self._profiler_classes if cls.canActivate()
        ]

        # Currently running profiler instances (populated on start, cleared on stop)
        self._running_profilers: List[ProfilerAdapter] = []

        self.profilePath = QgsApplication.qgisSettingsDirPath()
        self.pluginPath = os.path.join(self.profilePath, "python", "plugins")
        self.pluginMetadata = findPlugins(self.pluginPath)

        for name, info in self.pluginMetadata:
            if name in plugins:
                self.cmbPlugins.addItem(name, info)

        # Wire toolbar actions
        self.btnInvestigate.clicked.connect(self.inspect)
        self.mActionProfiler.triggered.connect(self.toggleProfiler)
        self.mActionClear.triggered.connect(self.clear)
        self.mActionSaveLog.triggered.connect(self.saveLog)
        self.mActionSettings.triggered.connect(self.showProfilerSettings)

        # Show dependency warnings on startup
        self._checkDependencies()

        # Lazy loading for tree inspection
        self.treeObjects.itemExpanded.connect(self._onItemExpanded)

    def clear(self):
        self.txtLog.clear()
        self.treeObjects.clear()

    def toggleProfiler(self, checked: bool):
        if checked:
            self.startProfiling()
        else:
            self.stopProfiling()

    def startProfiling(self):
        """Instantiate and start all enabled profilers."""
        self._running_profilers = []
        names = []
        for cls in self._enabled_profilers:
            if cls.canActivate():
                instance = cls()
                instance.start()
                self._running_profilers.append(instance)
                names.append(cls.display_name)
        if names:
            self.mActionProfiler.setToolTip("Stop profiler")
            self.txtLog.appendPlainText(f"▶ Profiling started: {', '.join(names)}")
        else:
            self.mActionProfiler.setChecked(False)
            self.txtLog.appendPlainText("⚠ No profilers available. Check Profiler Settings.")

    def stopProfiling(self):
        """Stop all running profilers and show summaries."""
        self.mActionProfiler.setToolTip("Start profiler")
        for profiler in self._running_profilers:
            try:
                profiler.stop()
                summary = profiler.get_summary()
                if summary:
                    self.txtLog.appendPlainText(summary)
            except Exception as ex:
                logger.warning("Error stopping profiler %s: %s", profiler.display_name, ex)
                self.txtLog.appendPlainText(f"⚠ Error stopping {profiler.display_name}: {ex}")
        self._running_profilers.clear()
        self.txtLog.appendPlainText("⏹ Profiling stopped.")

    def showProfilerSettings(self):
        """Open the profiler settings dialog."""
        dlg = ProfilerSettingsDialog(
            self._profiler_classes,
            self._enabled_profilers,
            parent=self,
        )
        if dlg.exec() == ProfilerSettingsDialog.Accepted:
            self._enabled_profilers = dlg.selected_profilers()
            names = [cls.display_name for cls in self._enabled_profilers]
            self.txtLog.appendPlainText(f"Profilers enabled: {', '.join(names) or 'none'}")

    def saveLog(self):
        """Save txtLog content to a file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log", "", "Text Files (*.txt);;All Files (*)"
        )
        if path:
            try:
                with open(path, "w") as f:
                    f.write(self.txtLog.toPlainText())
                self.txtLog.appendPlainText(f"Log saved to {path}")
            except Exception as ex:
                logger.warning("Could not save log: %s", ex)
                self.txtLog.appendPlainText(f"⚠ Could not save log: {ex}")

    def _checkDependencies(self):
        """Check profiler availability and warn user about missing dependencies."""
        import shutil

        for cls in self._profiler_classes:
            if not cls.canActivate() and cls.install_hint:
                self.txtLog.appendPlainText(
                    f"⚠ {cls.display_name} is not installed. "
                    f"Run {cls.install_hint} in the QGIS Python Console to enable it."
                )
            elif cls.canActivate() and cls.install_hint:
                if "snakeviz" in cls.install_hint and not shutil.which("snakeviz"):
                    self.txtLog.appendPlainText(
                        f"💡 {cls.display_name}: Install snakeviz for interactive visualization. "
                        f"Run !pip install snakeviz in the QGIS Python Console."
                    )

    def inspect(self):
        suspectName = self.cmbPlugins.currentText()
        pluginInstance = plugins[suspectName]

        self.treeObjects.clear()
        self.fillTree(pluginInstance)

    def fillTree(self, pluginInstance):
        self._seen_ids = set()
        rootItem = self.treeObjects.invisibleRootItem()
        self.recursiveInspection(
            rootItem, pluginInstance, [pluginInstance.__class__.__name__], depth=0
        )

    def recursiveInspection(
        self,
        parent: QTreeWidgetItem,
        obj: Any,
        path: List[str],
        depth: int = 0,
        max_depth: int = 3,
    ):
        """Appends a QTreeWidgetItem to the given parent with cycle detection and depth limiting."""
        # Safe value representation
        try:
            value_repr = repr(obj)
            if len(value_repr) > 200:
                value_repr = value_repr[:200] + "…"
        except Exception:
            value_repr = "<error getting repr>"

        # Safe size
        try:
            size_str = sizeof_fmt(sys.getsizeof(obj))
        except Exception:
            size_str = "?"

        try:
            item = QTreeWidgetItem(parent, [path[-1], value_repr, size_str], 0)
        except Exception as ex:
            logger.warning("Could not create tree item for '%s': %s", path[-1], ex)
            item = QTreeWidgetItem(parent, [path[-1], "<error>", ""], 0)

        # Type info as tooltip
        try:
            item.setToolTip(0, type(obj).__qualname__)
            item.setToolTip(1, type(obj).__qualname__)
        except Exception:
            pass

        # Check if object can have children
        if (
            obj is not None
            and not isinstance(obj, (str, bytes, float, int, bool))
            and hasattr(obj, "__dict__")
        ):
            obj_id = id(obj)

            # Cycle detection
            if obj_id in self._seen_ids:
                QTreeWidgetItem(item, ["[circular reference]", "", ""], 0)
                return

            self._seen_ids.add(obj_id)

            if depth >= max_depth:
                # Add placeholder for lazy loading
                placeholder = QTreeWidgetItem(item, [_PLACEHOLDER, "", ""], 0)
                item.setData(0, _LAZY_DATA_ROLE, (obj, path[:], depth, max_depth))
            else:
                self._populateChildren(item, obj, path, depth, max_depth)

    def _populateChildren(
        self,
        item: QTreeWidgetItem,
        obj: Any,
        path: List[str],
        depth: int,
        max_depth: int,
    ):
        """Populate child items for an object's attributes."""
        try:
            for attr in sorted(obj.__dict__.keys()):
                child_path = path + [attr]
                try:
                    child_obj = getattr(obj, attr)
                    self.recursiveInspection(
                        item, child_obj, child_path, depth + 1, max_depth
                    )
                except Exception:
                    logger.debug("Could not inspect attribute '%s'", attr)
        except Exception as ex:
            logger.debug("Could not iterate __dict__ of %s: %s", path[-1], ex)

    def _onItemExpanded(self, item: QTreeWidgetItem):
        """Lazy-load children when a depth-limited node is expanded."""
        data = item.data(0, _LAZY_DATA_ROLE)
        if data is None:
            return

        # Remove placeholder child(ren)
        for i in reversed(range(item.childCount())):
            child = item.child(i)
            if child.text(0) == _PLACEHOLDER:
                item.removeChild(child)

        obj, path, depth, max_depth = data
        item.setData(0, _LAZY_DATA_ROLE, None)  # Clear so it doesn't re-trigger
        self._populateChildren(item, obj, path, depth, max_depth + 3)


class InspectorDevTool(QgsDevToolWidget, InspectorWidget):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)


class InspectorFactory(QgsDevToolWidgetFactory):
    def __init__(self, title: str = "", icon: QIcon = QIcon()):
        super().__init__(title, icon)

    def createWidget(self, parent: QWidget = None):
        return InspectorDevTool()
