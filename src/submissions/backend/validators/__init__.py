"""
Contains all validators
"""
from __future__ import annotations
import logging, re
import sys
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.workbook import Workbook
from tools import jinja_template_loading
from jinja2 import Template
from dateutil.parser import parse
from datetime import date, datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.db.models import SubmissionType

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultNamer(object):

    def __init__(self, filepath: str | Path | Workbook, **kwargs):
        if isinstance(filepath, str):
            filepath = Path(filepath)
        if isinstance(filepath, Path):
            try:
                assert filepath.exists()
            except AssertionError:
                raise FileNotFoundError(f"File {filepath} does not exist.")
            self.filepath = filepath
            self.workbook = load_workbook(self.filepath)
        elif isinstance(filepath, Workbook):
            self.workbook = filepath


class ClientSubmissionNamer(DefaultNamer):

    def __init__(self, filepath: str | Path | Workbook , submissiontype: str|SubmissionType|None=None,
                 data: dict | None = None, **kwargs):
        from backend.db.models import SubmissionType
        super().__init__(filepath=filepath)
        
        if not submissiontype:
            self.submissiontype = self.retrieve_submissiontype()
        if isinstance(submissiontype, str):
            self.submissiontype = SubmissionType.query(name=submissiontype)

    def retrieve_submissiontype(self) -> SubmissionType:
        """
        Gets submissiontype from the input file.

        Returns
        """
        from backend.db.models import SubmissionType
        # NOTE: Attempt 1, get from form properties:
        sub_type = self.get_subtype_from_properties()
        if not sub_type:
            # NOTE: Attempt 2, get by opening file and using default parser
            logger.warning(f"Getting submissiontype from file properties failed, falling back on preparse.\nDepending on excel structure this might yield an incorrect submissiontype")
            sub_type = self.get_subtype_from_preparse()
        if not sub_type:
            logger.warning(f"Getting submissiontype from preparse failed, falling back on filename regex.\nDepending on file name this might yield an incorrect submissiontype")
            sub_type = self.get_subtype_from_regex()
        if not sub_type:
            logger.warning(f"Getting submissiontype from regex failed, asking user.")
            from frontend.widgets import ObjectSelector
            dlg = ObjectSelector(title="Couldn't parse submission type.",
                                 message="Please select submission type from list below.",
                                 obj_type=SubmissionType)
            if dlg.exec():
                sub_type = dlg.parse_form()
        if not sub_type:
            logger.warning(f"Getting submissiontype from regex failed, using default submissiontype.")
            sub_type = SubmissionType.query(name="Default SubmissionType", limit=1)
        return sub_type

    def get_subtype_from_regex(self) -> SubmissionType:
        """
        Uses Regex of file name to get submissiontype.

        Returns:
            SubmissionType
        """
        from backend.db.models import SubmissionType
        regex = SubmissionType.regexes
        m = regex.search(self.filepath.__str__())
        try:
            sub_type = m.lastgroup
            sub_type = SubmissionType.query(name=sub_type)
        except AttributeError as e:
            sub_type = None
            logger.critical(f"No procedure type found or procedure type found!: {e}")
        if isinstance(sub_type, list):
            sub_type = None
        return sub_type

    def get_subtype_from_preparse(self) -> SubmissionType:
        """
        Uses pre-parse of Client Info sheet to get submissiontype.

        Returns:
            SubmissionType
        """
        from backend.db.models import SubmissionType
        from backend.excel.parsers import DefaultKEYVALUEParser
        parser = DefaultKEYVALUEParser(worksheet=self.workbook["Client Info"])
        sub_type = next((value for k, value in parser.parsed_info if k in ["submissiontype", "submission_type"]), None)
        sub_type = SubmissionType.query(name=sub_type)
        if isinstance(sub_type, list):
            sub_type = None
        return sub_type

    def get_subtype_from_properties(self) -> SubmissionType:
        """
        Uses Excel file properties to get submissiontype

        Returns:
            SubmissionType
        """
        from backend.db.models import SubmissionType
        
        # NOTE: Gets first category in the metadata.
        try:
            categories = self.workbook.properties.category.split(";")
        except AttributeError:
            return None
        sub_type = next((item.strip().title() for item in categories), None)
        sub_type = SubmissionType.query(name=sub_type)
        if isinstance(sub_type, list):
            sub_type = None
        return sub_type


