"""
Module for manager of ClientSubmission object
"""
from __future__ import annotations
import logging, sys
from typing import TYPE_CHECKING
from pathlib import Path
from openpyxl.workbook import Workbook
from backend.validators import ClientSubmissionNamer
from backend.managers import DefaultManager
from backend.excel.parsers.clientsubmission_parser import ClientSubmissionInfoParser, ClientSubmissionSampleParser
from backend.excel.writers.clientsubmission_writer import ClientSubmissionInfoWriter, ClientSubmissionSampleWriter
if TYPE_CHECKING:
    from backend.db.models import SubmissionType, ClientSubmission
    from backend.validators.pydant import PydClientSubmission

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultClientSubmissionManager(DefaultManager):

    def __init__(self, parent, submissiontype: SubmissionType | str | None = None,
                 input_object: Path | str | ClientSubmission | PydClientSubmission | None = None):
        from backend.db.models import SubmissionType, ClientSubmission
        from backend.validators.pydant import PydClientSubmission
        match input_object:
            case str() | Path():
                self.namer = ClientSubmissionNamer(filepath=input_object)
            case x if isinstance(input_object, ClientSubmission):
                self.namer = input_object
            case x if isinstance(input_object, PydClientSubmission):
                self.namer = input_object
            case _:
                logger.warning(f"Skipping submission type")
        if submissiontype is None:
            try:
                submissiontype = self.namer.submissiontype
            except Exception as e:
                raise TypeError(f"Unknown type for submissiontype of {type(submissiontype)}")
        match submissiontype:
            case str():
                submissiontype = SubmissionType.query(name=submissiontype)
            case dict():
                q = submissiontype.get("name") or submissiontype.get("value")
                submissiontype = SubmissionType.query(name=q)
            case SubmissionType():
                pass
            case _:
                # NOTE: if unmatched, try to get from input_object
                pass
        self.submissiontype = submissiontype
        super().__init__(parent=parent, input_object=input_object)
        for procedure in self.find_procedures():
            proceduretype = procedure.strip(" Quality")

    def find_procedures(self):
        # At this point strings should be parsed into path
        from backend.db.models import ProcedureType
        if not isinstance(self.input_object, Path):
            return []
        else:
            ptypes = [item.name for item in ProcedureType.query()]
            actuals = [sheet for sheet in self.info_parser.workbook.sheetnames if sheet.removesuffix(" Quality") in ptypes]
            return actuals
                
    def to_pydantic(self):
        self.info_parser = ClientSubmissionInfoParser(filepath=self.input_object, submissiontype=self.submissiontype)
        
        # NOTE: Alter sheets List[dict] so that the start_row sent to sample parser is the end row of the info parser
        sheets = self.ratchet_start_row()
        self.sample_parser = ClientSubmissionSampleParser(filepath=self.input_object,
                                                          submissiontype=self.submissiontype,
                                                          sheets=sheets)
        # if self.info_parser._pyd_object is not None:
        self.clientsubmission = self.info_parser.to_pydantic()
        # else:
        # self.clientsubmission = None
        try:
            self.clientsubmission.sample = self.sample_parser.to_pydantic()
        except AttributeError:
            pass
        return self.clientsubmission

    def write(self, workbook: Workbook) -> Workbook:
        self.info_writer = ClientSubmissionInfoWriter(pydant_obj=self.pyd)
        assert isinstance(self.info_writer, ClientSubmissionInfoWriter)
        workbook = self.info_writer.write_to_workbook(workbook)
        self.sample_writer = ClientSubmissionSampleWriter(pydant_obj=self.pyd)
        workbook = self.sample_writer.write_to_workbook(workbook, start_row=self.info_writer.worksheet.max_row + 1)
        return workbook
