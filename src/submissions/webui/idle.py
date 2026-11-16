"""
Idle timeout for the web UI: closes the app after 15 minutes without mouse or keyboard activity in any of
its windows, like App.handle_timeout in the Qt app.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import threading
import webview

TIMEOUT_SECONDS = 15 * 60
CHECK_SECONDS = 30

# NOTE: Installs activity listeners the first time it runs in a page (and again after the page reloads),
# then returns the milliseconds since the last mouse/keyboard activity in that page.
PROBE = """(function () {
        if (!window.__idleSince) {
            window.__idleSince = Date.now();
            const touch = () => { window.__idleSince = Date.now(); };
            for (const type of ['mousemove', 'mousedown', 'keydown', 'wheel']) {
            document.addEventListener(type, touch, { capture: true, passive: true });
            }
        }
        return Date.now() - window.__idleSince;
        })()"""


def _idle_ms() -> float | None:
    """
    Shortest idle time across all open windows, or None if no window answered.
    """
    times = []
    for window in list(webview.windows):
        try:
            value = window.evaluate_js(PROBE)
        except Exception as e:
            logger.debug(f"Idle probe failed for {window.title}: {e}")
            continue
        if isinstance(value, (int, float)):
            times.append(value)
    return min(times) if times else None


def _watch(stop: threading.Event) -> None:
    while not stop.wait(CHECK_SECONDS):
        idle = _idle_ms()
        if idle is not None and idle >= TIMEOUT_SECONDS * 1000:
            logger.info(f"No activity for {TIMEOUT_SECONDS // 60} minutes; closing.")
            for window in list(webview.windows):
                try:
                    window.destroy()
                except Exception:
                    pass
            return
                                                                                                                
def start() -> threading.Event:
    """
    Starts the idle watcher. Pass to webview.start() so it runs once the GUI is up.

    :return: Event that stops the watcher when set.
    """
    stop = threading.Event()
    threading.Thread(target=_watch, args=(stop,), daemon=True, name="idle-watch").start()
    return stop                               