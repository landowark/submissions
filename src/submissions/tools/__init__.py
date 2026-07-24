"""
Contains miscellaenous functions used by both frontend and backend.
"""
from __future__ import annotations
from logging import handlers, Logger, Formatter, WARNING, INFO, DEBUG, CRITICAL, ERROR, getLogger, StreamHandler
logger = getLogger(f"submissions.{__name__}")
from html import escape as html_escape
from string import ascii_uppercase
from itertools import product as iterproduct, chain
from pandas import DataFrame, isnull as pdisnull
from numpy import nan as npnan, isnat as npisnat, isnan as npisnan
from getpass import getuser
from platform import system
from stat import S_IWGRP
from os import stat as osstat, chmod, umask
from yaml import dump as ydump
from re import sub as rsub, match as rmatch, I
from time import perf_counter
from importlib import import_module
from collections import OrderedDict
from datetime import date, datetime, timedelta
from json import JSONDecodeError, dumps as jdumps, loads as jloads
from pprint import pformat
from threading import Thread
from inspect import getmembers, isfunction, stack, currentframe
from dateutil.easter import easter
from jinja2 import Environment, FileSystemLoader, Template
from pathlib import Path
from sqlalchemy.orm import scoped_session, sessionmaker
from contextlib import contextmanager
from sqlalchemy import create_engine, text, MetaData
from pydantic import ValidationError, field_validator, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource, YamlConfigSettingsSource
from typing import Any, Tuple, Literal, List, Generator, Callable, TypeVar
from __init__ import project_path
from configparser import ConfigParser
from sqlalchemy.exc import IntegrityError as sqlalcIntegrityError
from pytz import timezone as tz
from functools import wraps
from collections.abc import Iterable
from enum import Enum
import builtins, sys

builtins.pformat = pformat

timezone = tz("America/Winnipeg")

logger.info(f"Package dir: {project_path}")

if system() == "Windows":
    os_config_dir = "AppData/local"
    logger.info(f"Got platform Windows, config_dir: {os_config_dir}")
else:
    os_config_dir = ".config"
    logger.info(f"Got platform {system()}, config_dir: {os_config_dir}")

main_aux_dir = Path.home().joinpath(f"{os_config_dir}/procedure")

CONFIGDIR = main_aux_dir.joinpath("config")
LOGDIR = main_aux_dir.joinpath("logs")

# 1. Generate single letters: ['A', 'B', ..., 'Z']
# single = list(ascii_uppercase)

# # 2. Generate double letters: ['AA', 'AB', ..., 'ZZ']
# double = [''.join(p) for p in iterproduct(ascii_uppercase, repeat=2)]

# 3. Combine and enumerate starting from index 1
# row_map = dict(enumerate(single + double, start=1))
# # 4. Reverse lookup. 
# row_keys = {v: k for k, v in row_map.items()}

# NOTE: Sets background for uneditable comboboxes and date edits.
main_form_style = '''
                        QComboBox:!editable, QDateEdit {
                            background-color:light gray;
                        }
                '''

page_size = 250



F = TypeVar("F", bound=Callable[..., Any])
_MAX = 300  # per-value repr cap

def _safe_repr(obj: Any, max_len: int = _MAX) -> str:
    """repr that never raises and never runs away."""
    try:
        r = repr(obj)
    except Exception as e:                       # a broken __repr__ won't break tracing
        return f"<unreprable {type(obj).__name__}: {e!r}>"
    return r if len(r) <= max_len else f"{r[:max_len]}...(+{len(r) - max_len})"

def trace(func: F | None = None, *, level: int = DEBUG,
          args: bool = True, result: bool = True, timing: bool = True,
          max_len: int = _MAX) -> Any:
    """Log entry args, exit value + elapsed, and exceptions (with traceback)."""
    def decorator(fn: F) -> F:
        log = getLogger(fn.__module__)   # attributes lines to the DEFINING module
        qual = fn.__qualname__

        @wraps(fn)
        def wrapper(*a: Any, **kw: Any) -> Any:
            on = log.isEnabledFor(level)
            if on and args:
                sig = ", ".join([_safe_repr(x, max_len) for x in a] +
                                [f"{k}={_safe_repr(v, max_len)}" for k, v in kw.items()])
                log.log(level, "call %s(%s)", qual, sig)
            elif on:
                log.log(level, "call %s(...)", qual)
            t0 = perf_counter()
            try:
                out = fn(*a, **kw)
            except Exception:
                log.log(level, "raise %s after %.1fms", qual,
                        (perf_counter() - t0) * 1000, exc_info=True)
                raise                            # this is the traceback you're currently losing
            if on:
                ms = (perf_counter() - t0) * 1000
                if result and timing: log.log(level, "ret  %s = %s  [%.1fms]", qual, _safe_repr(out, max_len), ms)
                elif result:          log.log(level, "ret  %s = %s", qual, _safe_repr(out, max_len))
                elif timing:          log.log(level, "ret  %s  [%.1fms]", qual, ms)
            return out
        return wrapper  # type: ignore[return-value]
    return decorator(func) if func is not None else decorator


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


