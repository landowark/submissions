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
            try:
                reagenttypes = [reagent.type.name for reagent in sub.reagents]
            except AttributeError as e:
                logger.error(f"Problem parsing reagents: {[f'{reagent.lot}, {reagent.type}' for reagent in sub.reagents]}")
        case KitType():
            ext_kit_rtypes = [reagenttype.name for reagenttype in sub.reagent_types]
    logger.debug(f"Kit reagents: {ext_kit_rtypes}")
    logger.debug(f"Submission reagents: {reagenttypes}")
    # check if lists are equal
    check = set(ext_kit_rtypes) == set(reagenttypes)
    logger.debug(f"Checking if reagents match kit contents: {check}")
    # what reagent types are in both lists?
    missing = list(set(ext_kit_rtypes).difference(reagenttypes))
    logger.debug(f"Missing reagents types: {missing}")
    # if lists are equal return no problem
    if len(missing)==0:
        result = None
    else:
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
        print(f"The initial plate name is: {in_str}")
        regex = re.compile(r"""
            # (?P<wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(?:_|-)\d?((?!\d)|R)?\d(?!\d))?)|
            (?P<wastewater>RSL(?:-|_)?WW(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?(\D|$)R?\d?)?)|
            (?P<bacterial_culture>RSL-?\d{2}-?\d{4})|
            (?P<wastewater_artic>(\d{4}-\d{2}-\d{2}_(?:\d_)?artic)|(RSL(?:-|_)?AR(?:-|_)?20\d{2}-?\d{2}-?\d{2}(?:(_|-)\d?(\D|$)R?\d?)?))
            """, flags = re.IGNORECASE | re.VERBOSE)
        m = regex.search(in_str)
        try:
            self.parsed_name = m.group().upper()
            logger.debug(f"Got parsed submission name: {self.parsed_name}")
            self.submission_type = m.lastgroup
        except AttributeError as e:
            logger.critical("No RSL plate number found or submission type found!")
            logger.debug(f"The cause of the above error was: {e}")

    def enforce_wastewater(self):
        """
        Uses regex to enforce proper formatting of wastewater samples
        """        
        self.parsed_name = re.sub(r"PCR(-|_)", "", self.parsed_name)
        self.parsed_name = self.parsed_name.replace("RSLWW", "RSL-WW")
        self.parsed_name = re.sub(r"WW(\d{4})", r"WW-\1", self.parsed_name, flags=re.IGNORECASE)
        self.parsed_name = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1\2\3", self.parsed_name)
        print(f"Coming out of the preliminary parsing, the plate name is {self.parsed_name}")
        try:
            plate_number = re.search(r"(?:(-|_)\d)(?!\d)", self.parsed_name).group().strip("_").strip("-")
            print(f"Plate number is: {plate_number}")
        except AttributeError as e:
            plate_number = "1"
        # self.parsed_name = re.sub(r"(\d{8})(-|_\d)?(R\d)?", fr"\1-{plate_number}\3", self.parsed_name)
        self.parsed_name = re.sub(r"(\d{8})(-|_)?\d?(R\d?)?", rf"\1-{plate_number}\3", self.parsed_name)
        print(f"After addition of plate number the plate name is: {self.parsed_name}")
        try:
            repeat = re.search(r"-\dR(?P<repeat>\d)?", self.parsed_name).groupdict()['repeat']
            if repeat == None:
                repeat = "1"
        except AttributeError as e:
            repeat = ""
        self.parsed_name = re.sub(r"(-\dR)\d?", rf"\1 {repeat}", self.parsed_name).replace(" ", "")
        

        

    def enforce_bacterial_culture(self):
        """
        Uses regex to enforce proper formatting of bacterial culture samples
        """        
        self.parsed_name = re.sub(r"RSL(\d{2})", r"RSL-\1", self.parsed_name, flags=re.IGNORECASE)
        self.parsed_name = re.sub(r"RSL-(\d{2})(\d{4})", r"RSL-\1-\2", self.parsed_name, flags=re.IGNORECASE)

    def enforce_wastewater_artic(self):
        self.parsed_name = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"RSL-AR-\1\2\3", self.parsed_name, flags=re.IGNORECASE)
        try:
            plate_number = int(re.search(r"_\d?_", self.parsed_name).group().strip("_"))
        except AttributeError as e:
            plate_number = 1
        self.parsed_name = re.sub(r"(_\d)?_ARTIC", f"-{plate_number}", self.parsed_name)


def massage_common_reagents(reagent_name:str):
    logger.debug(f"Attempting to massage {reagent_name}")
    if reagent_name.endswith("water") or "H2O" in reagent_name:
        reagent_name = "molecular_grade_water"
    reagent_name = reagent_name.replace("µ", "u")
    return reagent_name
        