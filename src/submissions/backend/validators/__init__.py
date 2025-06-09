"""
Contains all validators
"""
import logging, re
import sys
from pathlib import Path
from openpyxl import load_workbook
from backend.db.models import Run, SubmissionType
from tools import jinja_template_loading
from jinja2 import Template
from dateutil.parser import parse
from datetime import datetime

logger = logging.getLogger(f"submissions.{__name__}")


class RSLNamer(object):
    """
    Object that will enforce proper formatting on RSL plate names.
    """

    def __init__(self, filename: str, submission_type: str | None = None, data: dict | None = None):
        # NOTE: Preferred method is path retrieval, but might also need validation for just string.
        filename = Path(filename) if Path(filename).exists() else filename
        self.submission_type = submission_type
        if not self.submission_type:
            self.submission_type = self.retrieve_submission_type(filename=filename)
        logger.info(f"got procedure type: {self.submission_type}")
        if self.submission_type:
            self.sub_object = BasicRun.find_polymorphic_subclass(polymorphic_identity=self.submission_type)
            self.parsed_name = self.retrieve_rsl_number(filename=filename, regex=self.sub_object.get_regex(
                submission_type=submission_type))
            if not data:
                data = dict(submission_type=self.submission_type)
            if "proceduretype" not in data.keys():
                data['proceduretype'] = self.submission_type
            self.parsed_name = self.sub_object.enforce_name(instr=self.parsed_name, data=data)
            logger.info(f"Parsed name: {self.parsed_name}")

    @classmethod
    def retrieve_submission_type(cls, filename: str | Path) -> str:
        """
        Gets procedure type from excel file properties or sheet names or regex pattern match or user input

        Args:
            filename (str | Path): filename

        Raises:
            TypeError: Raised if unsupported variable type for filename given.

        Returns:
            str: parsed procedure type
        """

        def st_from_path(filepath: Path) -> str:
            """
            Sub def to get proceduretype from a file path

            Args:
                filepath ():

            Returns:

            """
            if filepath.exists():
                wb = load_workbook(filepath)
                try:
                    # NOTE: Gets first category in the metadata.
                    categories = wb.properties.category.split(";")
                    submission_type = next(item.strip().title() for item in categories)
                except (StopIteration, AttributeError):
                    sts = {item.name: item.template_file_sheets for item in SubmissionType.query() if
                           item.template_file}
                    try:
                        submission_type = next(k.title() for k, v in sts.items() if wb.sheetnames == v)
                    except StopIteration:
                        # NOTE: On failure recurse using filepath as string for string method
                        submission_type = cls.retrieve_submission_type(filename=filepath.stem.__str__())
            else:
                submission_type = cls.retrieve_submission_type(filename=filepath.stem.__str__())
            return submission_type

        def st_from_str(file_name: str) -> str:
            if file_name.startswith("tmp"):
                return "Bacterial Culture"
            regex = BasicRun.regex
            m = regex.search(file_name)
            try:
                sub_type = m.lastgroup
            except AttributeError as e:
                sub_type = None
                logger.critical(f"No procedure type found or procedure type found!: {e}")
            return sub_type

        match filename:
            case Path():
                submission_type = st_from_path(filepath=filename)
            case str():
                submission_type = st_from_str(file_name=filename)
            case _:
                raise TypeError(f"Unsupported filename type: {type(filename)}.")
        try:
            check = submission_type is None
        except UnboundLocalError:
            check = True
        if check:
            if "pytest" in sys.modules:
                raise ValueError("Submission Type came back as None.")
            from frontend.widgets import ObjectSelector
            dlg = ObjectSelector(title="Couldn't parse procedure type.",
                                 message="Please select procedure type from list below.",
                                 obj_type=SubmissionType)
            if dlg.exec():
                submission_type = dlg.parse_form()
        submission_type = submission_type.replace("_", " ")
        return submission_type

    @classmethod
    def retrieve_rsl_number(cls, filename: str | Path, regex: re.Pattern | None = None):
        """
        Uses regex to retrieve the plate number and procedure type from an input string

        Args:
            regex (str): string to construct pattern
            filename (str): string to be parsed
        """
        if regex is None:
            regex = BasicRun.regex
        match filename:
            case Path():
                m = regex.search(filename.stem)
            case str():
                m = regex.search(filename)
            case _:
                m = None
        if m is not None:
            try:
                parsed_name = m.group().upper().strip(".")
            except AttributeError:
                parsed_name = None
        else:
            parsed_name = None
        return parsed_name

    @classmethod
    def construct_new_plate_name(cls, data: dict) -> str:
        """
        Make a brand-new plate name from procedure data.

        Args:
            data (dict): incoming procedure data

        Returns:
            str: Output filename
        """
        logger.debug(data)
        if "submitted_date" in data.keys():
            if isinstance(data['submitted_date'], dict):
                if data['submitted_date']['value'] is not None:
                    today = data['submitted_date']['value']
                else:
                    today = datetime.now()
            else:
                today = data['submitted_date']
        else:
            try:
                today = re.search(r"\d{4}(_|-)?\d{2}(_|-)?\d{2}", data['name'])
                today = parse(today.group())
            except (AttributeError, KeyError):
                today = datetime.now()
        if isinstance(today, str):
            today = datetime.strptime(today, "%Y-%m-%d")
        if "name" in data.keys():
            plate_number = data['name'].split("-")[-1][0]
        else:
            previous = Run.query(start_date=today, end_date=today, submissiontype=data['submissiontype'])
            plate_number = len(previous) + 1
        return f"RSL-{data['abbreviation']}-{today.year}{str(today.month).zfill(2)}{str(today.day).zfill(2)}-{plate_number}"

    @classmethod
    def construct_export_name(cls, template: Template, **kwargs) -> str:
        """
        Make export file name from jinja template. (currently unused)

        Args:
            template (jinja2.Template): Template stored in BasicRun

        Returns:
            str: output file name.
        """
        environment = jinja_template_loading()
        template = environment.from_string(template)
        return template.render(**kwargs)

    def calculate_repeat(self) -> str:
        """
        Determines what repeat number this plate is.

        Returns:
            str: Repeat number.
        """
        regex = re.compile(r"-\d(?P<repeat>R\d)")
        m = regex.search(self.parsed_name)
        if m is not None:
            return m.group("repeat")
        else:
            return ""


from .pydant import PydSubmission, PydKitType, PydContact, PydOrganization, PydSample, PydReagent, PydReagentRole, \
    PydEquipment, PydEquipmentRole, PydTips, PydProcess, PydElastic, PydClientSubmission, PydProcedure, PydResults
