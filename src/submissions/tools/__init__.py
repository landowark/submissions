'''
Contains miscellaenous functions used by both frontend and backend.
'''
from __future__ import annotations

import json
import pprint
from json import JSONDecodeError
import numpy as np
import logging, re, yaml, sys, os, stat, platform, getpass, inspect, csv
import pandas as pd
from jinja2 import Environment, FileSystemLoader
from logging import handlers
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text, MetaData
from pydantic import field_validator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Tuple, Literal, List
from PyQt6.QtGui import QPageSize
from PyQt6.QtWebEngineWidgets import QWebEngineView
from openpyxl.worksheet.worksheet import Worksheet
from PyQt6.QtPrintSupport import QPrinter
from __init__ import project_path
from configparser import ConfigParser
from tkinter import Tk  # from tkinter import Tk for Python 3.x
from tkinter.filedialog import askdirectory

logger = logging.getLogger(f"submissions.{__name__}")

# package_dir = Path(__file__).parents[2].resolve()
# package_dir = project_path
logger.debug(f"Package dir: {project_path}")

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

main_form_style = '''
                        QComboBox:!editable, QDateEdit {
                            background-color:light gray;
                        }

                '''


def divide_chunks(input_list: list, chunk_count: int):
    """
    Divides a list into {chunk_count} equal parts

    Args:
        input_list (list): Initials list
        chunk_count (int): size of each chunk

    Returns:
        tuple: tuple containing sublists.
    """
    k, m = divmod(len(input_list), chunk_count)
    return (input_list[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(chunk_count))


def get_unique_values_in_df_column(df: pd.DataFrame, column_name: str) -> list:
    """
    get all unique values in a dataframe column by name

    Args:
        df (DataFrame): input dataframe
        column_name (str): name of column of interest

    Returns:
        list: sorted list of unique values
    """
    return sorted(df[column_name].unique())


def check_key_or_attr(key: str, interest: dict | object, check_none: bool = False) -> bool:
    """
    Checks if key exists in dict or object has attribute.

    Args:
        key (str): key or attribute name
        interest (dict | object): Dictionary or object to be checked.
        check_none (bool, optional): Return false if value exists, but is None. Defaults to False.

    Returns:
        bool: True if exists, else False
    """
    match interest:
        case dict():
            if key in interest.keys():
                if check_none:
                    match interest[key]:
                        case dict():
                            if 'value' in interest[key].keys():
                                try:
                                    check = interest[key]['value'] is None
                                except KeyError:
                                    check = True
                                if check:
                                    return False
                                else:
                                    return True
                            else:
                                try:
                                    check = interest[key] is None
                                except KeyError:
                                    check = True
                                if check:
                                    return False
                                else:
                                    return True
                        case _:
                            if interest[key] is None:
                                return False
                            else:
                                return True
                else:
                    return True
            return False
        case object():
            if hasattr(interest, key):
                if check_none:
                    if interest.__getattribute__(key) is None:
                        return False
                    else:
                        return True
                else:
                    return True
            return False


def check_not_nan(cell_contents) -> bool:
    """
    Check to ensure excel sheet cell contents are not blank.

    Args:
        cell_contents (_type_): The contents of the cell in question.

    Returns:
        bool: True if cell has value, else, false.
    """
    # NOTE: check for nan as a string first
    exclude = ['unnamed:', 'blank', 'void']
    try:
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
    if cell_contents is None:
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
    """
    Checks if a parsed value is missing.

    Args:
        value (Any): Incoming value

    Returns:
        Tuple[Any, bool]: Value, True if nan, else False
    """
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
    database_schema: str | None = None
    directory_path: Path | None = None
    database_user: str | None = None
    database_password: str | None = None
    database_name: str | None = None
    database_path: Path | str | None = None
    backup_path: Path | str | None = None
    submission_types: dict | None = None
    database_session: Session | None = None
    package: Any | None = None

    model_config = SettingsConfigDict(env_file_encoding='utf-8')

    @field_validator('database_schema', mode="before")
    @classmethod
    def set_schema(cls, value):
        if value is None:
            # print("No value for dir path")
            if check_if_app():
                alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
            else:
                alembic_path = project_path.joinpath("alembic.ini")
            # print(f"Getting alembic path: {alembic_path}")
            value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='schema')
        if value is None:
            value = "sqlite"
        return value

    @field_validator('backup_path', mode="before")
    @classmethod
    def set_backup_path(cls, value, values):
        match value:
            case str():
                value = Path(value)
            case None:
                value = values.data['directory_path'].joinpath("Database backups")
        if not value.exists():
            try:
                value.mkdir(parents=True)
            except OSError:
                value = Path(askdirectory(title="Directory for backups."))
        return value

    @field_validator('directory_path', mode="before")
    @classmethod
    def ensure_directory_exists(cls, value, values):
        if value is None:
            match values.data['database_schema']:
                case "sqlite":
                    # print("No value for dir path")
                    if check_if_app():
                        alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
                    else:
                        alembic_path = project_path.joinpath("alembic.ini")
                    # print(f"Getting alembic path: {alembic_path}")
                    value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='path').parent
                    # print(f"Using {value}")
                case _:
                    Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
                    value = Path(askdirectory(
                        title="Select directory for DB storage"))  # show an "Open" dialog box and return the path to the selected file
        if isinstance(value, str):
            value = Path(value)
        try:
            check = value.exists()
        except AttributeError:
            check = False
        if not check:  # and values.data['database_schema'] == "sqlite":
            # print(f"No directory found, using Documents/submissions")
            value.mkdir(exist_ok=True)
        # print(f"Final return of directory_path: {value}")
        return value

    @field_validator('database_path', mode="before")
    @classmethod
    def ensure_database_exists(cls, value, values):
        match values.data['database_schema']:
            case "sqlite":
                if value is None:
                    value = values.data['directory_path']
                if isinstance(value, str):
                    value = Path(value)
            case _:
                if value is None:
                    if check_if_app():
                        alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
                    else:
                        alembic_path = project_path.joinpath("alembic.ini")
                    # print(f"Getting alembic path: {alembic_path}")
                    value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='path').parent
        return value

    @field_validator('database_name', mode='before')
    @classmethod
    def get_database_name(cls, value):
        if value is None:
            if check_if_app():
                alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
            else:
                alembic_path = project_path.joinpath("alembic.ini")
            # print(f"Getting alembic path: {alembic_path}")
            value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='path').stem
        return value

    @field_validator("database_user", mode='before')
    @classmethod
    def get_user(cls, value):
        if value is None:
            if check_if_app():
                alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
            else:
                alembic_path = project_path.joinpath("alembic.ini")
            # print(f"Getting alembic path: {alembic_path}")
            value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='user')
            # print(f"Got {value} for user")
        return value

    @field_validator("database_password", mode='before')
    @classmethod
    def get_pass(cls, value):
        if value is None:
            if check_if_app():
                alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
            else:
                alembic_path = project_path.joinpath("alembic.ini")
            # print(f"Getting alembic path: {alembic_path}")
            value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='pass')
            # print(f"Got {value} for pass")
        return value

    @field_validator('database_session', mode="before")
    @classmethod
    def create_database_session(cls, value, values):
        if value is not None:
            return value
        else:
            match values.data['database_schema']:
                case "sqlite":
                    value = f"/{values.data['database_path']}"
                    db_name = f"{values.data['database_name']}.db"
                case _:
                    # print(pprint.pprint(values.data))
                    tmp = jinja_template_loading().from_string(
                        "{% if values['database_user'] %}{{ values['database_user'] }}{% if values['database_password'] %}:{{ values['database_password'] }}{% endif %}{% endif %}@{{ values['database_path'] }}")
                    value = tmp.render(values=values.data)
                    db_name = values.data['database_name']
            template = jinja_template_loading().from_string(
                "{{ values['database_schema'] }}://{{ value }}/{{ db_name }}")
            database_path = template.render(values=values.data, value=value, db_name=db_name)
            # print(f"Using {database_path} for database path")
            engine = create_engine(database_path)
            session = Session(engine)
            return session

    @field_validator('package', mode="before")
    @classmethod
    def import_package(cls, value):
        import __init__ as package
        if value is None:
            return package

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.set_from_db()

    def set_from_db(self):
        if 'pytest' in sys.modules:
            output = dict(power_users=['lwark', 'styson', 'ruwang'])
        else:
            print(f"Hello from database settings getter.")
            # print(self.__dict__)
            session = self.database_session
            metadata = MetaData()
            # print(self.database_session.get_bind())
            try:
                metadata.reflect(bind=session.get_bind())
            except AttributeError as e:
                print(f"Error getting tables: {e}")
                return
            if "_configitem" not in metadata.tables.keys():
                print(f"Couldn't find _configitems in {metadata.tables.keys()}.")
                return
            config_items = session.execute(text("SELECT * FROM _configitem")).all()
            # print(f"Config: {pprint.pprint(config_items)}")
            output = {}
            for item in config_items:
                try:
                    output[item[1]] = json.loads(item[2])
                except (JSONDecodeError, TypeError):
                    output[item[1]] = item[2]
        for k, v in output.items():
            if not hasattr(self, k):
                self.__setattr__(k, v)

    @classmethod
    def get_alembic_db_path(cls, alembic_path, mode=Literal['path', 'schema', 'user', 'pass']) -> Path | str:
        c = ConfigParser()
        c.read(alembic_path)
        url = c['alembic']['sqlalchemy.url']
        match mode:
            case 'path':
                path = re.sub(r"^.*//", "", url)
                path = re.sub(r"^.*@", "", path)
                return Path(path)
            case "schema":
                return url[:url.index(":")]
            case "user":
                url = re.sub(r"^.*//", "", url)
                try:
                    return url[:url.index("@")].split(":")[0]
                except (IndexError, ValueError) as e:
                    # print(f"Error on user: {e}")
                    return None
            case "pass":
                url = re.sub(r"^.*//", "", url)
                try:
                    return url[:url.index("@")].split(":")[1]
                except (IndexError, ValueError) as e:
                    # print(f"Error on user: {e}")
                    return None

    def save(self, settings_path: Path):
        if not settings_path.exists():
            dicto = {}
            for k, v in self.__dict__.items():
                if k in ['package', 'database_session', 'submission_types']:
                    continue
                match v:
                    case Path():
                        # print("Path")
                        if v.is_dir():
                            # print("dir")
                            v = v.absolute().__str__()
                        elif v.is_file():
                            # print("file")
                            v = v.parent.absolute().__str__()
                        else:
                            v = v.__str__()
                    case _:
                        pass
                # print(f"Key: {k}, Value: {v}")
                dicto[k] = v
            with open(settings_path, 'w') as f:
                yaml.dump(dicto, f)


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

    # NOTE: custom pyyaml constructor to join fields
    def join(loader, node):
        seq = loader.construct_sequence(node)
        return ''.join([str(i) for i in seq])

    # register the tag handler
    yaml.add_constructor('!join', join)
    # NOTE: make directories
    try:
        CONFIGDIR.mkdir(parents=True)
    except FileExistsError:
        logger.warning(f"Config directory {CONFIGDIR} already exists.")
    try:
        LOGDIR.mkdir(parents=True)
    except FileExistsError:
        logger.warning(f"Logging directory {LOGDIR} already exists.")
    # NOTE: if user hasn't defined config path in cli args
    if settings_path is None:
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
                settings_path = project_path.joinpath('src', 'config.yml')
            with open(settings_path, "r") as dset:
                default_settings = yaml.load(dset, Loader=yaml.Loader)
            # NOTE: Tell program we need to copy the config.yml to the user directory
            # NOTE: copy settings to config directory
            settings = Settings(**default_settings)
            settings.save(settings_path=CONFIGDIR.joinpath("config.yml"))
            # print(f"Default settings: {pprint.pprint(settings.__dict__)}")
            return settings
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
            settings = Settings(**default_settings)
            settings.save(settings_path=settings_path)
    # logger.debug(f"Using {settings_path} for config file.")
    with open(settings_path, "r") as stream:
        settings = yaml.load(stream, Loader=yaml.Loader)
    return Settings(**settings)


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


