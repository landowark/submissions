'''
Contains miscellaenous functions used by both frontend and backend.
'''
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import logging, re, yaml, sys, os, stat, platform, getpass, inspect, csv
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from logging import handlers
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from pydantic import field_validator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Tuple, Literal, List
from PyQt6.QtGui import QTextDocument, QPageSize
from PyQt6.QtWebEngineWidgets import QWebEngineView
from openpyxl.worksheet.worksheet import Worksheet

# from PyQt6 import QtPrintSupport, QtCore, QtWebEngineWidgets
from PyQt6.QtPrintSupport import QPrinter

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

row_map = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H"}
row_keys = {v: k for k, v in row_map.items()}


def check_not_nan(cell_contents) -> bool:
    """
    Check to ensure excel sheet cell contents are not blank.

    Args:
        cell_contents (_type_): The contents of the cell in question.

    Returns:
        bool: True if cell has value, else, false.
    """
    # check for nan as a string first
    exclude = ['unnamed:', 'blank', 'void']
    try:
        # if "Unnamed:" in cell_contents or "blank" in cell_contents.lower():
        if cell_contents.lower() in exclude:
            cell_contents = np.nan
        cell_contents = cell_contents.lower()
    except (TypeError, AttributeError):
        pass
    try:
        if np.isnat(cell_contents):
            cell_contents = np.nan
    except TypeError as e:
        pass
    if cell_contents == "nat":
        cell_contents = np.nan
    if cell_contents == 'nan':
        cell_contents = np.nan
    if cell_contents == None:
        cell_contents = np.nan
    if str(cell_contents).lower() == "none":
        cell_contents = np.nan
    try:
        if pd.isnull(cell_contents):
            cell_contents = np.nan
    except ValueError:
        pass
    try:
        return not np.isnan(cell_contents)
    except TypeError:
        return True
    except Exception as e:
        logger.error(f"Check encountered unknown error: {type(e).__name__} - {e}")
        return False


def convert_nans_to_nones(input_str) -> str | None:
    """
    Get rid of various "nan", "NAN", "NaN", etc/

    Args:
        input_str (str): input string

    Returns:
        str: _description_
    """
    # logger.debug(f"Input value of: {input_str}")
    if check_not_nan(input_str):
        return input_str
    return None


def is_missing(value: Any) -> Tuple[Any, bool]:
    if check_not_nan(value):
        return value, False
    else:
        return convert_nans_to_nones(value), True


def check_regex_match(pattern: str, check: str) -> bool:
    """
    Determines if a pattern matches a str

    Args:
        pattern (str): regex pattern string
        check (str): string to be checked

    Returns:
        bool: match found?
    """
    try:
        return bool(re.match(fr"{pattern}", check))
    except TypeError:
        return False


def get_first_blank_df_row(df: pd.DataFrame) -> int:
    """
    For some reason I need a whole function for this.

    Args:
        df (pd.DataFrame): Input dataframe.

    Returns:
        int: Index of the row after the last used row.
    """
    return df.shape[0] + 1


# Settings

