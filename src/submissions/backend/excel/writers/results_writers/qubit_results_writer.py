"""
Writers for PCR results from Design and Analysis Software
"""
from __future__ import annotations
import logging
from pprint import pformat
from typing import Generator, TYPE_CHECKING
from openpyxl import Workbook
from openpyxl.styles import Alignment
from . import DefaultResultsInfoWriter, DefaultResultsSampleWriter
from tools import flatten_list
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")

class QubitInfoWriter(DefaultResultsInfoWriter):

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        return workbook


class QubitSampleWriter(DefaultResultsSampleWriter):

    def write_to_workbook(self, workbook: Workbook, *args, **kwargs) -> Workbook:
        try:
            self.worksheet = workbook[f"{self.proceduretype.name[:15]} Results"]
        except KeyError:
            self.worksheet = workbook.create_sheet(f"{self.proceduretype.name[:15]} Results")
            # worksheet = workbook[f"{self.proceduretype.name[:15]} Results"]
        header_row = self.proceduretype.allowed_result_methods['Qubit']['sample']['start_row']
        for iii, header in enumerate(self.column_headers, start=1):
            logger.debug(f"Row: {header_row}, column: {iii}")
            self.worksheet.cell(row=header_row, column=iii, value=header.replace("_", " ").title())
        logger.debug(f"Column headers: {self.column_headers}")
        for iii, result in enumerate(self.pydant_obj, start = 1):
            row = header_row + iii
            for k, v in result.result.items():
                try:
                    column = next((col[0].column for col in self.worksheet.iter_cols() if col[0].value == k.replace("_", " ").title()))
                except StopIteration:
                    print(f"fail for {k.replace('_', ' ').title()}")
                    continue
                logger.debug(f"Writing to row: {row}, column {column}")
                cell = self.worksheet.cell(row=row, column=column)
                cell.value = v
                cell.alignment = Alignment(horizontal='left')
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    @property
    def column_headers(self):
        output = []
        for result in self.pydant_obj:
            for k, value in result.result.items():
                output.append(k)
        return sorted(list(set(output)))



