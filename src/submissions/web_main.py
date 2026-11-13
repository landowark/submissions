import sys
from pathlib import Path
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
    try:
        webview.start(gui="edgechromium", http_server=True, debug=not check_if_app())
    finally:
        sys.exit(ctx.run_teardown())