class Settings(BaseSettings, extra="allow"):
    """
    Pydantic model to hold settings

    Raises:
        FileNotFoundError: Error if database not found.

    """
    directory_path: Path
    database_path: Path | str | None = None
    backup_path: Path | str | None = None
    # super_users: list|None = None
    # power_users: list|None = None
    # rerun_regex: str
    submission_types: dict | None = None
    database_session: Session | None = None
    package: Any | None = None

    model_config = SettingsConfigDict(env_file_encoding='utf-8')

    @field_validator('backup_path', mode="before")
    @classmethod
    def set_backup_path(cls, value, values):
        match value:
            case str():
                value = Path(value)
            case None:
                value = values.data['directory_path'].joinpath("Database backups")
        if not value.exists():
            value.mkdir(parents=True)
        # metadata.backup_path = value
        return value

    @field_validator('directory_path', mode="before")
    @classmethod
    def ensure_directory_exists(cls, value):
        if isinstance(value, str):
            value = Path(value)
        if not value.exists():
            value = Path().home()
            # metadata.directory_path = value
        return value

    @field_validator('database_path', mode="before")
    @classmethod
    def ensure_database_exists(cls, value, values):
        if value == ":memory:":
            return value
        match value:
            case str():
                value = Path(value)
            case None:
                value = values.data['directory_path'].joinpath("submissions.db")
        if value.exists():
            return value
        else:
            raise FileNotFoundError(f"Couldn't find database at {value}")

    @field_validator('database_session', mode="before")
    @classmethod
    def create_database_session(cls, value, values):
        if value != None:
            return value
        else:
            database_path = values.data['database_path']
            if database_path == None:
                # check in user's .submissions directory for submissions.db
                if Path.home().joinpath(".submissions", "submissions.db").exists():
                    database_path = Path.home().joinpath(".submissions", "submissions.db")
                # finally, look in the local dir
                else:
                    database_path = package_dir.joinpath("submissions.db")
            else:
                if database_path == ":memory:":
                    pass
                # check if user defined path is directory
                elif database_path.is_dir():
                    database_path = database_path.joinpath("submissions.db")
                # check if user defined path is a file
                elif database_path.is_file():
                    database_path = database_path
                else:
                    raise FileNotFoundError("No database file found. Exiting program.")
            logger.info(f"Using {database_path} for database file.")
            engine = create_engine(f"sqlite:///{database_path}")  #, echo=True, future=True)
            session = Session(engine)
            # metadata.session = session
            return session

    @field_validator('package', mode="before")
    @classmethod
    def import_package(cls, value):
        import __init__ as package
        if value == None:
            return package

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.set_from_db(db_path=kwargs['database_path'])

    def set_from_db(self, db_path: Path):
        if 'pytest' in sys.modules:
            config_items = dict(power_users=['lwark', 'styson', 'ruwang'])
        else:
            session = Session(create_engine(f"sqlite:///{db_path}"))
            config_items = session.execute(text("SELECT * FROM _configitem")).all()
            session.close()
            config_items = {item[1]: json.loads(item[2]) for item in config_items}
        for k, v in config_items.items():
            if not hasattr(self, k):
                self.__setattr__(k, v)


def get_config(settings_path: Path | str | None = None) -> Settings:
    """
    Get configuration settings from path or default if blank.

    Args:
        settings_path (Path | str | None, optional): Path to config.yml Defaults to None.
        override (dict | None, optional): dictionary of settings to be used instead of file. Defaults to None.

    Returns:
        Settings: Pydantic settings object
    """
    # logger.debug(f"Creating settings...")
    if isinstance(settings_path, str):
        settings_path = Path(settings_path)

    # custom pyyaml constructor to join fields
    def join(loader, node):
        seq = loader.construct_sequence(node)
        return ''.join([str(i) for i in seq])

    # register the tag handler
    yaml.add_constructor('!join', join)

    # make directories
    try:
        CONFIGDIR.mkdir(parents=True)
    except FileExistsError:
        logger.warning(f"Config directory {CONFIGDIR} already exists.")

    try:
        LOGDIR.mkdir(parents=True)
    except FileExistsError:
        logger.warning(f"Logging directory {LOGDIR} already exists.")
    # NOTE: if user hasn't defined config path in cli args
    if settings_path == None:
        # NOTE: Check user .config/submissions directory
        if CONFIGDIR.joinpath("config.yml").exists():
            settings_path = CONFIGDIR.joinpath("config.yml")
        # NOTE: Check user .submissions directory
        elif Path.home().joinpath(".submissions", "config.yml").exists():
            settings_path = Path.home().joinpath(".submissions", "config.yml")
        # NOTE: finally look in the local config
        else:
            if check_if_app():
                settings_path = Path(sys._MEIPASS).joinpath("files", "config.yml")
            else:
                settings_path = package_dir.joinpath('config.yml')
            with open(settings_path, "r") as dset:
                default_settings = yaml.load(dset, Loader=yaml.Loader)
            # NOTE: Tell program we need to copy the config.yml to the user directory
            # NOTE: copy settings to config directory
            return Settings(**copy_settings(settings_path=CONFIGDIR.joinpath("config.yml"), settings=default_settings))
    else:
        # NOTE: check if user defined path is directory
        if settings_path.is_dir():
            settings_path = settings_path.joinpath("config.yml")
        # NOTE: check if user defined path is file
        elif settings_path.is_file():
            settings_path = settings_path
        else:
            logger.error("No config.yml file found. Writing to directory.")
            with open(settings_path, "r") as dset:
                default_settings = yaml.load(dset, Loader=yaml.Loader)
            return Settings(**copy_settings(settings_path=settings_path, settings=default_settings))
    # logger.debug(f"Using {settings_path} for config file.")
    with open(settings_path, "r") as stream:
        settings = yaml.load(stream, Loader=yaml.Loader)
    return Settings(**settings)


