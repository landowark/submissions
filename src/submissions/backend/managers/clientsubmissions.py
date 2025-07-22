from __future__ import annotations
import logging
from io import BytesIO
from typing import TYPE_CHECKING
from pathlib import Path

from openpyxl.reader.excel import load_workbook
from openpyxl.workbook import Workbook
from backend.validators import RSLNamer
from backend.managers import DefaultManager
from backend.excel.parsers.clientsubmission_parser import ClientSubmissionInfoParser, ClientSubmissionSampleParser
from backend.excel.writers.clientsubmission_writer import ClientSubmissionInfoWriter, ClientSubmissionSampleWriter

if TYPE_CHECKING:
    from backend.db.models import SubmissionType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultClientSubmissionManager(DefaultManager):

    def __init__(self, parent, submissiontype: "SubmissionType" | str | None = None,
                 input_object: Path | str | None = None):
        from backend.db.models import SubmissionType
        match input_object:
            case str() | Path():
                submissiontype = RSLNamer.retrieve_submission_type(input_object)
            case _:
                logger.warning(f"Skipping submission type")
        match submissiontype:
            case str():
                submissiontype = SubmissionType.query(name=submissiontype)
            case dict():
                submissiontype = SubmissionType.query(name=submissiontype['name'])
            case SubmissionType():
                pass
            case _:
                raise TypeError(f"Unknown type for submissiontype of {type(submissiontype)}")
        self.submissiontype = submissiontype
        super().__init__(parent=parent, input_object=input_object)

    def parse(self):
        self.info_parser = ClientSubmissionInfoParser(filepath=self.input_object, submissiontype=self.submissiontype)
        self.sample_parser = ClientSubmissionSampleParser(filepath=self.input_object,
                                                          submissiontype=self.submissiontype)
        self.to_pydantic()
        return self.clientsubmission

    def to_pydantic(self):
        self.clientsubmission = self.info_parser.to_pydantic()
        self.clientsubmission.sample = self.sample_parser.to_pydantic()

    def write(self):
        workbook: Workbook = load_workbook(BytesIO(self.submissiontype.template_file))
        self.info_writer = ClientSubmissionInfoWriter(pydant_obj=self.pyd)
        assert isinstance(self.info_writer, ClientSubmissionInfoWriter)
        logger.debug("Attempting write.")
        workbook = self.info_writer.write_to_workbook(workbook)
        self.sample_writer = ClientSubmissionSampleWriter(pydant_obj=self.pyd)
        workbook = self.sample_writer.write_to_workbook(workbook)
        # workbook.save(output_path)
        return workbook