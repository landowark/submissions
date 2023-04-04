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
    """
    Uses regex to retrieve the plate number and submission type from an input string

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


def format_rsl_number(instr:str) -> str:
    """
    Enforces proper formatting on a plate number
    Depreciated, replaced by RSLNamer class

    Args:
        instr (str): input plate number

    Returns:
        str: _description_
    """    
    output = instr.upper()
    output = output.replace("_", "-")
    return output
    

def check_regex_match(pattern:str, check:str) -> bool:
    try:
        return bool(re.match(fr"{pattern}", check))
    except TypeError:
        return False
    

class RSLNamer(object):
    """
    Object that will enforce proper formatting on RSL plate names.
    """
    def __init__(self, instr:str):
        # self.parsed_name, self.submission_type = self.retrieve_rsl_number(instr)
        self.retrieve_rsl_number(in_str=instr)
        if self.submission_type != None:
            parser = getattr(self, f"enforce_{self.submission_type}")
            parser()
            self.parsed_name = self.parsed_name.replace("_", "-")
        

    def retrieve_rsl_number(self, in_str:str) -> Tuple[str, str]:
        """
        Uses regex to retrieve the plate number and submission type from an input string

        Args:
            in_str (str): string to be parsed

        Returns:
            Tuple[str, str]: tuple of (output rsl number, submission_type)
        """    
        logger.debug(f"Attempting split of {in_str}")
        try:
            in_str = in_str.split("\\")[-1]
        except AttributeError:
            self.parsed_name = None
            self.submission_type = None
            return
        logger.debug(f"Attempting match of {in_str}")
        regex = re.compile(r"""
            (?P<wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(?:_|-)\d(?!\d))?)|
            (?P<bacterial_culture>RSL-?\d{2}-?\d{4})
            """, flags = re.IGNORECASE | re.VERBOSE)
        m = regex.search(in_str)
        try:
            self.parsed_name = m.group().upper()
            self.submission_type = m.lastgroup
        except AttributeError as e:
            logger.critical("No RSL plate number found or submission type found!")
            logger.debug(f"The cause of the above error was: {e}")

    def enforce_wastewater(self):
        """
        Uses regex to enforce proper formatting of wastewater samples
        """        
        # self.parsed_name = re.sub(r"(\d)-(\d)", "\1\2", self.parsed_name)
        # year = str(date.today().year)[:2]
        self.parsed_name = re.sub(r"PCR(-|_)", "", self.parsed_name)
        self.parsed_name = self.parsed_name.replace("RSLWW", "RSL-WW")
            # .replace(f"WW{year}", f"WW-{year}")
        self.parsed_name = re.sub(r"WW(\d{4})", r"WW-\1", self.parsed_name, flags=re.IGNORECASE)
        self.parsed_name = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", self.parsed_name)

    def enforce_bacterial_culture(self):
        """
        Uses regex to enforce proper formatting of bacterial culture samples
        """        
        # year = str(date.today().year)[2:]
        # self.parsed_name = self.parsed_name.replace(f"RSL{year}", f"RSL-{year}")
        # reg_year = re.compile(fr"{year}(?P<rsl>\d\d\d\d)")
        self.parsed_name = re.sub(r"RSL(\d{2})", r"RSL-\1", self.parsed_name, flags=re.IGNORECASE)
        self.parsed_name = re.sub(r"RSL-(\d{2})(\d{4})", r"RSL-\1-\2", self.parsed_name, flags=re.IGNORECASE)
        # year = regex.group('year')
        # rsl = regex.group('rsl')
        # self.parsed_name = re.sub(fr"{year}(\d\d\d\d)", fr"{year}-\1", self.parsed_name)
        # plate_search = reg_year.search(self.parsed_name)
        # if plate_search != None:
        #     self.parsed_name = re.sub(reg_year, f"{year}-{plate_search.group('rsl')}", self.parsed_name)