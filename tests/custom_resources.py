
import sys
sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
from unittest import TestCase
from toy_database import make_toy_db
import logging

logger = logging.getLogger(f"testing.{__name__}")

class CustomFormatter(logging.Formatter):
    class bcolors:
        HEADER = '\033[95m'
        OKBLUE = '\033[94m'
        OKCYAN = '\033[96m'
        OKGREEN = '\033[92m'
        WARNING = '\033[93m'
        FAIL = '\033[91m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'

    log_format = "%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: bcolors.ENDC + log_format + bcolors.ENDC,
        logging.INFO: bcolors.ENDC + log_format + bcolors.ENDC,
        logging.WARNING: bcolors.WARNING + log_format + bcolors.ENDC,
        logging.ERROR: bcolors.FAIL + log_format + bcolors.ENDC,
        logging.CRITICAL: bcolors.FAIL + log_format + bcolors.ENDC
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)



class CustomLogger(logging.Logger):

    def __init__(self, name: str = "testing", level=logging.ERROR):
        super().__init__(name, level)
        self.extra_info = None
        self.propagate = False
        ch = logging.StreamHandler(stream=sys.stdout)
        ch.name = "Stream"
        # Ensure handler only emits ERROR or above when running tests
        ch.setLevel(logging.ERROR)
        # Simple filter to allow only ERROR and CRITICAL records
        class _ErrorOnlyFilter(logging.Filter):
            def filter(self, record):
                return record.levelno >= logging.ERROR
        ch.addFilter(_ErrorOnlyFilter())
        # NOTE: create formatter and add it to the handlers
        ch.setFormatter(CustomFormatter())
        # NOTE: add the handlers to the logger
        self.addHandler(ch)
        sys.excepthook = self.handle_exception

    def info(self, msg, *args, xtra=None, **kwargs):
        extra_info = xtra if xtra is not None else self.extra_info
        super().info(msg, *args, extra=extra_info, **kwargs)

    @classmethod
    def handle_exception(cls, exc_type, exc_value, exc_traceback):
        """
        System won't halt after error, except KeyboardInterrupt

        Args:
            exc_value ():
            exc_traceback ():

        Returns:

        """
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

logging.setLoggerClass(CustomLogger)

class DatabaseTestCase(TestCase):

    def setUp(self) -> None:
        self.engine, self.session = make_toy_db(populate=True)
        super().setUp()
        
        
    def tearDown(self) -> None:
        super().tearDown()
        try:
            self.session.close()
        except Exception:
            pass
        # Dispose the engine to close any remaining DB connections/pools
        try:
            self.engine.dispose()
        except Exception:
            pass