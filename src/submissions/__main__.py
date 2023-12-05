import sys
import os
# environment variable must be set to enable qtwebengine in network path
from tools import ctx, setup_logger, check_if_app
if check_if_app():
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"
# setup custom logger
logger = setup_logger(verbosity=3)
# create settings object

from PyQt6.QtWidgets import QApplication
from frontend.widgets.app import App

if __name__ == '__main__':
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    sys.exit(app.exec())
