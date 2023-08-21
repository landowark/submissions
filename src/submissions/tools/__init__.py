'''
Contains miscellaenous functions used by both frontend and backend.
'''
from pathlib import Path
import re
import numpy as np
import logging
import pandas as pd
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import yaml
import sys, os, stat, platform, getpass
import logging
from logging import handlers
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any, Tuple

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
    if cell_contents == 'nan':
        cell_contents = np.nan
    if cell_contents == None:
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
    if not check_not_nan(input_str):
        return None
    return input_str

def check_is_power_user(ctx:dict) -> bool:
    """
    Check to ensure current user is in power users list.

    Args:
        ctx (dict): settings passed down from gui.

    Returns:
        bool: True if user is in power users, else false.
    """    
    try:
        check = getpass.getuser() in ctx.power_users
    except KeyError as e:
        check = False
    except Exception as e:
        logger.debug(f"Check encountered unknown error: {type(e).__name__} - {e}")
        check = False
    return check

def create_reagent_list(in_dict:dict) -> list[str]:
    """
    Makes list of reagent types without "lot\_" prefix for each key in a dictionary

    Args:
        in_dict (dict): input dictionary of reagents

    Returns:
        list[str]: list of reagent types with "lot\_" prefix removed.
    """    
    return [item.strip("lot_") for item in in_dict.keys()]

def check_if_app(ctx:dict=None) -> bool:
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
    
def retrieve_rsl_number(in_str:str) -> Tuple[str, str]:
    """
    Uses regex to retrieve the plate number and submission type from an input string
    DEPRECIATED. REPLACED BY RSLNamer.parsed_name
    
    Args:
        in_str (str): string to be parsed

    Returns:
        Tuple[str, str]: tuple of (output rsl number, submission_type)
    """    
    in_str = in_str.split("\\")[-1]
    logger.debug(f"Attempting match of {in_str}")
    regex = re.compile(r"""
        (?P<wastewater>RSL-?WW(?:-|_)20\d{6}(?:(?:_|-)\d(?!\d))?)|(?P<bacterial_culture>RSL-\d{2}-\d{4})
        """, re.VERBOSE)
    m = regex.search(in_str)
    parsed = m.group().replace("_", "-")
    return (parsed, m.lastgroup)

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
        
