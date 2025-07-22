'''
Contains miscellaenous functions used by both frontend and backend.
'''
from __future__ import annotations
import builtins, importlib, time, logging, re, yaml, sys, os, stat, platform, getpass, json, numpy as np, pandas as pd
import itertools
from datetime import date, datetime, timedelta
from json import JSONDecodeError
from threading import Thread
from inspect import getmembers, isfunction, stack
from dateutil.easter import easter
from dateutil.parser import parse
from jinja2 import Environment, FileSystemLoader
from logging import handlers, Logger
from pathlib import Path
from sqlalchemy.orm import Session, InstrumentedAttribute
from sqlalchemy import create_engine, text, MetaData
from pydantic import field_validator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, YamlConfigSettingsSource
from typing import Any, Tuple, Literal, List, Generator
from sqlalchemy.orm.relationships import _RelationshipDeclared
from __init__ import project_path
from configparser import ConfigParser
from tkinter import Tk  # NOTE: This is for choosing database path before app is created.
from tkinter.filedialog import askdirectory
from sqlalchemy.exc import IntegrityError as sqlalcIntegrityError
from pytz import timezone as tz
from functools import wraps

timezone = tz("America/Winnipeg")

logger = logging.getLogger(f"submissions.{__name__}")

logger.info(f"Package dir: {project_path}")

if platform.system() == "Windows":
    os_config_dir = "AppData/local"
    logger.info(f"Got platform Windows, config_dir: {os_config_dir}")
else:
    os_config_dir = ".config"
    logger.info(f"Got platform {platform.system()}, config_dir: {os_config_dir}")

main_aux_dir = Path.home().joinpath(f"{os_config_dir}/procedure")

CONFIGDIR = main_aux_dir.joinpath("config")
LOGDIR = main_aux_dir.joinpath("logs")

row_map = {1: "A", 2: "B", 3: "C", 4: "D", 5: "E", 6: "F", 7: "G", 8: "H"}
row_keys = {v: k for k, v in row_map.items()}

# NOTE: Sets background for uneditable comboboxes and date edits.
main_form_style = '''
                        QComboBox:!editable, QDateEdit {
                            background-color:light gray;
                        }
                '''

page_size = 250


def divide_chunks(input_list: list, chunk_count: int) -> Generator[Any, Any, None]:
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
    exclude = ['unnamed:', 'blank', 'void', 'nat', 'nan', "", "none"]
    try:
        if cell_contents.lower() in exclude:
            cell_contents = np.nan
    except (TypeError, AttributeError):
        pass
    try:
        if np.isnat(cell_contents):
            cell_contents = np.nan
    except TypeError as e:
        pass
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


def convert_nans_to_nones(input_str: str) -> str | None:
    """
    Get rid of various "nan", "NAN", "NaN", etc/

    Args:
        input_str (str): input string

    Returns:
        str: _description_
    """
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