# Logging formatters

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
        prevumask = os.umask(0o002)
        rtv = handlers.RotatingFileHandler._open(self)
        os.umask(prevumask)
        return rtv


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

    format = "%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: bcolors.ENDC + format + bcolors.ENDC,
        logging.INFO: bcolors.ENDC + format + bcolors.ENDC,
        logging.WARNING: bcolors.WARNING + format + bcolors.ENDC,
        logging.ERROR: bcolors.FAIL + format + bcolors.ENDC,
        logging.CRITICAL: bcolors.FAIL + format + bcolors.ENDC
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


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


def setup_logger(verbosity: int = 3):
    """
    Set logger levels using settings.

    Args:
        verbosity (int, optional): Level of verbosity desired 3 is highest. Defaults to 3.

    Returns:
        logger: logger object
    """
    logger = logging.getLogger("submissions")
    logger.setLevel(logging.DEBUG)
    # NOTE: create file handler which logs even debug messages
    try:
        Path(LOGDIR).mkdir(parents=True)
    except FileExistsError:
        logger.warning(f"Logging directory {LOGDIR} already exists.")
    # NOTE: logging to file turned off due to repeated permission errors
    # fh = GroupWriteRotatingFileHandler(LOGDIR.joinpath('submissions.log'), mode='a', maxBytes=100000, backupCount=3, encoding=None, delay=False)
    # file logging will always be debug
    # fh.setLevel(logging.DEBUG)
    # fh.name = "File"
    # NOTE: create console handler with a higher log level
    # NOTE: create custom logger with STERR -> log
    ch = logging.StreamHandler(stream=sys.stdout)
    # NOTE: set looging level based on verbosity
    match verbosity:
        case 3:
            ch.setLevel(logging.DEBUG)
        case 2:
            ch.setLevel(logging.INFO)
        case 1:
            ch.setLevel(logging.WARNING)
    ch.name = "Stream"
    # NOTE: create formatter and add it to the handlers
    formatter = CustomFormatter()
    # fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # NOTE: add the handlers to the logger
    # logger.addHandler(fh)
    logger.addHandler(ch)

    # NOTE: Output exception and traceback to logger
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    return logger


def copy_settings(settings_path: Path, settings: dict) -> dict:
    """
    copies relevant settings dictionary from the default config.yml to a new directory

    Args:
        settings_path (Path): path to write the file to
        settings (dict): settings dictionary obtained from default config.yml

    Returns:
        dict: output dictionary for use in first run
    """
    # NOTE: if the current user is not a superuser remove the superusers entry
    if not getpass.getuser() in settings['super_users']:
        del settings['super_users']
    if not getpass.getuser() in settings['power_users']:
        del settings['power_users']
    if not settings_path.exists():
        with open(settings_path, 'w') as f:
            yaml.dump(settings, f)
    return settings


def jinja_template_loading() -> Environment:
    """
    Returns jinja2 template environment.

    Returns:
        _type_: _description_
    """
    # NOTE: determine if pyinstaller launcher is being used
    if check_if_app():
        loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
    else:
        loader_path = Path(__file__).parent.joinpath('templates').absolute()  #.__str__()
    # NOTE: jinja template loading
    loader = FileSystemLoader(loader_path)
    env = Environment(loader=loader)
    env.globals['STATIC_PREFIX'] = loader_path.joinpath("static", "css")
    return env