class RSLNamer(object):
    """
    Object that will enforce proper formatting on RSL plate names.
    """
    def __init__(self, ctx, instr:str, sub_type:str|None=None):
        self.ctx = ctx
        self.submission_type = sub_type
        self.retrieve_rsl_number(in_str=instr)
        if self.submission_type != None:
            parser = getattr(self, f"enforce_{self.submission_type.lower()}")
            parser()
            self.parsed_name = self.parsed_name.replace("_", "-")
        
    def retrieve_rsl_number(self, in_str:str|Path):
        """
        Uses regex to retrieve the plate number and submission type from an input string

        Args:
            in_str (str): string to be parsed
        """    
        if not isinstance(in_str, Path):
            in_str = Path(in_str)
        self.out_str = in_str.stem
        logger.debug(f"Attempting match of {self.out_str}")
        logger.debug(f"The initial plate name is: {self.out_str}")
        regex = re.compile(r"""
                # (?P<wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(?:_|-)\d?((?!\d)|R)?\d(?!\d))?)|
                (?P<wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?(\D|$)R?\d?)?)|
                (?P<bacterial_culture>RSL-?\d{2}-?\d{4})|
                (?P<wastewater_artic>(\d{4}-\d{2}-\d{2}_(?:\d_)?artic)|(RSL(?:-|_)?AR(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?(\D|$)R?\d?)?))
                """, flags = re.IGNORECASE | re.VERBOSE)
        m = regex.search(self.out_str)
        if m != None:
            self.parsed_name = m.group().upper().strip(".")
            logger.debug(f"Got parsed submission name: {self.parsed_name}")
            if self.submission_type == None:
                try:
                    self.submission_type = m.lastgroup
                except AttributeError as e:
                    logger.critical("No RSL plate number found or submission type found!")
                    logger.debug(f"The cause of the above error was: {e}")
                    logger.warning(f"We're going to have to create the submission type from the excel sheet properties...")
                    if in_str.exists():
                        my_xl = pd.ExcelFile(in_str)
                        if my_xl.book.properties.category != None:
                            categories = [item.strip().title() for item in my_xl.book.properties.category.split(";")]
                            self.submission_type = categories[0].replace(" ", "_").lower()
                        else:
                            raise AttributeError(f"File {in_str.__str__()} has no categories.")
                    else:
                        raise FileNotFoundError()
        # else:
        #     raise ValueError(f"No parsed name could be created for {self.out_str}.")

    def enforce_wastewater(self):
        """
        Uses regex to enforce proper formatting of wastewater samples
        """      
        def construct():
            today = datetime.now()
            return f"RSL-WW-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}"
        try:
            self.parsed_name = re.sub(r"PCR(-|_)", "", self.parsed_name)
        except AttributeError as e:
            logger.error(f"Problem using regex: {e}")
            self.parsed_name = construct()
        self.parsed_name = self.parsed_name.replace("RSLWW", "RSL-WW")
        self.parsed_name = re.sub(r"WW(\d{4})", r"WW-\1", self.parsed_name, flags=re.IGNORECASE)
        self.parsed_name = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", self.parsed_name)
        logger.debug(f"Coming out of the preliminary parsing, the plate name is {self.parsed_name}")
        try:
            plate_number = re.search(r"(?:(-|_)\d)(?!\d)", self.parsed_name).group().strip("_").strip("-")
            logger.debug(f"Plate number is: {plate_number}")
        except AttributeError as e:
            plate_number = "1"
        # self.parsed_name = re.sub(r"(\d{8})(-|_\d)?(R\d)?", fr"\1-{plate_number}\3", self.parsed_name)
        self.parsed_name = re.sub(r"(\d{8})(-|_)?\d?(R\d?)?", rf"\1-{plate_number}\3", self.parsed_name)
        logger.debug(f"After addition of plate number the plate name is: {self.parsed_name}")
        try:
            repeat = re.search(r"-\dR(?P<repeat>\d)?", self.parsed_name).groupdict()['repeat']
            if repeat == None:
                repeat = "1"
        except AttributeError as e:
            repeat = ""
        self.parsed_name = re.sub(r"(-\dR)\d?", rf"\1 {repeat}", self.parsed_name).replace(" ", "")
        
    

    def enforce_bacterial_culture(self):
        """
        Uses regex to enforce proper formatting of bacterial culture samples
        """        
        def construct(ctx) -> str:
            """
            DEPRECIATED due to slowness. Search for the largest rsl number and increment by 1

            Returns:
                str: new RSL number
            """        
            logger.debug(f"Attempting to construct RSL number from scratch...")
            # directory = Path(self.ctx['directory_path']).joinpath("Bacteria")
            directory = Path(ctx.directory_path).joinpath("Bacteria")
            year = str(datetime.now().year)[-2:]
            if directory.exists():
                logger.debug(f"Year: {year}")
                relevant_rsls = []
                all_xlsx = [item.stem for item in directory.rglob("*.xlsx") if bool(re.search(r"RSL-\d{2}-\d{4}", item.stem)) and year in item.stem[4:6]]
                logger.debug(f"All rsls: {all_xlsx}")
                for item in all_xlsx:
                    try:
                        relevant_rsls.append(re.match(r"RSL-\d{2}-\d{4}", item).group(0))
                    except Exception as e:
                        logger.error(f"Regex error: {e}")
                        continue
                logger.debug(f"Initial xlsx: {relevant_rsls}")
                max_number = max([int(item[-4:]) for item in relevant_rsls])
                logger.debug(f"The largest sample number is: {max_number}")
                return f"RSL-{year}-{str(max_number+1).zfill(4)}"
            else:
                # raise FileNotFoundError(f"Unable to locate the directory: {directory.__str__()}")
                return f"RSL-{year}-0000"
        try:
            self.parsed_name = re.sub(r"RSL(\d{2})", r"RSL-\1", self.parsed_name, flags=re.IGNORECASE)
        except AttributeError as e:
            self.parsed_name = construct(ctx=self.ctx)
            # year = datetime.now().year
            # self.parsed_name = f"RSL-{str(year)[-2:]}-0000"
        self.parsed_name = re.sub(r"RSL-(\d{2})(\d{4})", r"RSL-\1-\2", self.parsed_name, flags=re.IGNORECASE)

    
    def enforce_wastewater_artic(self):
        """
        Uses regex to enforce proper formatting of wastewater samples
        """     
        def construct():
            today = datetime.now()
            return f"RSL-AR-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}"
        try:
            self.parsed_name = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"RSL-AR-\1\2\3", self.parsed_name, flags=re.IGNORECASE)
        except AttributeError:
            self.parsed_name = construct()
        try:
            plate_number = int(re.search(r"_\d?_", self.parsed_name).group().strip("_"))
        except AttributeError as e:
            plate_number = 1
        self.parsed_name = re.sub(r"(_\d)?_ARTIC", f"-{plate_number}", self.parsed_name)

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
    database_path: Path|None = None
    backup_path: Path
    super_users: list
    power_users: list
    rerun_regex: str
    submission_types: dict|None = None
    database_session: Session|None = None
    package: Any|None = None

    model_config = SettingsConfigDict(env_file_encoding='utf-8')

    @field_validator('directory_path', mode="before")
    @classmethod
    def ensure_directory_exists(cls, value):
        if isinstance(value, str):
            value = Path(value)
        if value.exists():
            return value
        else:
            raise FileNotFoundError(f"Couldn't find settings file {value}")
        
    @field_validator('database_path', mode="before")
    @classmethod
    def ensure_database_exists(cls, value):
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
                # check if user defined path is directory
                if database_path.is_dir():
                    database_path = database_path.joinpath("submissions.db")
                # check if user defined path is a file
                elif database_path.is_file():
                    database_path = database_path
                else:
                    raise FileNotFoundError("No database file found. Exiting program.")
                    # sys.exit()
            logger.debug(f"Using {database_path} for database file.")
            engine = create_engine(f"sqlite:///{database_path}")
            session = Session(engine)
            return session

    @field_validator('package', mode="before")
    @classmethod
    def import_package(cls, value):
        import __init__ as package
        if value == None:
            return package

