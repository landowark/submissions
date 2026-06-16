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
        match submissiontype:
            case str():
                if submissiontype in ["", "None"]:
                    self.submissiontype = self.retrieve_submissiontype()    
                else:
                    self.submissiontype = SubmissionType.query(name=submissiontype)
            case SubmissionType():
                self.submissiontype = submissiontype
            case _:
                logger.warning(f"Unrecognised submissiontype type {type(submissiontype)}, falling back to retrieval.")
                self.submissiontype = self.retrieve_submissiontype()

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

    def __init__(self, submission_type: str | SubmissionType | dict):
        from backend.db.models import SubmissionType
        # NOTE: Preferred method is path retrieval, but might also need validation for just string.
        match submission_type:
            case str():
                self.sub_object = SubmissionType.query(name=submission_type, limit=1)
                self.submission_type = submission_type
            case SourcedField():
                self.sub_object = SubmissionType.query(name=submission_type.value, limit=1)
                self.submission_type = submission_type.value
            case dict():
                self.sub_object = SubmissionType.query(name=submission_type['value'], limit=1)
                self.submission_type = submission_type['value']
            case SubmissionType():
                self.sub_object = submission_type
                self.submission_type = submission_type.name
            case _:
                raise TypeError(f"Unmatched type {type(submission_type)} for submission_type")
        
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
    

from .pydant import *
