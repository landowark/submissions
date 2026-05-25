from datetime import datetime, date, timedelta
from dateutil.parser import parse, ParserError


def coerce_none_to_na(value: str | None) -> str:
    return "NA" if value is None else value

def coerce_int_to_bool(value) -> bool:
    if value is None:
        value = True
    if isinstance(value, str):
        if value.lower() in ["false", "0", "no", "off"]:
            value = False
        else:
            value = True
    if isinstance(value, int):
        value = bool(value)
    return value

def parse_optional_datetime(value) -> datetime | None:
    if not value:
        return None
    match value:
        case str():
            try: return parse(value)
            except ParserError: return None
        case date():
            return datetime.combine(value, datetime.min.time())
        case datetime():
            return value
        case _:
            return None
        
def parse_expiry(value, class_name):
    if not value:
        t = 365
        if class_name == "PydTipsLot":
            t = t * 10
        value = date.today() + timedelta(days=t)
    match value:
        case str():
            try:
                value = parse(value)
            except ParserError:
                value = None
        case date() | datetime():
            value = datetime.combine(value, datetime.max.time())
        case _:
            raise ValueError(f"Could not parse expiry date: {value}")
    return value