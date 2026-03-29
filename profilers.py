import logging
import os
import pstats
import subprocess
import webbrowser
from abc import ABC, abstractmethod
from cProfile import Profile
from pathlib import Path
from pstats import SortKey

from qgis.core import QgsApplication

from .gadgets import _find_script


logger = logging.getLogger(__name__)


class ProfilerAdapter(ABC):
    display_name: str = "Unknown Profiler"
    install_hint: str = ""
    settings_key: str = ""
    settings_schema: dict = {}

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

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

    def get_summary(self) -> str:
        """Return a short text summary of the profiling results, or empty string."""
        return ""


class PyinstrumentProfiler(ProfilerAdapter):
    display_name = "pyinstrument"
    install_hint = "!pip install pyinstrument"
    settings_key = "pyinstrument"
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

    def get_summary(self) -> str:
        return f"pyinstrument: HTML report opened in browser ({self.HTML_PATH})"


class cProfileProfiler(ProfilerAdapter):
    display_name = "cProfile"
    install_hint = "!pip install snakeviz (optional, for interactive visualization)"
    settings_key = "cprofile"
    PROF_PATH = os.path.join(QgsApplication.qgisSettingsDirPath(), "cProfile_dump.prof")
    STATS_PATH = os.path.join(QgsApplication.qgisSettingsDirPath(), "pstats_dump.txt")

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

        # Write human-readable stats text file
        with open(self.STATS_PATH, "w") as file:
            ps = pstats.Stats(self.PROF_PATH, stream=file)
            ps.sort_stats(SortKey.CUMULATIVE)
            ps.print_stats()

        # Launch snakeviz if available (opens interactive browser visualization)
        self._snakeviz_launched = False
        snakeviz = _find_script("snakeviz")
        if snakeviz:
            subprocess.Popen([snakeviz, self.PROF_PATH])
            self._snakeviz_launched = True

    def get_summary(self) -> str:
        if getattr(self, "_snakeviz_launched", False):
            return f"cProfile: snakeviz opened in browser ({self.PROF_PATH})"
        # Fallback: show text summary when snakeviz is not available
        try:
            lines = Path(self.STATS_PATH).read_text().splitlines()[:30]
            hint = ""
            if not _find_script("snakeviz"):
                hint = "\n💡 Install snakeviz for interactive visualization: !pip install snakeviz\n"
            return hint + "cProfile results (top entries):\n" + "\n".join(lines)
        except Exception:
            return "cProfile: results written to " + self.PROF_PATH


class YappiProfiler(ProfilerAdapter):
    """Thread-aware profiler with configurable clock type.

    In wall-time mode, yappi captures everything that happens during nested
    event loops (e.g. QDialog.exec()), because it measures elapsed real time
    rather than CPU time. yappi also profiles *all* threads, so work
    offloaded to background threads during dialog execution becomes visible.
    """

    display_name = "yappi"
    install_hint = "!pip install yappi"
    settings_key = "yappi"
    settings_schema = {
        "use_wall_time": {
            "type": "bool",
            "default": True,
            "label": "Use wall-clock time (vs CPU time)",
        }
    }
    PROF_PATH = os.path.join(
        QgsApplication.qgisSettingsDirPath(), "yappi_wall.prof"
    )
    STATS_PATH = os.path.join(
        QgsApplication.qgisSettingsDirPath(), "yappi_wall.txt"
    )

    @classmethod
    def canActivate(cls) -> bool:
        try:
            import yappi  # noqa: F401
        except ImportError:
            return False
        return True

    def start(self):
        import yappi

        yappi.clear_stats()
        clock = "wall" if self._settings.get("use_wall_time", True) else "cpu"
        yappi.set_clock_type(clock)
        yappi.start(builtins=True)

    def stop(self):
        import yappi

        yappi.stop()
        func_stats = yappi.get_func_stats()

        # Save pstat-compatible file (usable by snakeviz / other tools)
        func_stats.save(self.PROF_PATH, type="pstat")

        # Save human-readable text summary
        try:
            with open(self.STATS_PATH, "w") as f:
                func_stats.print_all(out=f)
        except Exception as ex:
            logger.warning("Could not write yappi text stats: %s", ex)

        # Try snakeviz for interactive visualisation
        self._snakeviz_launched = False
        snakeviz = _find_script("snakeviz")
        if snakeviz:
            subprocess.Popen([snakeviz, self.PROF_PATH])
            self._snakeviz_launched = True

    def get_summary(self) -> str:
        clock_label = (
            "wall-time" if self._settings.get("use_wall_time", True) else "cpu-time"
        )
        if getattr(self, "_snakeviz_launched", False):
            summary = f"yappi ({clock_label}): snakeviz opened in browser ({self.PROF_PATH})"
            if self._settings.get("use_wall_time", True):
                summary += "\nℹ️  Wall-time mode — includes time inside dialog event loops."
            return summary
        try:
            lines = Path(self.STATS_PATH).read_text().splitlines()[:30]
            hint = ""
            if not _find_script("snakeviz"):
                hint = (
                    "\n💡 Install snakeviz for interactive visualization: "
                    "!pip install snakeviz\n"
                )
            title = f"yappi ({clock_label}) results"
            if self._settings.get("use_wall_time", True):
                title += " — includes dialog/event-loop time"
            return hint + title + ":\n" + "\n".join(lines)
        except Exception:
            return f"yappi: results written to {self.PROF_PATH}"


