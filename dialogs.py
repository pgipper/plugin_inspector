import logging
from typing import Dict, List, Type

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .profilers import ProfilerAdapter

logger = logging.getLogger(__name__)


class ProfilerSettingsDialog(QDialog):
    """Dialog for selecting which profilers to enable."""

    def __init__(
        self,
        profiler_classes: List[Type[ProfilerAdapter]],
        enabled_profilers: List[Type[ProfilerAdapter]],
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Profiler Settings")
        self.setMinimumWidth(320)

        self._checkboxes: Dict[Type[ProfilerAdapter], QCheckBox] = {}

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select profilers to run:"))

        for profiler_cls in profiler_classes:
            available = profiler_cls.canActivate()
            label = profiler_cls.display_name
            if not available and profiler_cls.install_hint:
                label += f"  (not installed — {profiler_cls.install_hint})"
            elif not available:
                label += "  (not available)"

            checkbox = QCheckBox(label)
            checkbox.setEnabled(available)
            checkbox.setChecked(available and profiler_cls in enabled_profilers)
            self._checkboxes[profiler_cls] = checkbox
            layout.addWidget(checkbox)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def selected_profilers(self) -> List[Type[ProfilerAdapter]]:
        """Return the list of profiler classes that are checked."""
        return [
            cls for cls, cb in self._checkboxes.items()
            if cb.isChecked() and cb.isEnabled()
        ]