# Logging formatters

class GroupWriteRotatingFileHandler(handlers.RotatingFileHandler):

    def doRollover(self):
        """
        Override base class method to make the new log file group writable.
        """
        # NOTE: Rotate the file first.
        handlers.RotatingFileHandler.doRollover(self)
        # NOTE: Add group write to the current permissions.
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

    log_format = "%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: bcolors.ENDC + log_format + bcolors.ENDC,
        logging.INFO: bcolors.ENDC + log_format + bcolors.ENDC,
        logging.WARNING: bcolors.WARNING + log_format + bcolors.ENDC,
        logging.ERROR: bcolors.FAIL + log_format + bcolors.ENDC,
        logging.CRITICAL: bcolors.FAIL + log_format + bcolors.ENDC
    }

    def format(self, record):
        if check_if_app():
            log_fmt = self.log_format
        else:
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

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    logger = logging.getLogger("submissions")
    logger.setLevel(logging.DEBUG)
    # NOTE: create file handler which logs even debug messages
    try:
        Path(LOGDIR).mkdir(parents=True)
    except FileExistsError:
        logger.warning(f"Logging directory {LOGDIR} already exists.")
    # NOTE: logging to file turned off due to repeated permission errors
    # NOTE: create console handler with a higher log level
    # NOTE: create custom logger with STERR -> log
    ch = logging.StreamHandler(stream=sys.stdout)
    # NOTE: set logging level based on verbosity
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
    ch.setFormatter(formatter)
    # NOTE: add the handlers to the logger
    logger.addHandler(ch)
    # NOTE: Output exception and traceback to logger
    sys.excepthook = handle_exception
    return logger


