"""

"""
from __future__ import annotations
import logging
from pathlib import Path
from string import ascii_lowercase
from typing import Generator

from openpyxl.reader.excel import load_workbook

from tools import row_keys
# from backend.db.models import SubmissionType
from . import DefaultKEYVALUEParser, DefaultTABLEParser
from backend.managers import procedures as procedure_managers

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionTyperMixin(object):

    @classmethod
    def retrieve_submissiontype(cls, filepath: Path):
        # NOTE: Attempt 1, get from form properties:
        sub_type = cls.get_subtype_from_properties(filepath=filepath)
        if not sub_type:
            # NOTE: Attempt 2, get by opening file and using default parser
            logger.warning(
                f"Getting submissiontype from file properties failed, falling back on preparse.\nDepending on excel structure this might yield an incorrect submissiontype")
            sub_type = cls.get_subtype_from_preparse(filepath=filepath)
        if not sub_type:
            logger.warning(
                f"Getting submissiontype from preparse failed, falling back on filename regex.\nDepending on excel structure this might yield an incorrect submissiontype")
            sub_type = cls.get_subtype_from_regex(filepath=filepath)
        return sub_type

    @classmethod
    def get_subtype_from_regex(cls, filepath: Path):
        from backend.db.models import SubmissionType
        regex = SubmissionType.regex
        m = regex.search(filepath.__str__())
        try:
            sub_type = m.lastgroup
        except AttributeError as e:
            sub_type = None
            logger.critical(f"No procedure type found or procedure type found!: {e}")
        return sub_type

    @classmethod
    def get_subtype_from_preparse(cls, filepath: Path):
        from backend.db.models import SubmissionType
        parser = ClientSubmissionInfoParser(filepath)
        sub_type = next((value for k, value in parser.parsed_info if k == "submissiontype"), None)
        sub_type = SubmissionType.query(name=sub_type)
        if isinstance(sub_type, list):
            sub_type = None
        return sub_type

    @classmethod
    def get_subtype_from_properties(cls, filepath: Path):
        from backend.db.models import SubmissionType
        wb = load_workbook(filepath)
        # NOTE: Gets first category in the metadata.
        categories = wb.properties.category.split(";")
        sub_type = next((item.strip().title() for item in categories), None)
        sub_type = SubmissionType.query(name=sub_type)
        if isinstance(sub_type, list):
            sub_type = None
        return sub_type


class ClientSubmissionInfoParser(DefaultKEYVALUEParser, SubmissionTyperMixin):
    """
    Object for retrieving submitter info from "sample list" sheet
    """

    default_range_dict = [dict(
        start_row=2,
        end_row=18,
        key_column=1,
        value_column=2,
        sheet="Sample List"
    )]

    def __init__(self, filepath: Path | str, *args, **kwargs):
        from frontend.widgets.pop_ups import QuestionAsker
        self.submissiontype = self.retrieve_submissiontype(filepath=filepath)
        if "range_dict" not in kwargs:
            kwargs['range_dict'] = self.submissiontype.info_map
        super().__init__(filepath=filepath, **kwargs)
        allowed_procedure_types = [item.name for item in self.submissiontype.proceduretype]
        for name in allowed_procedure_types:
            if name in self.workbook.sheetnames:
                # TODO: check if run with name already exists
                add_run = QuestionAsker(title="Add Run?", message="We've detected a sheet corresponding to an associated procedure type.\nWould you like to add a new run?")
                if add_run.accepted:


                # NOTE: recruit parser.
                    try:
                        manager = getattr(procedure_managers, name)
                    except AttributeError:
                        manager = procedure_managers.DefaultManager
                    self.manager = manager(proceduretype=name)
                pass


class ClientSubmissionSampleParser(DefaultTABLEParser, SubmissionTyperMixin):
    """
    Object for retrieving submitter samples from "sample list" sheet
    """

    default_range_dict = [dict(
        header_row=20,
        end_row=116,
        sheet="Sample List"
    )]

    def __init__(self, filepath: Path | str, *args, **kwargs):
        self.submissiontype = self.retrieve_submissiontype(filepath=filepath)
        if "range_dict" not in kwargs:
            kwargs['range_dict'] = self.submissiontype.sample_map
        super().__init__(filepath=filepath, **kwargs)

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        output = super().parsed_info
        for ii, sample in enumerate(output):
            if isinstance(sample["row"], str) and sample["row"].lower() in ascii_lowercase[0:8]:
                try:
                    sample["row"] = row_keys[sample["row"]]
                except KeyError:
                    pass
            sample['submission_rank'] = ii + 1
            yield sample

    def to_pydantic(self):
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample['sample_id']]
