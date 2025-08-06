from __future__ import annotations
import logging
from pprint import pformat
from openpyxl.workbook import Workbook
from openpyxl.styles import Alignment
from openpyxl.worksheet.worksheet import Worksheet
from typing import TYPE_CHECKING
from . import DefaultKEYVALUEWriter, DefaultTABLEWriter
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmissionInfoWriter(DefaultKEYVALUEWriter):
    exclude = ["name", "id", "clientlab", "filepath"]

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        logger.debug(f"{self.__class__.__name__} recruited!")

    def prewrite(self, worksheet: Worksheet, start_row: int) -> Worksheet:
        # worksheet.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=4)
        worksheet.cell(row=start_row, column=1, value="Submitter Info")
        worksheet.cell(row=start_row, column=1).alignment = Alignment(horizontal="center")
        return worksheet


class ClientSubmissionSampleWriter(DefaultTABLEWriter):


    exclude = ['id', 'enabled', 'procedure_rank', "name"]
    header_order = ["submission_rank", "sample_id"]

    def __init__(self, pydant_obj, proceduretype: "ProcedureType" | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        self.pydant_obj = self.pad_samples_to_length(row_count=self.pydant_obj.max_sample_rank)#, column_names=header_list)
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