def jinja_template_loading() -> Environment:
    """
    Returns jinja2 template environment.

    Returns:
        Environment: jinja2 environment object
    """
    # NOTE: determine if pyinstaller launcher is being used
    if check_if_app():
        loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
    else:
        loader_path = Path(__file__).parents[1].joinpath('templates').absolute()  # .__str__()
    # NOTE: jinja template loading
    loader = FileSystemLoader(loader_path)
    env = Environment(loader=loader)
    env.globals['STATIC_PREFIX'] = loader_path.joinpath("static", "css")
    return env


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
        logger.debug(f"sanitized kwargs: {sanitized_kwargs}")
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
        """
        Takes a result object or all results in another report and adds them to this one.

        Args:
            result (Result | Report | None): Results to be added.
        """
        match result:
            case Result():
                logger.info(f"Adding {result} to results.")
                try:
                    self.results.append(result)
                except AttributeError:
                    logger.error(f"Problem adding result.")
            case Report():
                # logger.debug(f"Adding all results in report to new report")
                for res in result.results:
                    logger.info(f"Adding {res} from {result} to results.")
                    self.results.append(res)
            case _:
                logger.error(f"Unknown variable type: {type(result)} for <Result> entry into <Report>")


def rreplace(s: str, old: str, new: str) -> str:
    """
    Removes rightmost occurence of a substring

    Args:
        s (str): input string
        old (str): original substring
        new (str): new substring

    Returns:
        str: updated string
    """
    return (s[::-1].replace(old[::-1], new[::-1], 1))[::-1]


