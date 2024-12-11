import sys, os
from tools import ctx, setup_logger, check_if_app
from backend import scripts

# environment variable must be set to enable qtwebengine in network path
if check_if_app():
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"

# setup custom logger
logger = setup_logger(verbosity=3)

from PyQt6.QtWidgets import QApplication
from frontend.widgets.app import App


def run_startup():
    try:
        startup_scripts = ctx.startup_scripts
    except AttributeError as e:
        logger.error(f"Couldn't get startup scripts due to {e}")
        return
    for script in startup_scripts:
        try:
            func = getattr(scripts, script)
        except AttributeError as e:
            logger.error(f"Couldn't run startup script {script} due to {e}")
            continue
        func(ctx)


def run_teardown():
    try:
        teardown_scripts = ctx.teardown_scripts
    except AttributeError as e:
        logger.error(f"Couldn't get teardown scripts due to {e}")
        return
    for script in teardown_scripts:
        try:
            func = getattr(scripts, script)
        except AttributeError as e:
            logger.error(f"Couldn't run teardown script {script} due to {e}")
            continue
        func(ctx)

if __name__ == '__main__':
    run_startup()
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    app.exec()
    sys.exit(run_teardown())
