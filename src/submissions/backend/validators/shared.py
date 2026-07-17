from __future__ import annotations
from logging import getLogger
from typing import List
logger = getLogger(f"submissions.{__name__}")
from datetime import datetime, date, timedelta
from dateutil.parser import parse as dateparse, ParserError
from re import sub as rsub
from tools import iterable_enforcer, timezone, TimeFill


def coerce_none_to_na(value: str | None) -> str:
    return "NA" if value is None else value

def coerce_int_to_bool(value) -> bool:
    if value is None:
        value = True
    if isinstance(value, str):
        if value.lower() in ["false", "0", "no", "off"]:
            value = False
        elif value.lower() in ["true", "1", "yes", "on"]:
            value = True
        else:
            raise ValueError(f"Unparseable string {value}")
    if isinstance(value, int):
        value = bool(value)
    return value

def parse_optional_datetime(value, timefill: TimeFill | None = None) -> datetime | None:
    from . import SourcedField
    match value:
        case dict():
            value = value.get("value", datetime.now())
        case SourcedField():
            value = value.value
        case None:
            value = datetime.now()
        case _:
            pass
    match value:
        case str():
            string = rsub(r"(_|-)\d(R\d)?$", "", value)
            try: 
                output = dateparse(string)
            except ParserError: 
                logger.exception(f"Problem parsing date: {e}")
                try:
                    output = dateparse(string.replace("-", ""))
                except Exception as e2:
                    logger.exception(f"Problem with parse fallback: {e2}")
                    output = datetime.now()   # <- bug: setters ignore return values; this is now baked into all 5 copies
        case date():
            output = datetime.combine(value, datetime.now().time())
        case datetime():
            output = value
        case int():
            output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
        case _:
            output = datetime.now()
    if timefill:
        output = datetime.combine(output, timefill.value())
    return output.replace(tzinfo=timezone)
    
        
def parse_expiry(value, days: int = 365) -> datetime | None:
    if not value:
        value = date.today() + timedelta(days=days)
    value = parse_optional_datetime(value, timefill=TimeFill.MAX)
    return value

def vet_comment(value: dict | List[dict], current: List[dict] = []) -> List[dict]:
    value = iterable_enforcer(value)
    logger.debug(f"Vetting comment: {value}")
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
    
    