def get_unique_values_in_df_column(df: DataFrame, column_name: str) -> list:
    """
    get all unique values in a dataframe column by name

    Args:
        df (DataFrame): input dataframe
        column_name (str): name of column of interest

    Returns:
        list: sorted list of unique values
    """
    return sorted(df[column_name].unique())


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
            cell_contents = npnan
    except (TypeError, AttributeError):
        pass
    try:
        if npisnat(cell_contents):
            cell_contents = npnan
    except TypeError as e:
        logger.exception(f"Cell contents {cell_contents} not value for isnat")
    try:
        if pdisnull(cell_contents):
            cell_contents = npnan
    except ValueError:
        logger.exception(f"Cell contents {cell_contents} not value for isnull")
    try:
        return not npisnan(cell_contents)
    except TypeError:
        logger.exception(f"Cell contents {cell_contents} not value for isnan")
        return True
    except Exception as e:
        logger.exception(f"Check encountered unknown error: {type(e).__name__} - {e}")
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


def get_first_blank_df_row(df: DataFrame) -> int:
    """
    For some reason I need a whole function for this.

    Args:
        df (DataFrame): Input dataframe.

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
        start_time = perf_counter()
        value = func(*args, **kwargs)
        end_time = perf_counter()
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


def clean_string(text):
    """
    Strips out whitespace and all non-alphanumeric symbols.
    """
    if not isinstance(text, str):
        return text
    # Replaces any non-letter and non-number character with an empty string
    return rsub(r'[^a-zA-Z0-9]', '', text)

# Logging formatters

class GroupWriteRotatingFileHandler(handlers.RotatingFileHandler):

    def doRollover(self):
        """
        Override base class method to make the new log file group writable.
        """
        # NOTE: Rotate the file first.
        handlers.RotatingFileHandler.doRollover(self)
        # NOTE: Add group write to the current permissions.
        currMode = osstat(self.baseFilename).st_mode
        chmod(self.baseFilename, currMode | S_IWGRP)

    def _open(self):
        prevumask = umask(0o002)
        rtv = handlers.RotatingFileHandler._open(self)
        umask(prevumask)
        return rtv


class CustomFormatter(Formatter):
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
        DEBUG: bcolors.ENDC + log_format + bcolors.ENDC,
        INFO: bcolors.ENDC + log_format + bcolors.ENDC,
        WARNING: bcolors.WARNING + log_format + bcolors.ENDC,
        ERROR: bcolors.FAIL + log_format + bcolors.ENDC,
        CRITICAL: bcolors.FAIL + log_format + bcolors.ENDC
    }

    def format(self, record):
        if check_if_app():
            log_fmt = self.log_format
        else:
            log_fmt = self.FORMATS.get(record.levelno)
        formatter = Formatter(log_fmt)
        return formatter.format(record)


class CustomLogger(Logger):

    def __init__(self, name: str = "procedure", level=DEBUG):
        if check_if_app():
           level = INFO 
        super().__init__(name, level)
        self.extra_info = None
        self.propagate = False
        ch = StreamHandler(stream=sys.stdout)
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


class GlobalLoggerProxy:
    def __getattr__(self, item):
        # Find the __name__ of the file currently calling the logger
        frame = currentframe().f_back
        module_name = frame.f_globals.get('__name__', '__main__')
        actual_logger = getLogger(f"submissions.{module_name}")
        return getattr(actual_logger, item)


def jinja_template_loading() -> Environment:
    """
    Returns jinja2 template environment.

    Returns:
        Environment: jinja2 environment object
    """
    # NOTE: allows retrieval of an object's Python type directly within a template
    # Usage: The type of this variable is: {{ my_variable | get_type }}
    def get_type(obj_):
        return type(obj_).__name__
    def get_value(obj_):
        return obj_.get('value') if isinstance(obj_, dict) else obj_
    # NOTE: determine if pyinstaller launcher is being used
    if check_if_app():
        loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
    else:
        loader_path = Path(__file__).parents[1].joinpath('templates').absolute()
    # NOTE: jinja template loading
    loader = FileSystemLoader(loader_path)
    env = Environment(loader=loader)
    env.globals['STATIC_PREFIX'] = loader_path.joinpath("static", "css")
    env.filters['get_type'] = get_type
    # env.filters['extract_value'] = handle_results
    env.filters['sanitize'] = sanitize_object_for_json
    env.filters['handle_key'] = handle_keys
    env.filters['handle_results'] = handle_results
    return env


def render_details_template(template: str | Template, css_in: List[str] | str = [], js_in: List[str] | str = [],
                            **kwargs) -> str:
    if isinstance(css_in, str):
        css_in = [css_in]
    env = jinja_template_loading()
    html_folder = Path(env.loader.__getattribute__("searchpath")[0])
    css_in = ["styles"] + css_in
    css_in = [html_folder.joinpath("css", f"{c}.css") for c in css_in]
    if isinstance(js_in, str):
        js_in = [js_in]
    js_in = ["details"] + js_in
    js_in = [html_folder.joinpath("js", f"{j}.js") for j in js_in]
    if isinstance(template, str):
        template = f"{template}.html"
    template = env.get_template(template)
    css_out = []
    for css in css_in:
        with open(css, "r") as f:
            css_out.append(f.read())
    js_out = []
    for js in js_in:
        with open(js, "r") as f:
            js_out.append(f.read())
    return template.render(css=css_out, js=js_out, **kwargs)


def convert_well_to_row_column(input_str: str) -> Tuple[int | None, int | None]:
    """
    Converts alphanumeric coordinates to 1-based row and column integers.
    Will still return a row index if the column numbers are missing.
    
    Args:
        input_str (str): Input string. Ex. "AA10" or "AA"
        
    Returns:
        Tuple[int | None, int | None]: (row, column) integers.
    """
    # row_keys = {v: k for k, v in row_map.items()}
    # try:
    #     row = int(row_keys[input_str[0].upper()])
    #     column = int(input_str[1:])
    # except IndexError:
    #     return None, None
    # return row, column
    # Match an arbitrary number of letters followed by an arbitrary number of digits
    clean_str = input_str.strip()
    if not clean_str:
        return None, None

    # Match starting letters and optional trailing digits
    match = rmatch(r"^([A-Za-z]+)([0-9]*)$", clean_str)
    if not match:
        return None, None
        
    row_str, col_str = match.groups()
    
    # Convert arbitrary row letters to a 1-based index (A=1, B=2, AA=27)
    row = 0
    for char in row_str.upper():
        row = row * 26 + (ord(char) - ord('A') + 1)
        
    # Safely convert column if digits exist
    column = int(col_str) if col_str else None
    
    return row, column


def convert_row_column_to_well(row: int, column: int|None=None) -> str | None:
    """
    Converts 1-based integer row and column coordinates back to an alphanumeric string.
    
    Args:
        row (int): 1-based row index (e.g., 1, 27).
        column (int | None): 1-based column index (e.g., 2, 10). Defaults to None
        
    Returns:
        str | None: Alphanumeric coordinate string (e.g., "A2", "AA10"), 
                    or None if inputs are invalid.
    """
    if not isinstance(row, int):
        return None
    # Guard against invalid 1-based indices
    if row <= 0:
        return None
    if column is None or column <= 0:
        column = ""
    # Convert row integer back to Excel-style letters (base-26)
    row_str = ""
    while row > 0:
        row, remainder = divmod(row - 1, 26)
        row_str = chr(65 + remainder) + row_str
        
    return f"{row_str}{column}"


def list_str_comparator(target_str: str, list_: List[str], mode: Literal["starts_with", "contains"] = "starts_with") -> bool:
    """
    If target string starts with/contains any string in a list, return true.

    Args: 
        target_str (str): String to be tested against list.
        list_ (str): List of the tests to be run.
        mode (Literal["starts_with", "contains"]): comparisons to be run. Defaults to "starts_with".

    Returns:
        bool: whether target string starts with/contains any string in the list.
    
    """
    match mode:
        case "starts_with":
            if any([target_str.startswith(item) for item in list_]):
                return True
            else:
                return False
        case _:
            if any([item in target_str for item in list_]):
                return True
            else:
                return False


def find_paths_to_value(target_key, data: dict) -> Generator[Tuple[dict, list], None, None]:
        
    """Iterates through a nested dictionary.
    
    Once a match is found, the function locks into that top-level key
    and yields the entire dictionary container that holds the target_key,
    along with the path leading to that container.
    """
    for top_key, top_value in data.items():
        # Inner helper to perform standard recursive search
        def _search(current_data, current_path):
            if isinstance(current_data, dict):
                for k, v in current_data.items():
                    # If target is found, yield the current parent dictionary
                    if k == target_key:
                        yield current_data, current_path
                    
                    next_path = current_path + [k]
                    yield from _search(v, next_path)

        # Initialize the generator for the current top-level branch
        branch_generator = _search(top_value, [top_key])
        
        try:
            # Check if the branch contains at least one match
            first_match = next(branch_generator)
            yield first_match
            # Yield all remaining containers matching the target in this branch
            yield from branch_generator
            # Stop searching any other top-level keys
            break 
        except StopIteration:
            # No match in this branch, move to the next top-level key
            continue


def convert_strings(data):
    if isinstance(data, dict):
        return {k: convert_strings(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_strings(item) for item in data]
    elif isinstance(data, str):
        try:
            if "." in data:
                return float(data)
            return int(data)
        except ValueError:
            return data
    return data


def get_prioritized_dict_prefix(data, target_prefixes):
    # Base case: if it is a list, process any dictionaries inside it
    if isinstance(data, list):
        return [get_prioritized_dict_prefix(item, target_prefixes) for item in data]
    
    # Base case: if it is not a dictionary, return it as-is
    if not isinstance(data, dict):
        return data

    # 1. First, recursively process all nested items
    processed_data = {}
    for key, value in data.items():
        processed_data[key] = get_prioritized_dict_prefix(value, target_prefixes)

    # 2. Rebuild the current level dictionary with prioritized keys at the top
    new_dict = {}
    
    # Track which keys we have already moved to avoid duplicates
    moved_keys = set()

    # Move matching keys to the top in the order of the target_prefixes list
    for prefix in target_prefixes:
        for key in processed_data:
            if key not in moved_keys and str(key).startswith(prefix):
                new_dict[key] = processed_data[key]
                moved_keys.add(key)

    # Append all remaining unmoved keys
    for key, value in processed_data.items():
        if key not in moved_keys:
            new_dict[key] = value

    return new_dict


def sort_dict_by_list(dictionary: dict, order_list: list) -> dict:
    output = OrderedDict()
    for item in order_list:
        try:
            output[item] = dictionary[item]
        except KeyError:
            continue
    for k, v in dictionary.items():
        if k in output:
            continue
        output[k] = v
    return output


def setup_lookup(func):
    """
    Checks to make sure all args are allowed

    Args:
        func (_type_): wrapped function
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        from backend.validators import SourcedField
        sanitized_kwargs = {}
        for k, v in locals()['kwargs'].items():
            match v:
                case dict():
                    if not v:
                        continue
                    try:
                        sanitized_kwargs[k] = v['value']
                    except KeyError:
                        raise ValueError(f"Could not sanitize dictionary {v} in query. Make sure you parse it first.")
                case SourcedField():
                    try: 
                        sanitized_kwargs[k] = v.value
                    except AttributeError:
                        raise AttributeError(f"Could not sanitize SourcedField {v} in query. Make sure you parse it first.")
                case _:
                    sanitized_kwargs[k] = v
        if set(sanitized_kwargs.keys()) & set(["name", "id"]):
            sanitized_kwargs['limit'] = 1
        return func(*args, **sanitized_kwargs)
    return wrapper


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