def html_to_pdf(html: str, output_file: Path | str):
    """
    Attempts to print an html string as a PDF. (currently not working)

    Args:
        html (str): Input html string.
        output_file (Path | str): Output PDF file path.
    """
    if isinstance(output_file, str):
        output_file = Path(output_file)
    logger.debug(f"Printing PDF to {output_file}")
    document = QWebEngineView()
    document.setHtml(html)
    # document.show()
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(output_file.absolute().__str__())
    printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    document.print(printer)
    # document.close()


def remove_key_from_list_of_dicts(input: list, key: str) -> list:
    """
    Removes a key from all dictionaries in a list of dictionaries

    Args:
        input (list): Input list of dicts
        key (str): Name of key to remove.

    Returns:
        list: List of updated dictionaries
    """
    for item in input:
        del item[key]
    return input


# def workbook_2_csv(worksheet: Worksheet, filename: Path):
#     """
#     Export an excel worksheet (workbook is not correct) to csv file.
#
#     Args:
#         worksheet (Worksheet): Incoming worksheet
#         filename (Path): Output csv filepath.
#     """
#     with open(filename, 'w', newline="") as f:
#         c = csv.writer(f)
#         for r in worksheet.rows:
#             c.writerow([cell.value for cell in r])


ctx = get_config(None)


def is_power_user() -> bool:
    """
    Checks if user is in list of power users

    Returns:
        bool: True if yes, False if no.
    """
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


def report_result(func):
    def wrapper(*args, **kwargs):
        logger.debug(f"Arguments: {args}")
        logger.debug(f"Keyword arguments: {kwargs}")
        output = func(*args, **kwargs)
        match output:
            case Report():
                report = output
            case tuple():
                try:
                    report = [item for item in output if isinstance(item, Report)][0]
                except IndexError:
                    report = None
            case _:
                report = None
        logger.debug(f"Got report: {report}")
        try:
            results = report.results
        except AttributeError:
            logger.error("No results available")
            results = []
        for iii, result in enumerate(results):
            logger.debug(f"Result {iii}: {result}")
            try:
                dlg = result.report()
                dlg.exec()
            except Exception as e:
                logger.error(f"Problem reporting due to {e}")
                logger.error(result.msg)
        logger.debug(f"Returning: {output}")
        return output
    return wrapper
