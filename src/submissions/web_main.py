import faulthandler
from pathlib import Path
_crash_log = Path.home().joinpath("AppData", "Local", "submissions_tng", "crash.log")
_crash_log.parent.mkdir(parents=True, exist_ok=True)
faulthandler.enable(open(_crash_log, "a"))

import sys
import os
import logging
# NOTE: Temporary diagnostics. Attaching a handler before webview is imported makes pywebview skip its own
# stderr handler, so all of its messages (incl. WebView2 start-up errors) land in this file.
_wv_logger = logging.getLogger("pywebview")
_wv_handler = logging.FileHandler(_crash_log.with_name("webview.log"), encoding="utf-8")
_wv_handler.setFormatter(logging.Formatter("%(asctime)s [pid %(process)d] %(levelname)s %(message)s"))
_wv_logger.addHandler(_wv_handler)
_wv_logger.setLevel(logging.DEBUG)
_wv_logger.info(f"start: executable={sys.executable!r} meipass={getattr(sys, '_MEIPASS', None)!r} "
                f"cwd={os.getcwd()!r} realpath={os.path.realpath(sys.executable)!r}")
import subprocess

if getattr(sys, "frozen", False) and sys.platform == "win32":
    # NOTE: Started from a mapped drive (L:\...) WebView2 fails to start; from the UNC path it works.
    # Ask Windows what the drive is mapped to and relaunch from there.
    import ctypes
    from ctypes import wintypes
    _drive, _rest = os.path.splitdrive(sys.executable)
    if len(_drive) == 2 and _drive[1] == ":":
        _remote = ctypes.create_unicode_buffer(1024)
        _size = wintypes.DWORD(len(_remote))
        # NOTE: Returns 0 (NO_ERROR) only for mapped network drives; local drives return ERROR_NOT_CONNECTED.
        _result = ctypes.windll.mpr.WNetGetConnectionW(_drive, _remote, ctypes.byref(_size))
        _wv_logger.info(f"WNetGetConnectionW({_drive!r}) -> {_result} {_remote.value!r}")
        if _result == 0:
            _wv_logger.info(f"relaunching from {_remote.value + _rest!r}")
            subprocess.Popen([_remote.value + _rest, *sys.argv[1:]], close_fds=True)
            sys.exit(0)
from tools import ctx, check_if_app
import webview
from webui.api import Api

if __name__ == '__main__':
    if check_if_app():
        static = Path(sys._MEIPASS).joinpath("files", "webui", "static")
    else:
        static = Path(__file__).parent.joinpath("webui", "static")
    ctx.run_startup()
    api = Api(ctx)
    api._window = webview.create_window(
        f"Submissions App TNG (v{ctx.package.__version__})",
        url=str(static.joinpath("index.html")), js_api=api, width=1300, height=1000)
    api._window.events.loaded += api._bind_drop
    api._window.events.shown += lambda: _wv_logger.info("window shown")
    api._window.events.closed += lambda: _wv_logger.info("window closed")
    from webui.alerts import install as install_alerts
    install_alerts(api._window)
    try:
        webview.start(gui="edgechromium", http_server=True, debug=not check_if_app())
    except Exception:
        # NOTE: Without this, the sys.exit in finally replaces the exception and the app quits silently.
        import traceback
        traceback.print_exc()
        with open(_crash_log, "a") as f:
            traceback.print_exc(file=f)
    finally:
        sys.exit(ctx.run_teardown())