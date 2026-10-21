from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from datetime import datetime, date, timedelta
from dateutil.parser import parse as dateparse, ParserError
from re import sub as rsub
from tools import iterable_enforcer, timezone, TimeFill
from typing import List, Any, TYPE_CHECKING
from enum import Enum
if TYPE_CHECKING:
    from . import SourcedField


def coerce_none_to_na(value: str | None) -> str:
    return "NA" if value is None else value

class Booleanize(Enum):
    INTEGER = int
    BOOL = bool

def booleanize(value: int | bool | str | None, mode: Booleanize = Booleanize.BOOL) -> int | bool:
    match value:
        case int() | bool():
            output = value
        case str():
            if value.lower() in ['true', '1', 'yes', 'on']:
                output = 1
            elif value.lower() in ['false', '0', 'no', 'off']:
                output = 0
            else:
                raise ValueError(f"Cannot convert string {value} to booleanize")
        case None:
            output = 0
        case _:
            raise TypeError(f"Unsupported type {type(value)} to booleanize")
    return mode.value(output)


def parse_optional_datetime(value: dict | SourcedField | str | datetime | date | int | None, timefill: TimeFill | None = None) -> datetime | None:
    from . import SourcedField
    match value:
        case dict():
            value = value.get("value", datetime.now())
        case SourcedField():
            value = value.value
        case None:
            logger.warning(f"None passed in for datetime using current datetime.")
            value = datetime.now()
        case _:
            pass
    match value:
        case str():
            if value == "NA":
                value = "1970-01-01"
            string = rsub(r"(_|-)\d(R\d)?$", "", value)
            try: 
                output = dateparse(string)
            except ParserError as e: 
                logger.exception(f"Problem parsing date: {e}")
                try:
                    output = dateparse(string.replace("-", ""))
                except Exception as e2:
                    logger.exception(f"Problem with parse fallback: {e2}")
                    output = datetime.now()   # <- bug: setters ignore return values; this is now baked into all 5 copies
        case datetime():
            output = value
        case date():
            output = datetime.combine(value, datetime.now().time())
        case int():
            output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
        case _:
            logger.warning(f"Unparsable value {value}, using current datetime.")
            output = datetime.now()
    if timefill is not None:
        output = datetime.combine(output, timefill.value())
    return output.replace(tzinfo=timezone)
    
        
def parse_expiry(value: date | None, days: int = 365) -> datetime | None:
    """
    If no expiry given uses today as a start and adds {days, defaults to 365}.

    :param value: incoming date. Defaulst to 
    :type value: date | None
    :param days: Days to add to the default value. 
    :type days: int
    :return: parse_optional_datetime(value, timefill=TimeFill.MAX)
    :rtype: datetime | None
    """
    if not value:
        value = date.today() + timedelta(days=days)
    value = parse_optional_datetime(value, timefill=TimeFill.MAX)
    return value

def vet_comment(value: dict | List[dict], current: List[dict] = []) -> List[dict]:
    value = iterable_enforcer(value)
    if not isinstance(current, list):
        current = []
    for comment in value:
        if not isinstance(comment, dict):
            logger.error(f"Invalid comment value {comment}, must be a dictionary.")
            continue
        if comment['text'] in ["", None]:
            continue
        if any([comment['time'] == x['time'] for x in current]):
            continue
        current.append(comment)
    return current