class AlertStatus(str, Enum):
    """
    Deliberately uses the exact PyQt6 QMessageBox.Icon member names as values,
    so AlertPop can resolve an icon with getattr(QMessageBox.Icon, status.value)
    without re-validating the string at the point of use.
    """
    NO_ICON = "NoIcon"
    QUESTION = "Question"
    INFORMATION = "Information"
    WARNING = "Warning"
    CRITICAL = "Critical"


class Alert(BaseModel, arbitrary_types_allowed=True):
    owner: str = Field(default="", validate_default=True)
    code: int = Field(default=0)
    msg: str | Exception
    status: AlertStatus = Field(default=AlertStatus.NO_ICON.value)

    @field_validator('status', mode='before')
    @classmethod
    def to_title(cls, value: AlertStatus | str) -> AlertStatus:
        # NOTE: still accepts old-style strings ("warning", "Critical", etc.)
        # for backward compatibility with existing call sites, but now
        # validates against real AlertStatus members instead of blindly
        # .title()-casing whatever comes in.
        if isinstance(value, AlertStatus):
            return value.value
        normalized = str(value).strip().lower().replace(" ", "")
        try:
            return next(s for s in AlertStatus if s.value.lower() == normalized)
        except StopIteration:
            raise ValueError(
                f"{value!r} is not a valid AlertStatus. "
                f"Choose one of: {[s.value for s in AlertStatus]}"
            )

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
        return f"Alert({self.owner})"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = stack()[1].function

    def report(self):
        from frontend.widgets.pop_ups import AlertPop
        return AlertPop(message=self.msg, status=self.status, owner=self.owner)


