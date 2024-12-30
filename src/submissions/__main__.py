import sys, os
from tools import ctx, setup_logger, check_if_app

# environment variable must be set to enable qtwebengine in network path
if check_if_app():
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"

# setup custom logger
logger = setup_logger(verbosity=3)

# from backend import scripts
from PyQt6.QtWidgets import QApplication
from frontend.widgets.app import App


if __name__ == '__main__':
    ctx.run_startup()
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    app.exec()
    sys.exit(ctx.run_teardown())