def timer(func):
    """
    Performs timing of wrapped function

    Args:
        func (__function__): incoming function

    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        value = func(*args, **kwargs)
        end_time = time.perf_counter()
        run_time = end_time - start_time
        print(f"Finished {func.__name__}() in {run_time:.4f} secs")
        return value

    return wrapper


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


class CustomLogger(Logger):

    def __init__(self, name: str = "procedure", level=logging.DEBUG):
        super().__init__(name, level)
        self.extra_info = None
        ch = logging.StreamHandler(stream=sys.stdout)
        ch.name = "Stream"
        ch.setLevel(self.level)
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

    logger = logging.getLogger("procedure")
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


def render_details_template(template_name:str, css_in:List[str]|str=[], js_in:List[str]|str=[], **kwargs) -> str:
    if isinstance(css_in, str):
        css_in = [css_in]
    css_in = ["styles"] + css_in
    css_in = [project_path.joinpath("src", "submissions", "templates", "css", f"{c}.css") for c in css_in]
    if isinstance(js_in, str):
        js_in = [js_in]
    js_in = ["details"] + js_in
    js_in = [project_path.joinpath("src", "submissions", "templates", "js", f"{j}.js") for j in js_in]
    env = jinja_template_loading()
    template = env.get_template(f"{template_name}.html")
    # template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
    css_out = []
    for css in css_in:
        with open(css, "r") as f:
            css_out.append(f.read())
    js_out = []
    for js in js_in:
        with open(js, "r") as f:
            js_out.append(f.read())
    logger.debug(f"Kwargs: {kwargs}")
    return template.render(css=css_out, js=js_out, **kwargs)



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

# Copy a sheet with style, format, layout, ect. from one Excel file to another Excel file
# Please add the ..path\\+\\file..  and  ..sheet_name.. according to your desire.
import openpyxl
from copy import copy


def copy_xl_sheet(source_sheet, target_sheet):
    copy_cells(source_sheet, target_sheet)  # copy all the cel values and styles
    copy_sheet_attributes(source_sheet, target_sheet)


def copy_sheet_attributes(source_sheet, target_sheet):
    if isinstance(source_sheet, openpyxl.worksheet._read_only.ReadOnlyWorksheet):
        return
    target_sheet.sheet_format = copy(source_sheet.sheet_format)
    target_sheet.sheet_properties = copy(source_sheet.sheet_properties)
    target_sheet.merged_cells = copy(source_sheet.merged_cells)
    target_sheet.page_margins = copy(source_sheet.page_margins)
    target_sheet.freeze_panes = copy(source_sheet.freeze_panes)

    # set row dimensions
    # So you cannot copy the row_dimensions attribute. Does not work (because of meta data in the attribute I think). So we copy every row's row_dimensions. That seems to work.
    for rn in range(len(source_sheet.row_dimensions)):
        target_sheet.row_dimensions[rn] = copy(source_sheet.row_dimensions[rn])

    if source_sheet.sheet_format.defaultColWidth is None:
        print('Unable to copy default column wide')
    else:
        target_sheet.sheet_format.defaultColWidth = copy(source_sheet.sheet_format.defaultColWidth)

    # set specific column width and hidden property
    # we cannot copy the entire column_dimensions attribute so we copy selected attributes
    for key, value in source_sheet.column_dimensions.items():
        target_sheet.column_dimensions[key].min = copy(source_sheet.column_dimensions[key].min)   # Excel actually groups multiple columns under 1 key. Use the min max attribute to also group the columns in the targetSheet
        target_sheet.column_dimensions[key].max = copy(source_sheet.column_dimensions[key].max)  # https://stackoverflow.com/questions/36417278/openpyxl-can-not-read-consecutive-hidden-columns discussed the issue. Note that this is also the case for the width, not onl;y the hidden property
        target_sheet.column_dimensions[key].width = copy(source_sheet.column_dimensions[key].width) # set width for every column
        target_sheet.column_dimensions[key].hidden = copy(source_sheet.column_dimensions[key].hidden)


def copy_cells(source_sheet, target_sheet):
    for r, row in enumerate(source_sheet.iter_rows()):
        for c, cell in enumerate(row):
            source_cell = cell
            if isinstance(source_cell, openpyxl.cell.read_only.EmptyCell):
                continue
            target_cell = target_sheet.cell(column=c+1, row=r+1)

            target_cell._value = source_cell._value
            target_cell.data_type = source_cell.data_type

            if source_cell.has_style:
                target_cell.font = copy(source_cell.font)
                target_cell.border = copy(source_cell.border)
                target_cell.fill = copy(source_cell.fill)
                target_cell.number_format = copy(source_cell.number_format)
                target_cell.protection = copy(source_cell.protection)
                target_cell.alignment = copy(source_cell.alignment)

            if not isinstance(source_cell, openpyxl.cell.ReadOnlyCell) and source_cell.hyperlink:
                target_cell._hyperlink = copy(source_cell.hyperlink)

            if not isinstance(source_cell, openpyxl.cell.ReadOnlyCell) and source_cell.comment:
                target_cell.comment = copy(source_cell.comment)


def list_str_comparator(input_str:str, listy: List[str], mode: Literal["starts_with", "contains"]) -> bool:
    match mode:
        case "starts_with":
            if any([input_str.startswith(item) for item in listy]):
                return True
            else:
                return False
        case "contains":
            if any([item in input_str for item in listy]):
                return True
            else:
                return False


def setup_lookup(func):
    """
    Checks to make sure all args are allowed

    Args:
        func (_type_): wrapped function
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        sanitized_kwargs = {}
        for k, v in locals()['kwargs'].items():
            if isinstance(v, dict):
                try:
                    sanitized_kwargs[k] = v['value']
                except KeyError:

                    raise ValueError(f"Could not sanitize dictionary {v} in query. Make sure you parse it first.")
            elif v is not None:
                sanitized_kwargs[k] = v
        return func(*args, **sanitized_kwargs)

    return wrapper