class Report(BaseModel):
    results: List[Alert] = Field(default=[])

    def __repr__(self):
        return f"<Report(result_count:{len(self.results)})>"

    def __str__(self):
        return f"<Report(result_count:{len(self.results)})>"

    def add_result(self, result: Alert | Report | None):
        """
        Takes a result object or all results in another report and adds them to this one.

        Args:
            result (Alert | Report | None): Results to be added.
        """
        match result:
            case Alert():
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
                logger.error(f"Unknown variable type: {type(result)} for <Alert> entry into <Report>")


def is_developer() -> bool:
    """
    Checks if user is in list of super users

    Returns:
        bool: True if yes, False if no.
    """
    try:
        check = getuser() in ctx.super_users
    except (ValueError, AttributeError, TypeError):
        check = False
    return check


def is_power_user() -> bool:
    """
    Checks if user is in list of power users

    Returns:
        bool: True if yes, False if no.
    """
    try:
        check = getuser() in ctx.power_users
    except (ValueError, AttributeError, TypeError):
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
        error_msg = f"User {getuser()} is not authorized for this function."
        auth_func = is_power_user
        if auth_func():
            return func(*args, **kwargs)
        else:
            logger.error(error_msg)
            report = Report()
            report.add_result(
                Alert(owner=func.__str__(), code=1, msg=error_msg, status=AlertStatus.WARNING.value))
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
            error_msg = f"User {getuser()} is not authorized for this function."
            logger.error(error_msg)
            report = Report()
            report.add_result(
                Alert(owner=func.__str__(), code=1, msg=error_msg, status=AlertStatus.WARNING.value))
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
        for result in results:
            try:
                dlg = result.report()
                if "testing" in args:
                    return report
                else:
                    dlg.exec()
            except Exception as e:
                logger.error(f"Problem reporting due to {e}")
                logger.exception(result.msg)
        if output:
            logger.info(f"Report result being called by {func.__name__}")
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
                check = bool(iter(object))
            except TypeError:
                check = False
            return check


