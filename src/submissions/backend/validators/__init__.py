import logging, re
import sys
from pathlib import Path
from openpyxl import load_workbook
from backend.db.models import BasicSubmission, SubmissionType
from tools import jinja_template_loading
from jinja2 import Template
from dateutil.parser import parse
from datetime import datetime

logger = logging.getLogger(f"submissions.{__name__}")


class RSLNamer(object):
    """
    Object that will enforce proper formatting on RSL plate names.
    """

    def __init__(self, filename: str, sub_type: str | None = None, data: dict | None = None):
        # NOTE: Preferred method is path retrieval, but might also need validation for just string.
        filename = Path(filename) if Path(filename).exists() else filename
        self.submission_type = sub_type
        if self.submission_type is None:
            # logger.debug("Creating submission type because none exists")
            self.submission_type = self.retrieve_submission_type(filename=filename)
        # logger.debug(f"got submission type: {self.submission_type}")
        if self.submission_type is not None:
            # logger.debug("Retrieving BasicSubmission subclass")
            self.sub_object = BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
            self.parsed_name = self.retrieve_rsl_number(filename=filename, regex=self.sub_object.get_regex())
            if data is None:
                data = dict(submission_type=self.submission_type)
            if "submission_type" not in data.keys():
                data['submission_type'] = self.submission_type
            self.parsed_name = self.sub_object.enforce_name(instr=self.parsed_name, data=data)

    @classmethod
    def retrieve_submission_type(cls, filename: str | Path) -> str:
        """
        Gets submission type from excel file properties or sheet names or regex pattern match or user input

        Args:
            filename (str | Path): filename

        Returns:
            str: parsed submission type
        """
        match filename:
            case Path():
                # logger.debug(f"Using path method for {filename}.")
                if filename.exists():
                    wb = load_workbook(filename)
                    try:
                        submission_type = [item.strip().title() for item in wb.properties.category.split(";")][0]
                    except AttributeError:
                        try:
                            sts = {item.name: item.get_template_file_sheets() for item in SubmissionType.query()}
                            for k, v in sts.items():
                                # This gets the *first* submission type that matches the sheet names in the workbook 
                                if wb.sheetnames == v:
                                    submission_type = k.title()
                                    break
                        except:
                            # On failure recurse using filename as string for string method
                            submission_type = cls.retrieve_submission_type(filename=filename.stem.__str__())
                else:
                    submission_type = cls.retrieve_submission_type(filename=filename.stem.__str__())
            case str():
                regex = BasicSubmission.construct_regex()
                # logger.debug(f"Using string method for {filename}.")
                m = regex.search(filename)
                try:
                    submission_type = m.lastgroup
                except AttributeError as e:
                    logger.critical("No RSL plate number found or submission type found!")
            case _:
                submission_type = None
        try:
            check = submission_type is None
        except UnboundLocalError:
            check = True
        if check:
            if "pytest" in sys.modules:
                return "Bacterial Culture"
            # logger.debug("Final option, ask the user for submission type")
            from frontend.widgets import ObjectSelector
            dlg = ObjectSelector(title="Couldn't parse submission type.",
                                 message="Please select submission type from list below.", obj_type=SubmissionType)
            if dlg.exec():
                submission_type = dlg.parse_form()
        submission_type = submission_type.replace("_", " ")
        return submission_type

    @classmethod
    def retrieve_rsl_number(cls, filename: str | Path, regex: str | None = None):
        """
        Uses regex to retrieve the plate number and submission type from an input string

        Args:
            regex (str): string to construct pattern
            filename (str): string to be parsed
        """
        # logger.debug(f"Input string to be parsed: {filename}")
        if regex is None:
            regex = BasicSubmission.construct_regex()
        else:
            regex = re.compile(rf'{regex}', re.IGNORECASE | re.VERBOSE)
        # logger.debug(f"Using regex: {regex}")
        match filename:
            case Path():
                m = regex.search(filename.stem)
            case str():
                # logger.debug(f"Using string method.")
                m = regex.search(filename)
            case _:
                m = None
        if m is not None:
            try:
                parsed_name = m.group().upper().strip(".")
            except:
                parsed_name = None
        else:
            parsed_name = None
        # logger.debug(f"Got parsed submission name: {parsed_name}")
        return parsed_name

    @classmethod
    def construct_new_plate_name(cls, data: dict) -> str:
        """
        Make a brand new plate name from submission data.

        Args:
            data (dict): incoming submission data

        Returns:
            str: Output filename
        """
        if "submitted_date" in data.keys():
            if isinstance(data['submitted_date'], dict):
                if data['submitted_date']['value'] != None:
                    today = data['submitted_date']['value']
                else:
                    today = datetime.now()
            else:
                today = data['submitted_date']
        else:
            try:
                today = re.search(r"\d{4}(_|-)?\d{2}(_|-)?\d{2}", data['rsl_plate_num'])
                today = parse(today.group())
            except (AttributeError, KeyError):
                today = datetime.now()
        if "rsl_plate_num" in data.keys():
            plate_number = data['rsl_plate_num'].split("-")[-1][0]
        else:
            previous = BasicSubmission.query(start_date=today, end_date=today, submission_type=data['submission_type'])
            plate_number = len(previous) + 1
        return f"RSL-{data['abbreviation']}-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}-{plate_number}"

    @classmethod
    def construct_export_name(cls, template: Template, **kwargs) -> str:
        """
        Make export file name from jinja template. (currently unused)

        Args:
            template (jinja2.Template): Template stored in BasicSubmission

        Returns:
            str: output file name.
        """
        # logger.debug(f"Kwargs: {kwargs}")
        # logger.debug(f"Template: {template}")
        environment = jinja_template_loading()
        template = environment.from_string(template)
        return template.render(**kwargs)


from .pydant import PydSubmission, PydKit, PydContact, PydOrganization, PydSample, PydReagent, PydReagentType, \
    PydEquipment, PydEquipmentRole