class VizTracerProfiler(ProfilerAdapter):
    """Timeline tracer across all threads, displayed via vizviewer."""

    display_name = "viztracer (timeline)"
    install_hint = "!pip install viztracer"
    settings_key = "viztracer"
    settings_schema = {
        "max_stack_depth": {
            "type": "int",
            "default": -1,
            "label": "Max stack depth (-1 = unlimited)",
        },
        "log_func_args": {
            "type": "bool",
            "default": False,
            "label": "Log function arguments",
        },
        "log_func_retval": {
            "type": "bool",
            "default": False,
            "label": "Log return values",
        },
        "log_gc": {
            "type": "bool",
            "default": False,
            "label": "Log garbage collection",
        },
        "ignore_c_function": {
            "type": "bool",
            "default": False,
            "label": "Ignore C extension functions",
        },
        "ignore_frozen": {
            "type": "bool",
            "default": False,
            "label": "Ignore frozen/importlib modules",
        },
        "log_print": {
            "type": "bool",
            "default": False,
            "label": "Capture print() in timeline",
        },
        "log_async": {
            "type": "bool",
            "default": False,
            "label": "Trace async/await",
        },
        "min_duration": {
            "type": "float",
            "default": 0,
            "label": "Min duration µs (0 = all)",
        },
        "minimize_memory": {
            "type": "bool",
            "default": False,
            "label": "Minimize memory usage",
        },
    }
    JSON_PATH = os.path.join(
        QgsApplication.qgisSettingsDirPath(), "viztracer_report.json"
    )
    _vizviewer_proc: subprocess.Popen | None = None

    def __init__(self, settings: dict | None = None):
        super().__init__(settings)
        self.tracer = None
        self._vizviewer_launched = False

    @classmethod
    def canActivate(cls) -> bool:
        try:
            from viztracer import VizTracer  # noqa: F401
        except ImportError:
            return False
        return True

    def start(self):
        from viztracer import VizTracer

        try:
            os.remove(self.JSON_PATH)
        except FileNotFoundError:
            pass

        self.tracer = VizTracer(
            output_file=self.JSON_PATH,
            max_stack_depth=self._settings.get("max_stack_depth", -1),
            log_func_args=self._settings.get("log_func_args", False),
            log_func_retval=self._settings.get("log_func_retval", False),
            log_gc=self._settings.get("log_gc", False),
            ignore_c_function=self._settings.get("ignore_c_function", False),
            ignore_frozen=self._settings.get("ignore_frozen", False),
            log_print=self._settings.get("log_print", False),
            log_async=self._settings.get("log_async", False),
            min_duration=self._settings.get("min_duration", 0),
            minimize_memory=self._settings.get("minimize_memory", False),
        )
        self.tracer.start()

    def stop(self):
        self._vizviewer_launched = False
        self.tracer.stop()
        self.tracer.save()

        # Kill previous vizviewer (it binds a port)
        if VizTracerProfiler._vizviewer_proc is not None:
            try:
                VizTracerProfiler._vizviewer_proc.terminate()
                VizTracerProfiler._vizviewer_proc.wait(timeout=5)
            except Exception:
                pass
            VizTracerProfiler._vizviewer_proc = None

        # Release C-level tracer so a new session can start
        try:
            self.tracer.clear()
        except Exception:
            pass
        self.tracer = None

        # Launch vizviewer if available
        vizviewer_path = _find_script("vizviewer")
        if vizviewer_path and os.path.isfile(self.JSON_PATH) and os.path.getsize(self.JSON_PATH) > 0:
            try:
                proc = subprocess.Popen([vizviewer_path, "--once", self.JSON_PATH])
                VizTracerProfiler._vizviewer_proc = proc
                self._vizviewer_launched = True
            except OSError as ex:
                logger.warning("Could not launch vizviewer: %s", ex)
        else:
            logger.warning(
                "viztracer: could not launch vizviewer for %s. Install hint: %s",
                self.JSON_PATH,
                self.install_hint,
            )

    def get_summary(self) -> str:
        if self._vizviewer_launched:
            return (
                f"viztracer: timeline opened in vizviewer ({self.JSON_PATH})\n"
                "ℹ️  Timeline shows all function calls chronologically, "
                "including those inside dialogs and across threads."
            )
        return (
            f"viztracer: trace saved to {self.JSON_PATH}.\n"
            "Run manually with: vizviewer --once "
            f"{self.JSON_PATH}"
        )



