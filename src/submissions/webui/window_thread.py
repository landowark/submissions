"""
Per-window worker thread for web UI windows that hold database-backed state between calls.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from functools import wraps


class WindowThread(object):
    """
    Runs every call for one window on the same thread, so the window keeps one database session for its
    lifetime, the way the Qt dialogs did. pywebview otherwise runs each call on a new thread.
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self._executor = ThreadPoolExecutor(max_workers=1)

    def run(self, func, *args, **kwargs):
        return self._executor.submit(func, *args, **kwargs).result()

    def close(self) -> None:
        self._executor.submit(self._ctx.database.session.remove)
        self._executor.shutdown(wait=False)


def on_window_thread(func):
    """
    Runs a js_api method on its window's WindowThread (self._thread).
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        return self._thread.run(func, self, *args, **kwargs)
    return wrapper