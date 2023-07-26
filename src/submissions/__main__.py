import sys
import os
# environment variable must be set to enable qtwebengine in network path
if getattr(sys, 'frozen', False):
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"
from tools import get_config, setup_logger
# setup custom logger
logger = setup_logger(verbosity=3)
# create settings object
ctx = get_config(None)
from PyQt6.QtWidgets import QApplication
from frontend import App

if __name__ == '__main__':
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    sys.exit(app.exec())
