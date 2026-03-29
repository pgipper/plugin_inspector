import logging
import os
import pstats
import shutil
import subprocess
import sys
import webbrowser
from abc import ABC, abstractmethod
from cProfile import Profile
from pathlib import Path
from pstats import SortKey

from qgis.core import QgsApplication


logger = logging.getLogger(__name__)


class ProfilerAdapter(ABC):
    display_name: str = "Unknown Profiler"
    install_hint: str = ""

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
        if shutil.which("snakeviz"):
            subprocess.Popen(["snakeviz", self.PROF_PATH])
            self._snakeviz_launched = True

    def get_summary(self) -> str:
        if getattr(self, "_snakeviz_launched", False):
            return f"cProfile: snakeviz opened in browser ({self.PROF_PATH})"
        # Fallback: show text summary when snakeviz is not available
        try:
            lines = Path(self.STATS_PATH).read_text().splitlines()[:30]
            hint = ""
            if not shutil.which("snakeviz"):
                hint = "\n💡 Install snakeviz for interactive visualization: !pip install snakeviz\n"
            return hint + "cProfile results (top entries):\n" + "\n".join(lines)
        except Exception:
            return "cProfile: results written to " + self.PROF_PATH


class YappiProfiler(ProfilerAdapter):
    """Thread-aware profiler using wall-clock time.

    Wall-time mode captures everything that happens during nested event loops
    (e.g. QDialog.exec()), because it measures elapsed real time rather than
    CPU time.  yappi also profiles *all* threads, so work offloaded to
    background threads during dialog execution becomes visible.
    """

    display_name = "yappi (wall-time)"
    install_hint = "!pip install yappi"
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
        # Wall-clock mode is key: it includes time spent waiting inside
        # modal dialog event loops, not just CPU-busy time.
        yappi.set_clock_type("wall")
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
        if shutil.which("snakeviz"):
            subprocess.Popen(["snakeviz", self.PROF_PATH])
            self._snakeviz_launched = True

    def get_summary(self) -> str:
        if getattr(self, "_snakeviz_launched", False):
            return (
                f"yappi (wall-time): snakeviz opened in browser ({self.PROF_PATH})\n"
                "ℹ️  Wall-time mode — includes time inside dialog event loops."
            )
        try:
            lines = Path(self.STATS_PATH).read_text().splitlines()[:30]
            hint = ""
            if not shutil.which("snakeviz"):
                hint = (
                    "\n💡 Install snakeviz for interactive visualization: "
                    "!pip install snakeviz\n"
                )
            return (
                hint
                + "yappi (wall-time) results — includes dialog/event-loop time:\n"
                + "\n".join(lines)
            )
        except Exception:
            return f"yappi: results written to {self.PROF_PATH}"


class VizTracerProfiler(ProfilerAdapter):
    """Timeline tracer across all threads, displayed via vizviewer."""

    display_name = "viztracer (timeline)"
    install_hint = "!pip install viztracer"
    JSON_PATH = os.path.join(
        QgsApplication.qgisSettingsDirPath(), "viztracer_report.json"
    )
    _vizviewer_proc: subprocess.Popen | None = None

    def __init__(self):
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
            max_stack_depth=15,
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
        vizviewer_path = self._find_vizviewer()
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

    @staticmethod
    def _find_vizviewer() -> str | None:
        path = shutil.which("vizviewer")
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path

        sibling = os.path.join(os.path.dirname(sys.executable), "vizviewer")
        if os.path.isfile(sibling) and os.access(sibling, os.X_OK):
            return sibling

        user_local = os.path.expanduser("~/.local/bin/vizviewer")
        if os.path.isfile(user_local) and os.access(user_local, os.X_OK):
            return user_local

        return None

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



