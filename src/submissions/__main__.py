import sys
from pathlib import Path
import os
# must be set to enable qtwebengine in network path
if getattr(sys, 'frozen', False):
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"
else :
    pass
from configure import get_config, create_database_session, setup_logger
# setup custom logger
logger = setup_logger(verbosity=3)
# import config
ctx = get_config(None)
from PyQt6.QtWidgets import QApplication
from frontend import App
import __init__ as package

# create database session for use with gui session
ctx["database_session"] = create_database_session(Path(ctx['database']))
# set package information from __init__
ctx['package'] = package

if __name__ == '__main__':
    # 
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    sys.exit(app.exec())
