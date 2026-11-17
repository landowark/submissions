import time
_t0 = time.time()
def mark(step: str) -> None:
    """
    Prints a startup timing step to the console (stdout). Does nothing in the windowed exe, which has no console.
    """
    print(f"[startup] {time.time() - _t0:6.2f}s  {step}", flush=True)
mark("python running")
import faulthandler
from pathlib import Path
_crash_log = Path.home().joinpath("AppData", "Local", "submissions_tng", "crash.log")
_crash_log.parent.mkdir(parents=True, exist_ok=True)
# NOTE: Writes a traceback for native crashes that never reach Python logging.
faulthandler.enable(open(_crash_log, "a"))
import sys
import logging
from tools import ctx, check_if_app, CustomLogger
mark("tools/ctx loaded (config, database, set_from_db)")
# NOTE: Same logger setup as the Qt __main__.py. Without it, every submissions.* debug/info message is dropped.
logging.setLoggerClass(CustomLogger)
import webview
from webui.api import Api
mark("webview + webui imported")
from webui import idle


def close_other_windows(main) -> None:
    """
    Closing the main window quits the app, as in the Qt app. pywebview otherwise keeps running
    until the last window is closed.
    """
    for window in list(webview.windows):
        if window is not main:
            try:
                window.destroy()
            except Exception:
                pass


if __name__ == '__main__':
    if check_if_app():
        static = Path(sys._MEIPASS).joinpath("files", "webui", "static")
    else:
        static = Path(__file__).parent.joinpath("webui", "static")
    ctx.run_startup()
    mark("startup scripts started")
    api = Api(ctx)
    api._window = webview.create_window(
        f"Submissions App TNG (v{ctx.package.__version__})",
        url=str(static.joinpath("index.html")), js_api=api, width=1300, height=1000)
    api._window.events.loaded += api._bind_drop
    api._window.events.closed += lambda: close_other_windows(api._window)
    mark("main window shown")
    from webui.alerts import install as install_alerts
    install_alerts(api._window)
    mark("calling webview.start")
    try:
        webview.start(idle.start, gui="edgechromium", http_server=True, debug=not check_if_app())
    except Exception:
        # NOTE: Without this, the sys.exit in finally replaces the exception and the app quits silently.
        import traceback
        traceback.print_exc()
        with open(_crash_log, "a") as f:
            traceback.print_exc(file=f)
    finally:
        sys.exit(ctx.run_teardown())