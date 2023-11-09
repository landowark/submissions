'''
Contains miscellaenous functions used by both frontend and backend.
'''
from __future__ import annotations
from pathlib import Path
import re
import numpy as np
import logging
import pandas as pd
from jinja2 import Environment, FileSystemLoader
import yaml
import sys, os, stat, platform, getpass
import logging
from logging import handlers
from pathlib import Path
from sqlalchemy.orm import Session, declarative_base, DeclarativeMeta, Query
from sqlalchemy import create_engine
from pydantic import field_validator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Tuple, Literal, List
import inspect

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

row_map = {1:"A", 2:"B", 3:"C", 4:"D", 5:"E", 6:"F", 7:"G", 8:"H"}

Base: DeclarativeMeta = declarative_base()
metadata = Base.metadata

def check_not_nan(cell_contents) -> bool:
    """
    Check to ensure excel sheet cell contents are not blank.

    Args:
        cell_contents (_type_): The contents of the cell in question.

    Returns:
        bool: True if cell has value, else, false.
    """    
    # check for nan as a string first
    try:
        if "Unnamed:" in cell_contents or "blank" in cell_contents.lower():
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
        logger.debug(f"Check encountered unknown error: {type(e).__name__} - {e}")
        return False

def convert_nans_to_nones(input_str) -> str|None:
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

def check_regex_match(pattern:str, check:str) -> bool:
    try:
        return bool(re.match(fr"{pattern}", check))
    except TypeError:
        return False
    
def massage_common_reagents(reagent_name:str):
    logger.debug(f"Attempting to massage {reagent_name}")
    if reagent_name.endswith("water") or "H2O" in reagent_name.upper():
        reagent_name = "molecular_grade_water"
    reagent_name = reagent_name.replace("µ", "u")
    return reagent_name

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

class Settings(BaseSettings):
    """
    Pydantic model to hold settings

    Raises:
        FileNotFoundError: _description_

    """    
    directory_path: Path
    database_path: Path|str|None = None
    backup_path: Path
    super_users: list|None = None
    power_users: list|None = None
    rerun_regex: str
    submission_types: dict|None = None
    database_session: Session|None = None
    package: Any|None = None

    model_config = SettingsConfigDict(env_file_encoding='utf-8')

    @field_validator('backup_path')
    @classmethod
    def set_backup_path(cls, value):
        if isinstance(value, str):
            value = Path(value)
        metadata.backup_path = value
        return value

    @field_validator('directory_path', mode="before")
    @classmethod
    def ensure_directory_exists(cls, value):
        if isinstance(value, str):
            value = Path(value)
        if not value.exists():
            value = Path().home()    
        metadata.directory_path = value
        return value
        
    @field_validator('database_path', mode="before")
    @classmethod
    def ensure_database_exists(cls, value):
        if value == ":memory:":
            return value
        if isinstance(value, str):
            value = Path(value)
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
            logger.debug(f"Using {database_path} for database file.")
            engine = create_engine(f"sqlite:///{database_path}")#, echo=True, future=True)
            session = Session(engine)
            metadata.session = session
            
            return session

    @field_validator('package', mode="before")
    @classmethod
    def import_package(cls, value):
        import __init__ as package
        if value == None:
            return package

def get_config(settings_path: Path|str|None=None) -> Settings:
    """
    Get configuration settings from path or default if blank.

    Args:
        settings_path (Path | str | None, optional): Path to config.yml Defaults to None.

    Returns:
        Settings: Pydantic settings object
    """    
    logger.debug(f"Creating settings...")
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
            with open(settings_path, "r") as dset:
                default_settings = yaml.load(dset, Loader=yaml.Loader)
            # Tell program we need to copy the config.yml to the user directory
            # copy_settings_trigger = True
            # copy settings to config directory
            return Settings(**copy_settings(settings_path=CONFIGDIR.joinpath("config.yml"), settings=default_settings))
    else:
        # check if user defined path is directory
        if settings_path.is_dir():
            settings_path = settings_path.joinpath("config.yml")
        # check if user defined path is file
        elif settings_path.is_file():
            settings_path = settings_path
        else:
            logger.error("No config.yml file found. Writing to directory.")
            with open(settings_path, "r") as dset:
                default_settings = yaml.load(dset, Loader=yaml.Loader)
            return Settings(**copy_settings(settings_path=settings_path, settings=default_settings))
    logger.debug(f"Using {settings_path} for config file.")
    with open(settings_path, "r") as stream:
        settings = yaml.load(stream, Loader=yaml.Loader)
    return Settings(**settings)

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
    if not settings_path.exists():
        with open(settings_path, 'w') as f:
            yaml.dump(settings, f)
    return settings