def create_holidays_for_year(year: int | None = None) -> List[date]:
    """
    Gives stat holidays for the input year.

    Args:
        year (int | None, optional): The input year as an integer. Defaults to None.

    Returns:
        List[date]
    """
    def find_nth_monday(year, month, occurrence: int | None = None, day: int | None = None) -> date:
        """
        Gets the nth (eg 2nd) monday of the given month.

        Args:
            year (int): The year the month occurs in.
            month (int): The month of interest.
            occurrence (int): The n in nth.
            day (int): The day of the month to start after.

        Returns:
            date
        """
        if not occurrence:
            occurrence = 1
        if not day:
            day = occurrence * 7
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
    # NOTE: Static holidays. Includes New Year's day for next year.
    holidays = [date(year, 1, 1), date(year, 7, 1), date(year, 9, 30),
                date(year, 11, 11), date(year, 12, 25), date(year, 12, 26),
                date(year + 1, 1, 1)]
    # NOTE: Labour Day
    holidays.append(find_nth_monday(year, 9))
    # NOTE: Thanksgiving
    holidays.append(find_nth_monday(year, 10, occurrence=2))
    # NOTE: Victoria Day
    holidays.append(find_nth_monday(year, 5, day=25))
    # NOTE: Easter, etc
    holidays.append(easter(year) - timedelta(days=2))
    holidays.append(easter(year) + timedelta(days=1))
    return sorted(holidays)


