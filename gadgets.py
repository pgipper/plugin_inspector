import sys
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


def get_sizof_log():
    txt = ""
    for name, size in sorted(
        ((name, sys.getsizeof(value)) for name, value in list(globals().items())),
        key=lambda x: -x[1],
    )[:10]:
        txt += f"{name:>30}: {sizeof_fmt(size):>8}\n"
    return txt


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


def writeProfileToCsv(stats: str, path: str, delimiter: str = ","):
    stats = "ncalls" + stats.split("ncalls")[-1]
    stats = "\n".join(
        [delimiter.join(line.rstrip().split(None, 6)) for line in stats.split("\n")]
    )

    with open(path, "w") as file:
        file.write(stats)
