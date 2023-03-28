'''
Contains miscellaenous functions used by both frontend and backend.
'''
import re
import sys
import numpy as np
import logging
import getpass
from backend.db.models import BasicSubmission, KitType
from typing import Tuple

logger = logging.getLogger(f"submissions.{__name__}")

def check_not_nan(cell_contents) -> bool:
    """
    Check to ensure excel sheet cell contents are not blank.

    Args:
        cell_contents (_type_): The contents of the cell in question.

    Returns:
        bool: True if cell has value, else, false.
    """    
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
    """
    Check to ensure current user is in power users list.

    Args:
        ctx (dict): settings passed down from gui.

    Returns:
        bool: True if user is in power users, else false.
    """    
    try:
        check = getpass.getuser() in ctx['power_users']
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
        result = {'message' : f"The submission you are importing is missing some reagents expected by the kit.\n\nIt looks like you are missing: {[item.upper() for item in missing]}\n\nAlternatively, you may have set the wrong extraction kit.\n\nThe program will populate lists using existing reagents.\n\nPlease make sure you check the lots carefully!", 'missing': missing}
    return result


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
    in_str = in_str.split("\\")[-1]
    logger.debug(f"Attempting match of {in_str}")
    regex = re.compile(r"""
        (?P<wastewater>RSL-WW-20\d{6})|(?P<bacterial_culture>RSL-\d{2}-\d{4})
        """, re.VERBOSE)
    m = regex.search(in_str)
    return (m.group(), m.lastgroup)
    