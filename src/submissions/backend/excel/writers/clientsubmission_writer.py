"""
Module for ClientSubmission writing
"""
from __future__ import annotations
import logging, sys
from pprint import pformat
from openpyxl.workbook import Workbook
from openpyxl.styles import Alignment, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from typing import TYPE_CHECKING
from . import DefaultKEYVALUEWriter, DefaultTABLEWriter
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmissionInfoWriter(DefaultKEYVALUEWriter):
    exclude = ["name", "id", "clientlab", "filepath", "comments", "sample", 
               "excluded", "run", "clientsubmissionsampleassociation", "expanded"]

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)

    def prewrite(self, worksheet: Worksheet, start_row: int) -> Worksheet:
        worksheet.cell(row=start_row, column=1, value="Submitter Info")
        worksheet.cell(row=start_row, column=1).alignment = Alignment(horizontal="center")
        worksheet.cell(row=start_row, column=1).fill = PatternFill(start_color='2DE733', end_color='2DE733', fill_type="solid")
        worksheet.cell(row=start_row, column=2).fill = PatternFill(start_color='2DE733', end_color='2DE733', fill_type="solid")
        return worksheet


class ClientSubmissionSampleWriter(DefaultTABLEWriter):


    exclude = ['id', 'enabled', 'procedure_rank', "name", "clientsubmission", "is_control", "rank", "sample"]
    header_order = ["submission_rank", "sample_id"]

    def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        self.pydant_obj = self.pad_submission_samples_to_length()
        workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row, *args, **kwargs)
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        worksheet = super().postwrite(worksheet)
        for row in worksheet.iter_rows(min_row=self.start_row, max_row=self.end_row):
            for cell in row:
                if cell.value in [0, "0", "None"]:
                    cell.value = ""
                cell.alignment = Alignment(horizontal="center")
        return worksheet
    
    def pad_submission_samples_to_length(self):
        from backend.validators.pydant import PydClientSubmissionSampleAssociation
        output_samples = []
        for iii in range(1, self.pydant_obj.max_sample_rank + 1):
            iterator = self.pydant_obj.sql_instance.clientsubmissionsampleassociation
            try:
                sample = next(item.to_pydantic() for item in iterator if item.submission_rank == iii)
            except StopIteration:
                sample = PydClientSubmissionSampleAssociation(sample="", clientsubmission=self.pydant_obj.name, submission_rank=iii)
            output_samples.append(sample)
        return sorted(output_samples, key=lambda x: x.submission_rank)
