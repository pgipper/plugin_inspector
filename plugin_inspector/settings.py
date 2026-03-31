from qgis.core import QgsSettings


PLUGIN_DISPLAY_NAME = "Plugin Inspector"
SETTINGS_PREFIX = "PluginInspector"


def profiler_settings_key(profiler_key: str, setting: str) -> str:
	return f"{SETTINGS_PREFIX}/profilers/{profiler_key}/{setting}"


def load_profiler_settings(profiler_classes: list) -> dict:
	qgs_settings = QgsSettings()
	type_map = {
		"bool": bool,
		"int": int,
		"str": str,
		"float": float,
	}

	loaded_settings = {}
	for profiler_cls in profiler_classes:
		profiler_key = profiler_cls.settings_key
		profiler_values = {
			"enabled": qgs_settings.value(
				profiler_settings_key(profiler_key, "enabled"),
				defaultValue=True,
				type=bool,
			)
		}

		for setting_name, schema in profiler_cls.settings_schema.items():
			default_value = schema.get("default")
			value_type = type_map.get(schema.get("type", "str"), str)
			profiler_values[setting_name] = qgs_settings.value(
				profiler_settings_key(profiler_key, setting_name),
				defaultValue=default_value,
				type=value_type,
			)

		loaded_settings[profiler_cls] = profiler_values

	return loaded_settings


def save_profiler_settings(profiler_classes: list, settings: dict) -> None:
	qgs_settings = QgsSettings()

	for profiler_cls in profiler_classes:
		profiler_key = profiler_cls.settings_key
		profiler_values = settings.get(profiler_cls, {})

		qgs_settings.setValue(
			profiler_settings_key(profiler_key, "enabled"),
			profiler_values.get("enabled", True),
		)

		for setting_name, schema in profiler_cls.settings_schema.items():
			qgs_settings.setValue(
				profiler_settings_key(profiler_key, setting_name),
				profiler_values.get(setting_name, schema.get("default")),
			)