def check_object_in_manager(manager: list, object_name: object) -> Tuple[Any, bool]:
    if manager is None:
        return None, False
    # logger.debug(f"Manager: {manager}, aliases: {manager.aliases}, Key: {object_name}")
    if object_name in manager.aliases:
        return manager, True
    relationships = [getattr(manager.__class__, item) for item in dir(manager.__class__)
                     if isinstance(getattr(manager.__class__, item), InstrumentedAttribute)]
    relationships = [item for item in relationships if isinstance(item.property, _RelationshipDeclared)]
    for relationship in relationships:
        if relationship.key == object_name and "association" not in relationship.key:
            logger.debug(f"Checking {relationship.key}")
            try:
                rel_obj = getattr(manager, relationship.key)
                if rel_obj is not None:
                    logger.debug(f"Returning {rel_obj}")
                    return rel_obj, False
            except AttributeError:
                pass
        if "association" in relationship.key:
            try:
                logger.debug(f"Checking association {relationship.key}")
                rel_obj = next((getattr(item, object_name) for item in getattr(manager, relationship.key)
                                if getattr(item, object_name) is not None), None)
                if rel_obj is not None:
                    logger.debug(f"Returning {rel_obj}")
                    return rel_obj, False
            except AttributeError:
                pass
    return None, None


def get_application_from_parent(widget):
    try:
        return widget.app
    except AttributeError:
        logger.info("Using recursion to get application object.")
    from frontend.widgets.app import App
    while not isinstance(widget, App):
        try:
            widget = widget.parent()
        except AttributeError:
            return widget
    return widget


class Result(BaseModel, arbitrary_types_allowed=True):
    owner: str = Field(default="", validate_default=True)
    code: int = Field(default=0)
    msg: str | Exception
    status: Literal["NoIcon", "Question", "Information", "Warning", "Critical"] = Field(default="NoIcon")

    @field_validator('status', mode='before')
    @classmethod
    def to_title(cls, value: str):
        if value.lower().replace(" ", "") == "noicon":
            return "NoIcon"
        else:
            return value.title()

    @field_validator('msg')
    @classmethod
    def set_message(cls, value):
        if isinstance(value, Exception):
            value = cls.parse_exception_to_message(value=value)
        return value

    @classmethod
    def parse_exception_to_message(cls, value: Exception) -> str:
        """
        Converts an except to a human-readable error message for display.

        Args:
            value (Exception): Input exception

        Returns:
            str: Output message for display

        """
        match value:
            case sqlalcIntegrityError():
                origin = value.orig.__str__().lower()
                logger.error(f"Exception origin: {origin}")
                if "unique constraint failed:" in origin:
                    field = " ".join(origin.split(".")[1:]).replace("_", " ").upper()
                    value = f"{field} doesn't have a unique value.\nIt must be changed."
                else:
                    value = f"Got unknown integrity error: {value}"
            case _:
                value = f"Got generic error: {value}"
        return value

    def __repr__(self) -> str:
        return f"Result({self.owner})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = stack()[1].function

    def report(self):
        from frontend.widgets.pop_ups import AlertPop
        return AlertPop(message=self.msg, status=self.status, owner=self.owner)


