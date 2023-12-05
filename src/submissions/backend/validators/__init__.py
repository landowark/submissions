import logging, re
from pathlib import Path
from openpyxl import load_workbook
from backend.db.models import BasicSubmission, SubmissionType


logger = logging.getLogger(f"submissions.{__name__}")

class RSLNamer(object):
    """
    Object that will enforce proper formatting on RSL plate names.
    """
    def __init__(self, instr:str, sub_type:str|None=None, data:dict|None=None):
        self.submission_type = sub_type
        if self.submission_type == None:
            self.submission_type = self.retrieve_submission_type(instr=instr)
        logger.debug(f"got submission type: {self.submission_type}")
        if self.submission_type != None:
            enforcer = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
            self.parsed_name = self.retrieve_rsl_number(instr=instr, regex=enforcer.get_regex())
            self.parsed_name = enforcer.enforce_name(instr=self.parsed_name, data=data)

    @classmethod
    def retrieve_submission_type(cls, instr:str|Path) -> str:
        """
        Gets submission type from excel file properties or sheet names or regex pattern match or user input

        Args:
            instr (str | Path): filename

        Returns:
            str: parsed submission type
        """        
        match instr:
            case Path():
                logger.debug(f"Using path method for {instr}.")
                if instr.exists():
                    wb = load_workbook(instr)
                    try:
                        submission_type = [item.strip().title() for item in wb.properties.category.split(";")][0]
                    except AttributeError:
                        try:
                            # sts = {item.name:item.info_map['all_sheets'] for item in SubmissionType.query(key="all_sheets")}
                            sts = {item.name:item.get_template_file_sheets() for item in SubmissionType.query()}
                            for k,v in sts.items():
                                # This gets the *first* submission type that matches the sheet names in the workbook 
                                if wb.sheetnames == v:
                                    submission_type = k.title()
                                    break
                        except:
                            # On failure recurse using filename as string for string method
                            submission_type = cls.retrieve_submission_type(instr=instr.stem.__str__())
                else:
                    submission_type = cls.retrieve_submission_type(instr=instr.stem.__str__())
            case str():
                regex = BasicSubmission.construct_regex()
                logger.debug(f"Using string method for {instr}.")
                m = regex.search(instr)
                try:
                    submission_type = m.lastgroup
                except AttributeError as e:
                    logger.critical("No RSL plate number found or submission type found!")
            case _:
                submission_type = None
        try:
            check = submission_type == None
        except UnboundLocalError:
            check = True
        if check:
            from frontend.widgets import SubmissionTypeSelector
            dlg = SubmissionTypeSelector(title="Couldn't parse submission type.", message="Please select submission type from list below.")
            if dlg.exec():
                submission_type = dlg.parse_form()
        submission_type = submission_type.replace("_", " ")
        return submission_type

    @classmethod
    def retrieve_rsl_number(cls, instr:str|Path, regex:str|None=None):
        """
        Uses regex to retrieve the plate number and submission type from an input string

        Args:
            in_str (str): string to be parsed
        """    
        logger.debug(f"Input string to be parsed: {instr}")
        if regex == None:
            regex = BasicSubmission.construct_regex()
        else:
            regex = re.compile(rf'{regex}', re.IGNORECASE | re.VERBOSE)
        logger.debug(f"Using regex: {regex}")
        match instr:
            case Path():
                m = regex.search(instr.stem)
            case str():
                logger.debug(f"Using string method.")
                m = regex.search(instr)
            case _:
                pass
        if m != None:
            try:
                parsed_name = m.group().upper().strip(".")
            except:
                parsed_name = None
        else: 
            parsed_name = None
        logger.debug(f"Got parsed submission name: {parsed_name}")
        return parsed_name
        
from .pydant import *