def get_config(settings_path: Path|str|None=None) -> dict:
    """
    Get configuration settings from path or default if blank.

    Args:
        settings_path (Path | str | None, optional): Path to config.yml Defaults to None.

    Returns:
        Settings: Pydantic settings object
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
            # copy_settings_trigger = True
            # copy settings to config directory
            return Settings(**copy_settings(settings_path=CONFIGDIR.joinpath("config.yml"), settings=settings))
    else:
        # check if user defined path is directory
        if settings_path.is_dir():
            settings_path = settings_path.joinpath("config.yml")
        # check if user defined path is file
        elif settings_path.is_file():
            settings_path = settings_path
        else:
            logger.error("No config.yml file found. Cannot continue.")
            raise FileNotFoundError("No config.yml file found. Cannot continue.")
            return {}
    logger.debug(f"Using {settings_path} for config file.")
    with open(settings_path, "r") as stream:
        # try:
        settings = yaml.load(stream, Loader=yaml.Loader)
        # except yaml.YAMLError as exc:
            # logger.error(f'Error reading yaml file {settings_path}: {exc}'
            # return {}
    # copy settings to config directory
    # if copy_settings_trigger:
    #     settings = copy_settings(settings_path=CONFIGDIR.joinpath("config.yml"), settings=settings)
    return Settings(**settings)

def create_database_session(database_path: Path|str|None=None) -> Session:
    """
    Creates a session to sqlite3 database from path or default database if database_path is blank.
    DEPRECIATED: THIS IS NOW HANDLED BY THE PYDANTIC SETTINGS OBJECT.

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
        loader_path = Path(__file__).parents[1].joinpath('templates').absolute().__str__()

    # jinja template loading
    loader = FileSystemLoader(loader_path)
    env = Environment(loader=loader)
    return env