def flatten_list(input_list: list) -> list:
    """
    Takes nested lists and returns a single flat list.

    Args:
        input_list (list): input nested list.

    Returns:
        list:
    """
    return list(chain.from_iterable(input_list))


def handle_keys(key:str) -> str:
    key = key.replace("type", " type").strip()
    key = key.replace("role", " role").strip()
    key = key.replace("version", " version").strip()
    key = key.replace("lot", " lot").strip()
    key = key.replace("lab", " lab").strip()
    key = key.replace("_", " ")
    key = key.title()
    key = key.replace(" Id", " ID")
    key = key.replace("Ww", "WW")
    key = key.replace("Rsl", "RSL")
    key = key.replace("Pcr", "PCR")
    key = " ".join(key.split())
    return key


def handle_results(input_value:dict|str, html: bool=True, keep_iso: bool = False) -> str|None:
    if isinstance(input_value, dict):
        input_value = input_value.get("value", input_value)
    match input_value:
        case bool():
            output = str(input_value).title()
        case str() | int() | float():
            output = str(input_value)
            if html:
                output = html_escape(output)
        case datetime() | date():
            output = input_value.isoformat(timespec='minutes')
            if not html:
                output = output.split("T")[0]
            elif not keep_iso:
                output = output.split("T")[0]
        case None:
            output = html_escape("NA")
        case _:
            if not input_value:
                return None
            try:
                output = jdumps(input_value, indent=4)
            except (TypeError, ValueError):
                logger.error(f"Could not convert {input_value} to json for display. Displaying as string instead.")
                output = str(input_value)
            if html:
                output = f"<pre>{html_escape(output)}</pre>"
    output = rsub(r'[{}]|&quot;|,', '', output)
    
    return output


def sanitize_object_for_json(input_obj):

    from backend.db.models import BaseClass
    match input_obj:
        case datetime() | date():
            return input_obj.isoformat()
        case list():
            return [sanitize_object_for_json(item) for item in input_obj]
        case dict():
            return {k: sanitize_object_for_json(v) for k, v in input_obj.items()}
        case _ if issubclass(input_obj.__class__, BaseClass):
            return sanitize_object_for_json(input_obj.name)
        case _:
            return input_obj


def iterable_enforcer(value, pass_dict: bool = True) -> list:
        if value is None:
            return []
        if isinstance(value, Iterable):
            if isinstance(value, dict) and pass_dict:
                pass
            elif not isinstance(value, str):
                return list(value)
            else:
                pass
        return [value]


_MISC_INFO_INTERNAL_MARKERS = ("AssociationProxy", "sa_instance_state", "_sa_")


def is_internal_attr_key(key) -> bool:
    """
    True if `key` looks like SQLAlchemy/ORM-internal bookkeeping rather than
    real data - e.g. association_proxy's per-instance cache attributes like
    "_AssociationProxy_<target>_<id>". SQLAlchemy setattr()'s these directly;
    they must never be captured into _misc_info.
    """
    return isinstance(key, str) and key.startswith("_") and any(m in key for m in _MISC_INFO_INTERNAL_MARKERS)


class DictMode(Enum):
    POP = "pop"
    RETURN = "return"
    INDEX = "index"    


def find_first_matching_dict(list_of_dicts, key, value_to_match, mode: DictMode = DictMode.POP) -> dict | Tuple[int, dict]:
    """
    Removes and returns the first dictionary in the list where
    the specified key's value matches the value_to_match.

    Args:
        list_of_dicts: The list of dictionaries to search.
        key: The dictionary key to check the value against.
        value_to_match: The value to match for the given key.

    Returns:
        The popped dictionary, or None if no match is found.
    """
    from backend.validators.pydant import PydBaseClass
    from backend.db.models import BaseClass
    for index, d in enumerate(list_of_dicts):
        match d:
            case dict():
                d_value = d.get(key)
            case _ if issubclass(d.__class__, PydBaseClass):
                d_value = getattr(d, key)
            case _ if issubclass(d.__class__, BaseClass):
                d_value = getattr(d, key)
            case _ if hasattr(d, "__dict__") or hasattr(d, key): # <--- Set for test purposes
                d_value = getattr(d, key)
            case str() | int() | float() | bool():
                d_value = d
            case _:
                raise ValueError(f"Unmatched value {type(d)}")
        if d_value == value_to_match:
            if mode.value == "pop":
                # Pop and return the dictionary at the found index
                return index, list_of_dicts.pop(index)
            elif mode.value == "return":
                return d
            elif mode.value == "index":
                return index, d
            else:
                pass
    # Return None if no matching dictionary is found
    raise StopIteration(f"Could not find {key} value")


