import os
import sys
import shutil
from collections import deque
from itertools import chain
from reprlib import repr
from sys import getsizeof, stderr


def sizeof_fmt(num, suffix="B"):
    """by Fred Cirera,  https://stackoverflow.com/a/1094933/1870254, modified"""
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f %s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f %s%s" % (num, "Yi", suffix)



def memory_usage_psutil():
    # return the memory usage in MB
    import psutil

    process = psutil.Process()
    mem = process.memory_info().rss / 1024**2
    return mem


def total_size(o, handlers={}, verbose=False):
    """https://code.activestate.com/recipes/577504/
    Returns the approximate memory footprint an object and all of its contents.

    Automatically finds the contents of the following builtin containers and
    their subclasses:  tuple, list, deque, dict, set and frozenset.
    To search other containers, add handlers to iterate over their contents:

        handlers = {SomeContainerClass: iter,
                    OtherContainerClass: OtherContainerClass.get_elements}
    """
    dict_handler = lambda d: chain.from_iterable(d.items())
    all_handlers = {
        tuple: iter,
        list: iter,
        deque: iter,
        dict: dict_handler,
        set: iter,
        frozenset: iter,
    }
    all_handlers.update(handlers)  # user handlers take precedence
    seen = set()  # track which object id's have already been seen
    default_size = getsizeof(0)  # estimate sizeof object without __sizeof__

    def sizeof(o):
        if id(o) in seen:  # do not double count the same object
            return 0
        seen.add(id(o))
        s = getsizeof(o, default_size)

        if verbose:
            print(s, type(o), repr(o), file=stderr)

        for typ, handler in all_handlers.items():
            if isinstance(o, typ):
                s += sum(map(sizeof, handler(o)))
                break
        return s

    return sizeof(o)


def _find_script(name: str) -> str | None:
    """Locate a pip-installed console script cross-platform.

    On Windows, pip installs scripts as .exe in a Scripts/ subdirectory
    next to the Python interpreter.  QGIS bundles its own Python, so that
    directory is usually not on PATH.
    """
    # 1. Already on PATH?
    path = shutil.which(name)
    if path:
        return path

    python_dir = os.path.dirname(sys.executable)

    if sys.platform == "win32":
        # 2. Windows: <python_dir>/Scripts/name.exe
        candidate = os.path.join(python_dir, "Scripts", name + ".exe")
        if os.path.isfile(candidate):
            return candidate

        # 3. Windows user install – pip falls back to a user location when
        #    the global site-packages directory is not writeable.
        #    %APPDATA%\Python\PythonXYY\Scripts\

        version_tag = f"Python{sys.version_info.major}{sys.version_info.minor}"
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidate = os.path.join(
                appdata, "Python", version_tag, "Scripts", name + ".exe"
            )
            if os.path.isfile(candidate):
                return candidate

    else:
        # 4. Linux/macOS: same directory as python
        candidate = os.path.join(python_dir, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

        # 5. User-local installs
        candidate = os.path.expanduser(f"~/.local/bin/{name}")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None