def jinja_template_loading():
    """
    Returns jinja2 template environment.

    Returns:
        _type_: _description_
    """    
    # determine if pyinstaller launcher is being used
    if check_if_app():
        loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
    else:
        loader_path = Path(__file__).parent.joinpath('templates').absolute()#.__str__()
    # jinja template loading
    loader = FileSystemLoader(loader_path)
    env = Environment(loader=loader)
    env.globals['STATIC_PREFIX'] = loader_path.joinpath("static", "css")
    return env

def check_authorization(func):
    def wrapper(*args, **kwargs):
        logger.debug(f"Checking authorization")
        if getpass.getuser() in kwargs['ctx'].power_users:
            return func(*args, **kwargs)
        else:
            logger.error(f"User {getpass.getuser()} is not authorized for this function.")
            return dict(code=1, message="This user does not have permission for this function.", status="warning")
    return wrapper

def check_if_app(ctx:Settings=None) -> bool:
    """
    Checks if the program is running from pyinstaller compiled

    Args:
        ctx (dict, optional): Settings passed down from gui. Defaults to None.

    Returns:
        bool: True if running from pyinstaller. Else False.
    """    
    if getattr(sys, 'frozen', False):
        return True
    else:
        return False
    
def convert_well_to_row_column(input_str:str) -> Tuple[int, int]:
    """
    Converts typical alphanumeric (i.e. "A2") to row, column

    Args:
        input_str (str): Input string. Ex. "A2"

    Returns:
        Tuple[int, int]: row, column
    """    
    row_keys = dict(A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)
    try:
        row = int(row_keys[input_str[0].upper()])
        column = int(input_str[1:]) 
    except IndexError:
        return None, None
    return row, column

def query_return(query:Query, limit:int=0):
    """
    Execute sqlalchemy query.

    Args:
        query (Query): Query object
        limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

    Returns:
        _type_: Query result.
    """    
    with query.session.no_autoflush:
        match limit:
            case 0:
                return query.all()
            case 1:
                return query.first()
            case _:
                return query.limit(limit).all()

def setup_lookup(func):
    def wrapper(*args, **kwargs):
        for k, v in locals().items():
            if k == "kwargs":
                continue
            if isinstance(v, dict):
                raise ValueError("Cannot use dictionary in query. Make sure you parse it first.")
        return func(*args, **kwargs)
    return wrapper

class Result(BaseModel):

    owner: str = Field(default="", validate_default=True)
    code: int = Field(default=0)
    msg: str
    status: Literal["NoIcon", "Question", "Information", "Warning", "Critical"] = Field(default="NoIcon")

    def __repr__(self) -> str:
        return f"Result({self.owner})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = inspect.stack()[1].function

    def report(self):
        from frontend.custom_widgets.misc import AlertPop
        return AlertPop(message=self.msg, status=self.status, owner=self.owner)
    
class Report(BaseModel):

    results: List[Result] = Field(default=[])

    # def __init__(self, *args, **kwargs):
    #     if 'msg' in kwargs.keys():
    #         res = Result(msg=kwargs['msg'])
    #         for k,v in kwargs.items():
    #             if k in ['code', 'status']:
    #                 setattr(res, k, v)
    #         self.results.append(res)


    def __repr__(self):
        return f"Report(result_count:{len(self.results)})"

    def add_result(self, result:Result|Report|None):
        match result:
            case Result():
                logger.debug(f"Adding {result} to results.")
                try:
                    self.results.append(result)
                except AttributeError:
                    logger.error(f"Problem adding result.")
            case Report():
                
                for res in result.results:
                    logger.debug(f"Adding {res} from to results.")
                    self.results.append(res)
            case _:
                pass


