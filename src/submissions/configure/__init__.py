'''
Contains functions for setting up program from config.yml and database.
'''
import yaml
import sys, os, stat, platform, getpass
import logging
from logging import handlers
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from tools import check_if_app


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


def get_config(settings_path: Path|str|None=None) -> dict:
    """
    Get configuration settings from path or default if blank.

    Args:
        settings_path (Path | str | None, optional): Path to config.yml Defaults to None.

    Returns:
        dict: Dictionary of settings.
    """    
    if isinstance(settings_path, str):
        settings_path = Path(settings_path)
    # custom pyyaml constructor to join fields
    def join(loader, node):
        seq = loader.construct_sequence(node)
        return ''.join([str(i) for i in seq])
    # register the tag handler
    yaml.add_constructor('!join', join)
    logger.debug(f"Making directory: {CONFIGDIR.__str__()}")
    # make directories
    try:
        CONFIGDIR.mkdir(parents=True)
    except FileExistsError:
        pass
    logger.debug(f"Making directory: {LOGDIR.__str__()}")
    try:
        LOGDIR.mkdir(parents=True)
    except FileExistsError:
        pass
    # if user hasn't defined config path in cli args
    copy_settings_trigger = False
    if settings_path == None:
        # Check user .config/submissions directory
        if CONFIGDIR.joinpath("config.yml").exists():
            settings_path = CONFIGDIR.joinpath("config.yml")
        # Check user .submissions directory
        elif Path.home().joinpath(".submissions", "config.yml").exists():
            settings_path = Path.home().joinpath(".submissions", "config.yml")
        # finally look in the local config
        else:
            # if getattr(sys, 'frozen', False):
            if check_if_app():
                settings_path = Path(sys._MEIPASS).joinpath("files", "config.yml")
            else:
                settings_path = package_dir.joinpath('config.yml')
            # Tell program we need to copy the config.yml to the user directory
            copy_settings_trigger = True
    else:
        # check if user defined path is directory
        if settings_path.is_dir():
            settings_path = settings_path.joinpath("config.yml")
        # check if user defined path is file
        elif settings_path.is_file():
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
    # copy settings to config directory
    if copy_settings_trigger:
        settings = copy_settings(settings_path=CONFIGDIR.joinpath("config.yml"), settings=settings)
    return settings


def create_database_session(database_path: Path|str|None=None) -> Session:
    """
    Creates a session to sqlite3 database from path or default database if database_path is blank.

    Args:
        database_path (Path | str | None, optional): path to sqlite database. Defaults to None.

    Returns:
        Session: database session
    """    
    # convert string to path object
    if isinstance(database_path, str):
        database_path = Path(database_path)
    # check if database path defined by user
    if database_path == None:
        # check in user's .submissions directory for submissions.db
        if Path.home().joinpath(".submissions", "submissions.db").exists():
            database_path = Path.home().joinpath(".submissions", "submissions.db")
        # finally, look in the local dir
        else:
            database_path = package_dir.joinpath("submissions.db")
    else:
        # check if user defined path is directory
        if database_path.is_dir():
            database_path = database_path.joinpath("submissions.db")
        # check if user defined path is a file
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
    """
    Set logger levels using settings.

    Args:
        verbosit (int, optional): Level of verbosity desired 3 is highest. Defaults to 3.

    Returns:
        logger: logger object
    """
    logger = logging.getLogger("submissions")
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    try:
        Path(LOGDIR).mkdir(parents=True)
    except FileExistsError:
        pass
    fh = GroupWriteRotatingFileHandler(LOGDIR.joinpath('submissions.log'), mode='a', maxBytes=100000, backupCount=3, encoding=None, delay=False)
    # file logging will always be debug
    fh.setLevel(logging.DEBUG)
    fh.name = "File"
    # create console handler with a higher log level
    # create custom logger with STERR -> log
    ch = logging.StreamHandler(stream=sys.stdout)
    # set looging level based on verbosity
    match verbosity:
        case 3:
            ch.setLevel(logging.DEBUG)
        case 2:
            ch.setLevel(logging.INFO)
        case 1:
            ch.setLevel(logging.WARNING)
    ch.name = "Stream"
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - {%(pathname)s:%(lineno)d} - %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    # Output exception and traceback to logger
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception
    return logger

def copy_settings(settings_path:Path, settings:dict) -> dict:
    """
    copies relevant settings dictionary from the default config.yml to a new directory

    Args:
        settings_path (Path): path to write the file to
        settings (dict): settings dictionary obtained from default config.yml

    Returns:
        dict: output dictionary for use in first run
    """    
    # if the current user is not a superuser remove the superusers entry
    if not getpass.getuser() in settings['super_users']:
        del settings['super_users']
    if not getpass.getuser() in settings['power_users']:
        del settings['power_users']
    with open(settings_path, 'w') as f:
        yaml.dump(settings, f)
    return settings