class Report(BaseModel):
    results: List[Result] = Field(default=[])

    def __repr__(self):
        return f"<Report(result_count:{len(self.results)})>"

    def __str__(self):
        return f"<Report(result_count:{len(self.results)})>"

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
                for res in result.results:
                    logger.info(f"Adding {res} from {result} to results.")
                    self.results.append(res)
            case _:
                logger.error(f"Unknown variable type: {type(result)} for <Result> entry into <Report>")


def rreplace(s: str, old: str, new: str) -> str:
    """
    Removes rightmost occurrence of a substring

    Args:
        s (str): input string
        old (str): original substring
        new (str): new substring

    Returns:
        str: updated string
    """
    return (s[::-1].replace(old[::-1], new[::-1], 1))[::-1]


def list_sort_dict(input_dict: dict, sort_list: list) -> dict:
    sort_list = reversed(sort_list)
    for item in sort_list:
        try:
            input_dict = {item: input_dict.pop(item), **input_dict}
        except KeyError:
            continue
    return input_dict


def remove_key_from_list_of_dicts(input_list: list, key: str) -> list:
    """
    Removes a key from all dictionaries in a list of dictionaries

    Args:
        input_list (list): Input list of dicts
        key (str): Name of key to remove.

    Returns:
        list: List of updated dictionaries
    """
    for item in input_list:
        try:
            del item[key]
        except KeyError:
            continue
    return input_list


def yaml_regex_creator(loader, node):
    # Note: Add to import from json, NOT export yaml in app.
    nodes = loader.construct_sequence(node)
    name = nodes[0].replace(" ", "_")
    abbr = nodes[1]
    return f"(?P<{name}>RSL(?:-|_)?{abbr}(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)?\d?([^_0123456789\sA-QS-Z]|$)?R?\d?)?)"


def super_splitter(ins_str: str, substring: str, idx: int) -> str:
    """
    Splits string on substring at index

    Args:
        ins_str (str): input string
        substring (str): substring to split on
        idx (int): the occurrence of the substring to return

    Returns:

    """
    try:
        return ins_str.split(substring)[idx]
    except IndexError:
        logger.error(f"Index of split {idx} not found.")
        return ins_str


def is_developer() -> bool:
    """
    Checks if user is in list of super users

    Returns:
        bool: True if yes, False if no.
    """
    try:
        check = getpass.getuser() in ctx.super_users
    except:
        check = False
    return check


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
        func (function): Function to be used.
    """

    @wraps(func)
    @report_result
    def wrapper(*args, **kwargs):
        logger.info(f"Checking authorization")
        error_msg = f"User {getpass.getuser()} is not authorized for this function."
        auth_func = is_power_user
        if auth_func():
            return func(*args, **kwargs)
        else:
            logger.error(error_msg)
            report = Report()
            report.add_result(
                Result(owner=func.__str__(), code=1, msg=error_msg, status="warning"))
            return report, kwargs

    return wrapper


def under_development(func):
    """
    Decorator to check if user is authorized to access function

    Args:
        func (function): Function to be used.
    """

    @wraps(func)
    @report_result
    def wrapper(*args, **kwargs):
        logger.warning(f"This feature is under development")
        if is_developer():
            return func(*args, **kwargs)
        else:
            error_msg = f"User {getpass.getuser()} is not authorized for this function."
            logger.error(error_msg)
            report = Report()
            report.add_result(
                Result(owner=func.__str__(), code=1, msg=error_msg,
                       status="warning"))
            return report

    return wrapper


def report_result(func):
    """
    Decorator to display any reports returned from a function.

    Args:
        func (function): Function being decorated

    Returns:
        __type__: Output from decorated function

    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        # logger.info(f"Report result being called by {func.__name__}")
        output = func(*args, **kwargs)
        match output:
            case Report():
                report = output
            case tuple():
                report = next((item for item in output if isinstance(item, Report)), None)
            case _:
                report = Report()
        try:
            results = report.results
        except AttributeError:
            logger.error("No results available")
            results = []
        for iii, result in enumerate(results):
            try:
                dlg = result.report()
                if "testing" in args:
                    return report
                else:
                    dlg.exec()
            except Exception as e:
                logger.error(f"Problem reporting due to {e}")
                logger.error(result.msg)
        if output:
            if is_list_etc(output):
                true_output = tuple(item for item in output if not isinstance(item, Report))
                if len(true_output) == 1:
                    true_output = true_output[0]
            else:
                if isinstance(output, Report):
                    true_output = None
                else:
                    true_output = output
        else:
            true_output = None
        return true_output

    return wrapper


