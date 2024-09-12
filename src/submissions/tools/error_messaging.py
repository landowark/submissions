from sqlalchemy.exc import ArgumentError, IntegrityError as sqlalcIntegrityError
import logging

logger = logging.getLogger(f"submissions.{__name__}")


def parse_error_to_message(value: Exception):
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
                # logger.debug(field)
                value = f"{field} doesn't have a unique value.\nIt must be changed."
            else:
                value = f"Got unknown integrity error: {value}"
        case _:
            value = f"Got generic error: {value}"
    return value