class IndexDirection(Enum):
    COL = "col"
    ROW = "row"


class TimeFill(Enum):
    MIN = datetime.min.time
    MAX = datetime.max.time


def ensure_list(v: Any) -> List:
    if isinstance(v, (Generator, filter, map)):
        return list(v)
    return v


class classproperty(property):
    """
    Allows for properties on classes as well as objects.
    """
    def __init__(self, f):
        self.f = f
    def __get__(self, obj, cls=None):
        if cls is None:
            cls = type(obj)
        return self.f(cls)


# NOTE: Monkey patching... hooray!
builtins.classproperty = classproperty


class DotDict(dict):
    """A helper to allow dot notation on dictionaries while supporting standard dict syntax."""
    
    def __getattr__(self, name: str) -> Any:
        try:
            value = self[name]
            # Recursively wrap nested dicts so they also support dot notation
            return DotDict(value) if isinstance(value, dict) else value
        except KeyError:
            raise AttributeError(f"No attribute named '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        # Allows setting values via dot notation: d.key = value
        self[name] = value

    def __delattr__(self, name: str) -> None:
        # Allows deleting values via dot notation: del d.key
        try:
            del self[name]
        except KeyError:
            raise AttributeError(f"No attribute named '{name}'")


class AlembicModes(Enum):
        PATH = "path"
        SCHEMA = "schema"
        USER = "user"
        PASS = "pass"


class Settings(BaseSettings, extra="allow"):
    """
    Pydantic model to hold settings

    Raises:
        FileNotFoundError: Error if database not found.

    """
    database: DotDict = Field(default_factory=DotDict)
    directories: DotDict = Field(default_factory=DotDict)
    package: Any | None = None
    logging_enabled: bool = Field(default=False)

    def __getattr__(self, name: str) -> Any:
        # Use the public model_extra API
        extra = self.model_extra
        if extra and name in extra:
            value = extra[name]
            # Wrap dictionaries so something like user_data.email works
            return DotDict(value) if isinstance(value, dict) else value
        
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    @classproperty
    def main_aux_dir(cls):
        if system() == "Windows":
            os_config_dir = "AppData/local"
        else:
            os_config_dir = ".config"
        return Path.home().joinpath(f"{os_config_dir}/submissions_tng")

    @classproperty
    def configdir(cls):
        return cls.main_aux_dir.joinpath("config")

    @classproperty
    def logdir(cls):
        return cls.main_aux_dir.joinpath("logs")

    def __new__(cls, *args, **kwargs):
        
        settings_path = kwargs.get("settings_path", None)
        if isinstance(settings_path, str):
                settings_path = Path(settings_path)

        if settings_path is None:
            # NOTE: Check user .config/procedure directory
            if cls.configdir.joinpath("config.yml").exists():
                settings_path = cls.configdir.joinpath("config.yml")
            # NOTE: Check user .procedure directory
            elif Path.home().joinpath(".submissions_tng", "config.yml").exists():
                settings_path = Path.home().joinpath(".submissions_tng", "config.yml")
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
        return super().__new__(cls, **kwargs)

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
    
    @field_validator("directories", mode="before")
    @classmethod
    def enforce_directory_settings(cls, value):
        if isinstance(value, dict):
            directories = DotDict(value)
        elif isinstance(value, DotDict):
            directories = value
        else:
            raise ValidationError(f"Unsupported database model: {value}")
        return directories

    @field_validator("database", mode="before")
    @classmethod
    def enforce_database_settings(cls, value):
        if isinstance(value, dict):
            database = DotDict(value)
        elif isinstance(value, DotDict):
            database = value
        else:
            raise ValidationError(f"Unsupported database model: {value}")
        match database.schema:
            case "sqlite":
                value = f"/{database.path}"
                db_name = f"{database.name}.db"
                template = jinja_template_loading().from_string(
                    "{{ database.schema }}://{{ value }}/{{ db_name }}")
            case "mssql+pyodbc":
                value = database.path
                db_name = database.name
                template = jinja_template_loading().from_string(
                    "{{ database.schema }}://{{ value }}/{{ db_name }}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes&Trusted_Connection=yes"
                )
            case _:
                tmp = jinja_template_loading().from_string(
                    "{% if database.user %}{{ database.user }}{% if database.password %}:{{ database.password }}{% endif %}{% endif %}@{{ database.path }}")
                value = tmp.render(values=values.data)
                db_name = database.name
        database_path = template.render(database=database, value=value, db_name=db_name)
        print(f"Using {database_path} for database path")
        engine = create_engine(database_path)
        database.engine = engine
        database.session = scoped_session(sessionmaker(bind=engine))
        return database
        
    
    @field_validator('package', mode="before")
    @classmethod
    def import_package(cls, value):
        import __init__ as package
        if value is None:
            return package
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            del kwargs['settings_path']
        except KeyError:
            pass
        self.set_from_db()
        self.set_scripts()
        self.save()

    @contextmanager
    def db_session(self):
        session = self.database.session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self.database.session.remove()

    def close_database(self):
        """Close the active database session and dispose the engine."""
        engine = self.database.engine
        if engine is None and self.database.session is not None:
            try:
                engine = self.database.session.get_bind()
            except Exception:
                engine = None
        if self.database.session is not None:
            try:
                self.database.session.close()
            except Exception as e:
                logger.exception(f"Error closing database session: {e}")
            finally:
                self.database.session = None
        if engine is not None:
            try:
                engine.dispose()
            except Exception as e:
                logger.exception(f"Error disposing database engine: {e}")
            finally:
                self.database.engine = None

    def set_from_db(self):
        if 'pytest' in sys.modules:
            output = dict(power_users=['lwark', 'styson', 'ruwang'],
                          super_users=['lwark'],
                          startup_scripts=dict(hello=None),
                          teardown_scripts=dict(goodbye=None)
                          )
        else:
            session = self.database.session
            metadata = MetaData()
            try:
                metadata.reflect(bind=self.database.engine)
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
                    output[item[1]] = jloads(item[2])
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
            try:
                mod = import_module(module.stem)
            except ImportError as e:
                logger.exception(f"Error loading module: {e}")
                continue
            for function in getmembers(mod, isfunction):
                name = function[0]
                func = function[1]
                # NOTE: assign function based on its name being in config: startup/teardown
                # NOTE: scripts must be registered using {name: Null} in the database
                try:
                    if name in self.startup_scripts.keys():
                        self.model_extra['startup_scripts'][name] = func
                except AttributeError as e:
                    print(f"Couldn't set startup function due to {e}")
                    pass
                try:
                    if name in self.teardown_scripts.keys():
                        self.model_extra['teardown_scripts'][name] = func
                except AttributeError as e:
                    print(f"Couldn't set teardown function due to {e}")
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
                    logger.exception(f"Couldn't run teardown script: {script}")
        except AttributeError:
            logger.exception(f"Couldn't run teardown scripts.")
        finally:
            self.close_database()
            
    @classmethod
    def get_alembic_db_path(cls, alembic_path, mode:AlembicModes = AlembicModes.PATH) -> Path | str:
        """
        Retrieves database variables from alembic.ini file.
        Currently uused, but will keep it around.

        Args:
            alembic_path (Any): Path of the alembic.ini file.
            mode (Literal['path', 'schema', 'user', 'pass']): Variable of interest.

        Returns:
            Path | str
        """
        c = ConfigParser()
        c.read(alembic_path)
        url = c['alembic']['sqlalchemy.url']
        match mode:
            case AlembicModes.PATH:
                path = rsub(r"^.*//", "", url)
                path = rsub(r"^.*@", "", path)
                return Path(path)
            case AlembicModes.SCHEMA:
                return url[:url.index(":")]
            case AlembicModes.USER:
                url = rsub(r"^.*//", "", url)
                try:
                    return url[:url.index("@")].split(":")[0]
                except (IndexError, ValueError) as e:
                    logger.exception(f"Couldn't parse url: {url}")
                    return None
            case AlembicModes.PASS:
                url = rsub(r"^.*//", "", url)
                try:
                    return url[:url.index("@")].split(":")[1]
                except (IndexError, ValueError) as e:
                    logger.exception(f"Couldn't parse url: {url}")
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
                if k in ['package']:
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
                ydump(dicto, f)


ctx = Settings()
jinja_env = jinja_template_loading()