class RSLNamer(object):
    """
    Object that will enforce proper formatting on RSL plate names.
    """

    # def __init__(self, filename: str, submission_type: str | None = None, data: dict | None = None):
    def __init__(self, submission_type: str | SubmissionType | dict):
        from backend.db.models import SubmissionType
        # NOTE: Preferred method is path retrieval, but might also need validation for just string.
        # filename = Path(filename) if Path(filename).exists() else filename
        # if not submission_type:
        #     submission_type = self.retrieve_submission_type(filename=filename)
        match submission_type:
            case str():
                self.sub_object = SubmissionType.query(name=submission_type, limit=1)
                self.submission_type = submission_type
            case dict():
                self.sub_object = SubmissionType.query(name=submission_type['value'], limit=1)
                self.submission_type = submission_type['value']
            case SubmissionType():
                self.sub_object = submission_type
                self.submission_type = submission_type.name
            case _:
                raise TypeError(f"Unmatched type {type(submission_type)} for submission_type")
        
        # self.parsed_name = self.retrieve_rsl_number(filename=filename, regex=self.sub_object.get_regex(
        #     submission_type=self.submission_type))

        # logger.info(f"Parsed name: {self.parsed_name}")

    # @classmethod
    # def retrieve_submission_type(cls, filename: str | Path) -> str:
    #     """
    #     Gets procedure type from excel file properties or sheet names or regex pattern match or user input

    #     Args:
    #         filename (str | Path): filename

    #     Raises:
    #         TypeError: Raised if unsupported variable type for filename given.

    #     Returns:
    #         str: parsed procedure type
    #     """
    #     from backend.db.models import SubmissionType
    #     def st_from_path(filepath: Path) -> str:
    #         """
    #         Sub def to get proceduretype from a file path

    #         Args:
    #             filepath ():

    #         Returns:

    #         """
    #         if filepath.exists():
    #             wb = load_workbook(filepath)
    #             try:
    #                 # NOTE: Gets first category in the metadata.
    #                 categories = wb.properties.category.split(";")
    #                 submission_type = next(item.strip().title() for item in categories)
    #             except (StopIteration, AttributeError):
    #                 sts = {item.name: item.template_file_sheets for item in SubmissionType.query() if
    #                        item.template_file}
    #                 try:
    #                     submission_type = next(k.title() for k, v in sts.items() if wb.sheetnames == v)
    #                 except StopIteration:
    #                     # NOTE: On failure recurse using filepath as string for string method
    #                     submission_type = cls.retrieve_submission_type(filename=filepath.stem.__str__())
    #         else:
    #             submission_type = cls.retrieve_submission_type(filename=filepath.stem.__str__())
    #         return submission_type

    #     def st_from_str(file_name: str) -> str:
    #         if file_name.startswith("tmp"):
    #             return "Bacterial Culture"
    #         regex = SubmissionType.regexes
    #         m = regex.search(file_name)
    #         try:
    #             sub_type = m.lastgroup
    #         except AttributeError as e:
    #             sub_type = None
    #             logger.critical(f"No procedure type found or procedure type found!: {e}")
    #         return sub_type

    #     match filename:
    #         case Path():
    #             submission_type = st_from_path(filepath=filename)
    #         case str():
    #             submission_type = st_from_str(file_name=filename)
    #         case _:
    #             raise TypeError(f"Unsupported filename type: {type(filename)}.")
        
    #     submission_type = submission_type.replace("_", " ")
    #     return submission_type

    # @classmethod
    # def retrieve_rsl_number(cls, filename: str | Path, regex: re.Pattern | None = None):
    #     """
    #     Uses regex to retrieve the plate number and procedure type from an input string

    #     Args:
    #         regex (str): string to construct pattern
    #         filename (str): string to be parsed
    #     """
    #     from backend.db.models import SubmissionType
    #     if regex is None:
    #         regex = SubmissionType.regexes
    #     match filename:
    #         case Path():
    #             m = regex.search(filename.stem)
    #         case str():
    #             m = regex.search(filename)
    #         case _:
    #             m = None
    #     if m is not None:
    #         try:
    #             parsed_name = m.group().upper().strip(".")
    #         except AttributeError:
    #             parsed_name = None
    #     else:
    #         parsed_name = None
    #     return parsed_name

    @classmethod
    def construct_new_plate_name(cls, data: dict) -> str:
        """
        Make a brand-new plate name from procedure data.

        Args:
            data (dict): incoming procedure data

        Returns:
            str: Output filename
        """
        from backend.db.models import Run
        submitted_date = data.get("submitted_date", None)
        match submitted_date:
            case dict():
                data['submitted_date'] = submitted_date.get("value", datetime.now())
                return cls.construct_new_plate_name(data=data)
            case str():
                submitted_date = parse(submitted_date)
            case date():
                submitted_date = datetime.combine(submitted_date, datetime.min.time())
            case datetime():
                submitted_date = submitted_date
            case _:
                try:
                    submitted_date = re.search(r"\d{4}(_|-)?\d{2}(_|-)?\d{2}", data['name'])
                    submitted_date = parse(submitted_date.group())
                except (AttributeError, KeyError):
                    submitted_date = datetime.now()
        previous = Run.query(start_date=submitted_date, end_date=submitted_date, submissiontype_name=data['submissiontype'])
        plate_number = len(previous) + 1
        return f"RSL-{data['abbreviation']}-{submitted_date.year}{str(submitted_date.month).zfill(2)}{str(submitted_date.day).zfill(2)}-{plate_number}"

    @classmethod
    def construct_export_name(cls, template: str | Template, **kwargs) -> str:
        """
        Make export file name from jinja template.

        Args:
            template (jinja2.Template): Template stored in BasicRun

        Returns:
            str: output file name.
        """
        output = {}
        for k, v in kwargs.items():
            if isinstance(v, dict):
                v = v.get("value", None) or v.get("name", None)
            if v is not None:
                output[k] = v
            else: continue
        environment = jinja_template_loading()
        template = environment.from_string(source=template)
        return template.render(**output)

    # def calculate_repeat(self) -> str:
    #     """
    #     Determines what repeat number this plate is.

    #     Returns:
    #         str: Repeat number.
    #     """
    #     regex = re.compile(r"-\d(?P<repeat>R\d)")
    #     m = regex.search(self.parsed_name)
    #     if m is not None:
    #         return m.group("repeat")
    #     else:
    #         return ""


from .pydant import (
    PydRun, PydContact, PydClientLab, PydSample, PydReagent, PydReagentRole, PydEquipment, PydEquipmentRole, PydTips,
    PydProcess, PydClientSubmission, PydProcedure, PydResults, PydReagentLot
)
