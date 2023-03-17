import numpy as np
import logging
import getpass
from backend.db.models import BasicSubmission, KitType

logger = logging.getLogger(f"submissions.{__name__}")

def check_not_nan(cell_contents) -> bool:
    # check for nan as a string first
    if cell_contents == 'nan':
        cell_contents = np.nan
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
        logger.debug(f"Check encountered unknown error: {type(e).__name__} - {e}")
        check = False
    return check


def create_reagent_list(in_dict:dict) -> list[str]:
    return [item.strip("lot_") for item in in_dict.keys()]


def check_kit_integrity(sub:BasicSubmission|KitType, reagenttypes:list|None=None) -> dict|None:
    """
    Ensures all reagents expected in kit are listed in Submission

    Args:
        sub (BasicSubmission | KitType): Object containing complete list of reagent types.
        reagenttypes (list | None, optional): List to check against complete list. Defaults to None.

    Returns:
        dict|None: Result object containing a message and any missing components.
    """    
    logger.debug(type(sub))
    # What type is sub?
    match sub:
        case BasicSubmission():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.extraction_kit.reagent_types]
            # Overwrite function parameter reagenttypes
            reagenttypes = [reagent.type.name for reagent in sub.reagents]
        case KitType():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.reagent_types]
    logger.debug(f"Kit reagents: {ext_kit_rtypes}")
    logger.debug(f"Submission reagents: {reagenttypes}")
    # check if lists are equal
    check = set(ext_kit_rtypes) == set(reagenttypes)
    logger.debug(f"Checking if reagents match kit contents: {check}")
    # what reagent types are in both lists?
    # common = list(set(ext_kit_rtypes).intersection(reagenttypes))
    missing = list(set(ext_kit_rtypes).difference(reagenttypes))
    logger.debug(f"Missing reagents types: {missing}")
    # if lists are equal return no problem
    if len(missing)==0:
        result = None
    else:
        # missing = [x for x in ext_kit_rtypes if x not in common]
        result = {'message' : f"Couldn't verify reagents match listed kit components.\n\nIt looks like you are missing: {[item.upper() for item in missing]}\n\nAlternatively, you may have set the wrong extraction kit.", 'missing': missing}
    return result