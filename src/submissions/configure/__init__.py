import yaml
import sys, os, stat, platform, shutil
import logging
from logging import handlers
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import create_engine


logger = logging.getLogger(f"submissions.{__name__}")

package_dir = Path(__file__).parents[2].resolve()
logger.debug(f"Package dir: {package_dir}")

if platform.system() == "Windows":
    os_config_dir = "AppData/local"
    print(f"Got platform Windows, config_dir: {os_config_dir}")
else:
    os_config_dir = ".config"
    print(f"Got platform other, config_dir: {os_config_dir}")


main_aux_dir = Path.home().joinpath(f"{os_config_dir}/submissions")

CONFIGDIR = main_aux_dir.joinpath("config")
LOGDIR = main_aux_dir.joinpath("logs")




class GroupWriteRotatingFileHandler(handlers.RotatingFileHandler):

    def doRollover(self):
        """
        Override base class method to make the new log file group writable.
        """
        # Rotate the file first.
        handlers.RotatingFileHandler.doRollover(self)
        # Add group write to the current permissions.
        currMode = os.stat(self.baseFilename).st_mode
        os.chmod(self.baseFilename, currMode | stat.S_IWGRP)

    def _open(self):
        prevumask=os.umask(0o002)
        #os.fdopen(os.open('/path/to/file', os.O_WRONLY, 0600))
        rtv=handlers.RotatingFileHandler._open(self)
        os.umask(prevumask)
        return rtv


class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """

    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


def get_config(settings_path: str|None) -> dict:
    """Get configuration settings from path or default if blank.

    Args:
        settings_path (str, optional): _description_. Defaults to "".

    Returns:
        setting: dictionary of settings.
    """
    # with open("C:\\Users\\lwark\\Desktop\\packagedir.txt", "w") as f:
    #     f.write(package_dir.__str__())
    def join(loader, node):
        seq = loader.construct_sequence(node)
        return ''.join([str(i) for i in seq])
    ## register the tag handler
    yaml.add_constructor('!join', join)
    # if user hasn't defined config path in cli args
    logger.debug(f"Making directory: {CONFIGDIR.__str__()}")
    try:
        CONFIGDIR.mkdir(parents=True)
    except FileExistsError:
        pass
    logger.debug(f"Making directory: {LOGDIR.__str__()}")
    try:
        LOGDIR.mkdir(parents=True)
    except FileExistsError:
        pass
    if settings_path == None:
        # Check user .config/ozma directory
        # if Path.exists(Path.joinpath(CONFIGDIR, "config.yml")):
        #     settings_path = Path.joinpath(CONFIGDIR, "config.yml")
        if CONFIGDIR.joinpath("config.yml").exists():
            settings_path = CONFIGDIR.joinpath("config.yml")
        # Check user .ozma directory
        elif Path.home().joinpath(".submissions", "config.yml").exists():
            settings_path = Path.home().joinpath(".submissions", "config.yml")
        # finally look in the local config
        else:
            if getattr(sys, 'frozen', False):
                settings_path = Path(sys._MEIPASS).joinpath("files", "config.yml")
            else:
                settings_path = package_dir.joinpath('config.yml')
            shutil.copyfile(settings_path.__str__(), CONFIGDIR.joinpath("config.yml").__str__())
    else:
        if Path(settings_path).is_dir():
            settings_path = settings_path.joinpath("config.yml")
        elif Path(settings_path).is_file():
            settings_path = settings_path
        else:
            logger.error("No config.yml file found. Using empty dictionary.")
            return {}
    logger.debug(f"Using {settings_path} for config file.")
    
    with open(settings_path, "r") as stream:
        try:
            settings = yaml.load(stream, Loader=yaml.Loader)
        except yaml.YAMLError as exc:
            logger.error(f'Error reading yaml file {settings_path}: {exc}')
            return {}
    return settings


def create_database_session(database_path: Path|None) -> Session:
    """Get database settings from path or default if blank.

    Args:
        database_path (str, optional): _description_. Defaults to "".
    
    Returns:
        database_path: string of database path
    """
    if database_path == None:
        if Path.home().joinpath(".submissions", "submissions.db").exists():
            database_path = Path.home().joinpath(".submissions", "submissions.db")
        # finally, look in the local dir
        else:
            database_path = package_dir.joinpath("submissions.db")
    else:
        if database_path.is_dir():
            database_path = database_path.joinpath("submissions.db")
        elif database_path.is_file():
            database_path = database_path
        else:
            logger.error("No database file found. Exiting program.")
            sys.exit()
    logger.debug(f"Using {database_path} for database file.")
    engine = create_engine(f"sqlite:///{database_path}")
    session = Session(engine)
    return session


def setup_logger(verbosity:int=3):
    """Set logger levels using settings.

    Args:
        verbose (bool, optional): _description_. Defaults to False.

    Returns:
        logger: logger object
    """
    logger = logging.getLogger("submissions")
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    try:
        fh = GroupWriteRotatingFileHandler(LOGDIR.joinpath('submissions.log'), mode='a', maxBytes=100000, backupCount=3, encoding=None, delay=False)
    except FileNotFoundError as e:
        Path(LOGDIR).mkdir(parents=True, exist_ok=True)
        fh = GroupWriteRotatingFileHandler(LOGDIR.joinpath('submissions.log'), mode='a', maxBytes=100000, backupCount=3, encoding=None, delay=False)
    fh.setLevel(logging.DEBUG)
    fh.name = "File"
    # create console handler with a higher log level
    ch = logging.StreamHandler(stream=sys.stdout)
    match verbosity:
        case 3:
            ch.setLevel(logging.DEBUG)
        case 2:
            ch.setLevel(logging.INFO)
        case 1:
            ch.setLevel(logging.WARNING)
    ch.name = "Stream"
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # ch.setLevel(logging.ERROR)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    # stderr_logger = logging.getLogger('STDERR')
    
    return logger
    # sl = StreamToLogger(stderr_logger, logging.ERROR)
    # sys.stderr = sl

# def set_logger_verbosity(verbosity):
#     """Does what it says.
#     """
#     handler = [item for item in logger.parent.handlers if item.name == "Stream"][0]
#     match verbosity:
#         case 3:
#             handler.setLevel(logging.DEBUG)
#         case 2:
#             handler.setLevel(logging.INFO)
#         case 1:
#             handler.setLevel(logging.WARNING)

