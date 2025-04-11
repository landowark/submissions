import logging
import sys, os
from tools import ctx, check_if_app, CustomLogger

# NOTE: environment variable must be set to enable qtwebengine in network path
if check_if_app():
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"

# NOTE: setup custom logger
logging.setLoggerClass(CustomLogger)

from PyQt6.QtWidgets import QApplication
from frontend.widgets.app import App


if __name__ == '__main__':
    ctx.run_startup()
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    app.exec()
    sys.exit(ctx.run_teardown())