def is_list_etc(object):
    match object:
        case str():  #: I don't want to iterate strings, so hardcoding that
            return False
        case Report():
            return False
        case _:
            try:
                check = iter(object)
            except TypeError:
                check = False
            return check


def create_holidays_for_year(year: int | None = None) -> List[date]:
    def find_nth_monday(year, month, occurence: int | None = None, day: int | None = None):
        if not occurence:
            occurence = 1
        if not day:
            day = occurence * 7
        max_days = (date(2012, month + 1, 1) - date(2012, month, 1)).days
        if day > max_days:
            day = max_days
        try:
            d = datetime(year, int(month), day=day)
        except ValueError:
            return
        offset = -d.weekday()  # weekday == 0 means Monday
        output = d + timedelta(offset)
        return output.date()

    if not year:
        year = date.today().year
    # NOTE: Includes New Year's day for next year.
    holidays = [date(year, 1, 1), date(year, 7, 1), date(year, 9, 30),
                date(year, 11, 11), date(year, 12, 25), date(year, 12, 26),
                date(year + 1, 1, 1)]
    # NOTE: Labour Day
    holidays.append(find_nth_monday(year, 9))
    # NOTE: Thanksgiving
    holidays.append(find_nth_monday(year, 10, occurence=2))
    # NOTE: Victoria Day
    holidays.append(find_nth_monday(year, 5, day=25))
    # NOTE: Easter, etc
    holidays.append(easter(year) - timedelta(days=2))
    holidays.append(easter(year) + timedelta(days=1))
    return sorted(holidays)


def check_dictionary_inclusion_equality(listo: List[dict] | dict, dicto: dict) -> bool:
    """
    Determines if a dictionary is in a list of dictionaries (possible ordering issue with just using dict in list)

    Args:
        listo (List[dict): List of dictionaries to compare to.
        dicto (dict): Dictionary to compare.

    Returns:
        bool: True if dicto is equal to any dictionary in the list.
    """
    # logger.debug(f"Comparing: {listo} and {dicto}")
    if isinstance(dicto, list) and isinstance(listo, list):
        return listo == dicto
    elif isinstance(dicto, dict) and isinstance(listo, dict):
        return listo == dicto
    elif isinstance(dicto, dict) and isinstance(listo, list):
        return any([dicto == d for d in listo])
    else:
        raise TypeError(f"Unsupported variable: {type(listo)}")


def flatten_list(input_list: list):
    return list(itertools.chain.from_iterable(input_list))


def create_plate_grid(rows: int, columns: int):
    matrix = np.array([[0 for yyy in range(1, columns + 1)] for xxx in range(1, rows + 1)])
    return {iii: (item[0][1]+1, item[0][0]+1) for iii, item in enumerate(np.ndenumerate(matrix), start=1)}


class classproperty(property):
    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


