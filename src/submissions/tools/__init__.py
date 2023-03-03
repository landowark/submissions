import numpy as np
import logging
import getpass

logger = logging.getLogger(f"submissions.{__name__}")

def check_not_nan(cell_contents) -> bool:
    try:
        return not np.isnan(cell_contents)
    except TypeError:
        return True
    except Exception as e:
        logger.debug(f"Check encounteded unknown error: {type(e).__name__} - {e}")
        return False


def check_is_power_user(ctx:dict) -> bool:
    try:
        check = getpass.getuser() in ctx['power_users']
    except KeyError as e:
        check = False
    except Exception as e:
        logger.debug(f"Check encounteded unknown error: {type(e).__name__} - {e}")
        check = False
    return check


def create_reagent_list(in_dict:dict) -> list[str]:
    return [item.strip("lot_") for item in in_dict.keys()]