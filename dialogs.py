import logging
from typing import Any, Dict, List, Type

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
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
        profiler_settings: Dict[Type[ProfilerAdapter], Dict[str, Any]],
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Profiler Settings")
        self.setMinimumWidth(320)

        self._checkboxes: Dict[Type[ProfilerAdapter], QCheckBox] = {}
        self._settings_widgets: Dict[Type[ProfilerAdapter], Dict[str, QWidget]] = {}
        self._profiler_settings: Dict[Type[ProfilerAdapter], Dict[str, Any]] = {}

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Select profilers to run:"))

        for profiler_cls in profiler_classes:
            available = profiler_cls.canActivate()
            current_settings = dict(profiler_settings.get(profiler_cls, {}))
            current_enabled = bool(current_settings.get("enabled", True))
            self._profiler_settings[profiler_cls] = current_settings

            label = profiler_cls.display_name
            if not available and profiler_cls.install_hint:
                label += f"  (not installed — {profiler_cls.install_hint})"
            elif not available:
                label += "  (not available)"

            checkbox = QCheckBox(label)
            checkbox.setEnabled(available)
            checkbox.setChecked(available and current_enabled)
            self._checkboxes[profiler_cls] = checkbox
            layout.addWidget(checkbox)

            settings_schema = getattr(profiler_cls, "settings_schema", {}) or {}
            if settings_schema:
                settings_group = QGroupBox()
                settings_group.setFlat(True)
                settings_form = QFormLayout()
                settings_form.setContentsMargins(24, 0, 0, 0)
                settings_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

                profiler_widgets: Dict[str, QWidget] = {}

                for setting_key, setting_schema in settings_schema.items():
                    schema = setting_schema if isinstance(setting_schema, dict) else {}
                    setting_type = schema.get("type", "str")
                    setting_label = str(schema.get("label", setting_key))
                    value = current_settings.get(setting_key, schema.get("default"))

                    widget: QWidget
                    if setting_type == "bool":
                        bool_widget = QCheckBox()
                        bool_widget.setChecked(bool(value) if value is not None else False)
                        widget = bool_widget
                    elif setting_type == "int":
                        int_widget = QSpinBox()
                        int_widget.setRange(-1, 999999)
                        int_widget.setValue(int(value) if value is not None else 0)
                        widget = int_widget
                    elif setting_type == "float":
                        float_widget = QDoubleSpinBox()
                        float_widget.setRange(-1.0, 999999.0)
                        float_widget.setValue(float(value) if value is not None else 0.0)
                        widget = float_widget
                    else:
                        str_widget = QLineEdit()
                        str_widget.setText(str(value) if value is not None else "")
                        widget = str_widget

                    settings_form.addRow(setting_label, widget)
                    profiler_widgets[setting_key] = widget

                self._settings_widgets[profiler_cls] = profiler_widgets
                settings_group.setLayout(settings_form)
                checkbox.toggled.connect(settings_group.setEnabled)
                settings_group.setEnabled(available and checkbox.isChecked())
                if not available:
                    settings_group.setEnabled(False)
                layout.addWidget(settings_group)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def get_settings(self) -> Dict[Type[ProfilerAdapter], Dict[str, Any]]:
        """Return updated settings while preserving non-enabled values."""
        updated_settings: Dict[Type[ProfilerAdapter], Dict[str, Any]] = {}
        for profiler_cls, checkbox in self._checkboxes.items():
            values = dict(self._profiler_settings.get(profiler_cls, {}))
            values["enabled"] = checkbox.isChecked()

            for key, widget in self._settings_widgets.get(profiler_cls, {}).items():
                if isinstance(widget, QCheckBox):
                    values[key] = widget.isChecked()
                elif isinstance(widget, QSpinBox):
                    values[key] = widget.value()
                elif isinstance(widget, QDoubleSpinBox):
                    values[key] = widget.value()
                elif isinstance(widget, QLineEdit):
                    values[key] = widget.text()

            updated_settings[profiler_cls] = values
        return updated_settings

    def selected_profilers(self) -> List[Type[ProfilerAdapter]]:
        """Return the list of profiler classes that are checked."""
        settings = self.get_settings()
        return [
            cls for cls, cb in self._checkboxes.items()
            if cb.isEnabled() and settings.get(cls, {}).get("enabled", False)
        ]