def check_if_app() -> bool:
    """
    Checks if the program is running from pyinstaller compiled

    Returns:
        bool: True if running from pyinstaller. Else False.
    """
    if getattr(sys, 'frozen', False):
        return True
    else:
        return False


def convert_well_to_row_column(input_str: str) -> Tuple[int, int]:
    """
    Converts typical alphanumeric (i.e. "A2") to row, column

    Args:
        input_str (str): Input string. Ex. "A2"

    Returns:
        Tuple[int, int]: row, column
    """
    row_keys = {v: k for k, v in row_map.items()}
    try:
        row = int(row_keys[input_str[0].upper()])
        column = int(input_str[1:])
    except IndexError:
        return None, None
    return row, column


def setup_lookup(func):
    """
    Checks to make sure all args are allowed

    Args:
        func (_type_): wrapped function
    """

    def wrapper(*args, **kwargs):
        sanitized_kwargs = {}
        for k, v in locals()['kwargs'].items():
            if isinstance(v, dict):
                try:
                    sanitized_kwargs[k] = v['value']
                except KeyError:
                    raise ValueError("Could not sanitize dictionary in query. Make sure you parse it first.")
            elif v is not None:
                sanitized_kwargs[k] = v
        return func(*args, **sanitized_kwargs)

    return wrapper


class Result(BaseModel):
    owner: str = Field(default="", validate_default=True)
    code: int = Field(default=0)
    msg: str
    status: Literal["NoIcon", "Question", "Information", "Warning", "Critical"] = Field(default="NoIcon")

    @field_validator('status', mode='before')
    @classmethod
    def to_title(cls, value: str):
        if value.lower().replace(" ", "") == "noicon":
            return "NoIcon"
        else:
            return value.title()

    def __repr__(self) -> str:
        return f"Result({self.owner})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = inspect.stack()[1].function

    def report(self):
        from frontend.widgets.misc import AlertPop
        return AlertPop(message=self.msg, status=self.status, owner=self.owner)


class Report(BaseModel):
    results: List[Result] = Field(default=[])

    def __repr__(self):
        return f"Report(result_count:{len(self.results)})"

    def add_result(self, result: Result | Report | None):
        match result:
            case Result():
                logger.debug(f"Adding {result} to results.")
                try:
                    self.results.append(result)
                except AttributeError:
                    logger.error(f"Problem adding result.")
            case Report():
                # logger.debug(f"Adding all results in report to new report")
                for res in result.results:
                    logger.debug(f"Adding {res} from to results.")
                    self.results.append(res)
            case _:
                logger.error(f"Unknown variable type: {type(result)}")


def rreplace(s, old, new):
    return (s[::-1].replace(old[::-1], new[::-1], 1))[::-1]


def html_to_pdf(html, output_file: Path | str):
    if isinstance(output_file, str):
        output_file = Path(output_file)
    document = QWebEngineView()
    document.setHtml(html)
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(output_file.absolute().__str__())
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    document.print(printer)


def remove_key_from_list_of_dicts(input: list, key: str):
    for item in input:
        del item[key]
    return input


def workbook_2_csv(worksheet: Worksheet, filename: Path):
    with open(filename, 'w', newline="") as f:
        c = csv.writer(f)
        for r in worksheet.rows:
            c.writerow([cell.value for cell in r])


ctx = get_config(None)


def is_power_user() -> bool:
    try:
        check = getpass.getuser() in ctx.power_users
    except:
        check = False
    return check


def check_authorization(func):
    """
    Decorator to check if user is authorized to access function

    Args:
        func (_type_): Function to be used.
    """
    def wrapper(*args, **kwargs):
        logger.debug(f"Checking authorization")
        if is_power_user():
            return func(*args, **kwargs)
        else:
            logger.error(f"User {getpass.getuser()} is not authorized for this function.")
            return dict(code=1, message="This user does not have permission for this function.", status="warning")
    return wrapper
