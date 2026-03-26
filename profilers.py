import logging
import os
import pstats
import shutil
import subprocess
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