# NOTE: Monkey patching... hooray!
builtins.classproperty = classproperty


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
    logging_enabled: bool = Field(default=False)

    @classproperty
    def main_aux_dir(cls):
        if platform.system() == "Windows":
            os_config_dir = "AppData/local"
            # logger.info(f"Got platform Windows, config_dir: {os_config_dir}")
        else:
            os_config_dir = ".config"
            # logger.info(f"Got platform {platform.system()}, config_dir: {os_config_dir}")
        return Path.home().joinpath(f"{os_config_dir}/procedure")

    @classproperty
    def configdir(cls):
        return cls.main_aux_dir.joinpath("config")

    @classproperty
    def logdir(cls):
        return cls.main_aux_dir.joinpath("logs")

    def __new__(cls, *args, **kwargs):
        if "settings_path" in kwargs.keys():
            settings_path = kwargs['settings_path']
            if isinstance(settings_path, str):
                settings_path = Path(settings_path)
        else:
            settings_path = None
        if settings_path is None:
            # NOTE: Check user .config/procedure directory
            if cls.configdir.joinpath("config.yml").exists():
                settings_path = cls.configdir.joinpath("config.yml")
            # NOTE: Check user .procedure directory
            elif Path.home().joinpath(".procedure", "config.yml").exists():
                settings_path = Path.home().joinpath(".procedure", "config.yml")
            # NOTE: finally look in the local config
            else:
                if check_if_app():
                    settings_path = Path(sys._MEIPASS).joinpath("files", "config.yml")
                else:
                    settings_path = project_path.joinpath('src', 'config.yml')
        else:
            # NOTE: check if user defined path is directory
            if settings_path.is_dir():
                settings_path = settings_path.joinpath("config.yml")
            # NOTE: check if user defined path is file
            elif settings_path.is_file():
                settings_path = settings_path
            else:
                raise FileNotFoundError(f"{settings_path} not found.")
        # NOTE: how to load default settings into this?
        print(f"Loading settings from {settings_path}")
        cls.model_config = SettingsConfigDict(yaml_file=settings_path, yaml_file_encoding='utf-8', extra="allow")
        return super().__new__(cls)

    @classmethod
    def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            YamlConfigSettingsSource(settings_cls),
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    @field_validator('database_schema', mode="before")
    @classmethod
    def set_schema(cls, value):
        if value is None:
            if check_if_app():
                alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
            else:
                alembic_path = project_path.joinpath("alembic.ini")
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
                    if check_if_app():
                        alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
                    else:
                        alembic_path = project_path.joinpath("alembic.ini")
                    value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='path').parent
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
        if not check:
            value.mkdir(exist_ok=True)
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
            value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='user')
        return value

    @field_validator("database_password", mode='before')
    @classmethod
    def get_pass(cls, value):
        if value is None:
            if check_if_app():
                alembic_path = Path(sys._MEIPASS).joinpath("files", "alembic.ini")
            else:
                alembic_path = project_path.joinpath("alembic.ini")
            value = cls.get_alembic_db_path(alembic_path=alembic_path, mode='pass')
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
                    template = jinja_template_loading().from_string(
                        "{{ values['database_schema'] }}://{{ value }}/{{ db_name }}")
                case "mssql+pyodbc":
                    value = values.data['database_path']
                    db_name = values.data['database_name']
                    template = jinja_template_loading().from_string(
                        "{{ values['database_schema'] }}://{{ value }}/{{ db_name }}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes&Trusted_Connection=yes"
                    )
                case _:
                    tmp = jinja_template_loading().from_string(
                        "{% if values['database_user'] %}{{ values['database_user'] }}{% if values['database_password'] %}:{{ values['database_password'] }}{% endif %}{% endif %}@{{ values['database_path'] }}")
                    value = tmp.render(values=values.data)
                    db_name = values.data['database_name']
            database_path = template.render(values=values.data, value=value, db_name=db_name)
            print(f"Using {database_path} for database path")
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
        try:
            del kwargs['settings_path']
        except KeyError:
            pass
        self.set_from_db()
        self.set_scripts()
        self.save()

    def set_from_db(self):
        if 'pytest' in sys.modules:
            output = dict(power_users=['lwark', 'styson', 'ruwang'],
                          startup_scripts=dict(hello=None),
                          teardown_scripts=dict(goodbye=None)
                          )
        else:
            session = self.database_session
            metadata = MetaData()
            try:
                metadata.reflect(bind=session.get_bind())
            except AttributeError as e:
                print(f"Error getting tables: {e}")
                return
            if "_configitem" not in metadata.tables.keys():
                print(f"Couldn't find _configitems in {metadata.tables.keys()}.")
                return
            config_items = session.execute(text("SELECT * FROM _configitem")).all()
            output = {}
            for item in config_items:
                try:
                    output[item[1]] = json.loads(item[2])
                except (JSONDecodeError, TypeError):
                    output[item[1]] = item[2]
        for k, v in output.items():
            if not hasattr(self, k):
                self.__setattr__(k, v)

    def set_scripts(self):
        """
        Imports all functions from "scripts" folder, adding them to ctx scripts
        """
        if check_if_app():
            p = Path(sys._MEIPASS).joinpath("files", "scripts")
        else:
            p = Path(__file__).parents[2].joinpath("scripts").absolute()
        if p.__str__() not in sys.path:
            sys.path.append(p.__str__())
        # NOTE: Get all .py files that don't have __ in them.
        modules = p.glob("[!__]*.py")
        for module in modules:
            mod = importlib.import_module(module.stem)
            for function in getmembers(mod, isfunction):
                name = function[0]
                func = function[1]
                # NOTE: assign function based on its name being in config: startup/teardown
                # NOTE: scripts must be registered using {name: Null} in the database
                try:
                    if name in self.startup_scripts.keys():
                        self.startup_scripts[name] = func
                except AttributeError:
                    pass
                try:
                    if name in self.teardown_scripts.keys():
                        self.teardown_scripts[name] = func
                except AttributeError:
                    pass

    @timer
    def run_startup(self):
        """
        Runs startup scripts.
        """
        try:
            for script in self.startup_scripts.values():
                try:
                    logger.info(f"Running startup script: {script.__name__}")
                    thread = Thread(target=script, args=(ctx,))
                    thread.start()
                except AttributeError:
                    logger.error(f"Couldn't run startup script: {script}")
        except AttributeError:
            pass

    @timer
    def run_teardown(self):
        """
        Runs teardown scripts.
        """
        try:
            for script in self.teardown_scripts.values():
                try:
                    logger.info(f"Running teardown script: {script.__name__}")
                    thread = Thread(target=script, args=(ctx,))
                    thread.start()
                except AttributeError:
                    logger.error(f"Couldn't run teardown script: {script}")
        except AttributeError:
            pass

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
                    return None
            case "pass":
                url = re.sub(r"^.*//", "", url)
                try:
                    return url[:url.index("@")].split(":")[1]
                except (IndexError, ValueError) as e:
                    return None

    def save(self):
        if not self.configdir.joinpath("config.yml").exists():
            try:
                self.configdir.mkdir(parents=True)
            except FileExistsError:
                logger.warning(f"Config directory {self.configdir} already exists.")
            try:
                self.logdir.mkdir(parents=True)
            except FileExistsError:
                logger.warning(f"Logging directory {self.configdir} already exists.")
            dicto = {}
            for k, v in self.__dict__.items():
                if k in ['package', 'database_session', 'proceduretype']:
                    continue
                match v:
                    case Path():
                        if v.is_dir():
                            v = v.absolute().__str__()
                        elif v.is_file():
                            v = v.parent.absolute().__str__()
                        else:
                            v = v.__str__()
                    case _:
                        pass
                dicto[k] = v
            with open(self.configdir.joinpath("config.yml"), 'w') as f:
                yaml.dump(dicto, f)


ctx = Settings()
