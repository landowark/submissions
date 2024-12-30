import sys, os
from tools import ctx, setup_logger, check_if_app, timer
from threading import Thread

# environment variable must be set to enable qtwebengine in network path
if check_if_app():
    os.environ['QTWEBENGINE_DISABLE_SANDBOX'] = "1"

# setup custom logger
logger = setup_logger(verbosity=3)

# from backend import scripts
from PyQt6.QtWidgets import QApplication
from frontend.widgets.app import App


@timer
def run_startup():
    for script in ctx.startup_scripts.values():
        logger.info(f"Running startup script: {script.__name__}")
        thread = Thread(target=script, args=(ctx,))
        thread.start()


@timer
def run_teardown():
    for script in ctx.teardown_scripts.values():
        logger.info(f"Running teardown script: {script.__name__}")
        thread = Thread(target=script, args=(ctx,))
        thread.start()


if __name__ == '__main__':
    run_startup()
    app = QApplication(['', '--no-sandbox'])
    ex = App(ctx=ctx)
    app.exec()
    sys.exit(run_teardown())
