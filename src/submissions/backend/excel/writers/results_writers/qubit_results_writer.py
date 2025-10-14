"""
Writers for PCR results from Qubit device
"""
from __future__ import annotations
import logging
from pprint import pformat
from openpyxl import Workbook
from openpyxl.styles import Alignment
from . import DefaultResultsInfoWriter, DefaultResultsSampleWriter


logger = logging.getLogger(f"submissions.{__name__}")

class QubitInfoWriter(DefaultResultsInfoWriter):

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        return workbook


class QubitSampleWriter(DefaultResultsSampleWriter):

    def write_to_workbook(self, workbook: Workbook, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, *args, **kwargs)
        header_row = self.proceduretype.allowed_result_methods['Qubit']['sample']['header_row']
        for iii, header in enumerate(self.column_headers, start=1):
            self.worksheet.cell(row=header_row, column=iii, value=header.replace("_", " ").title())
        for iii, result in enumerate(self.pydant_obj, start = 1):
            row = header_row + iii
            for k, v in result.result.items():
                try:
                    column = next((col[0].column for col in self.worksheet.iter_cols() if col[0].value == k.replace("_", " ").title()))
                except StopIteration:
                    logger.error(f"fail for {k.replace('_', ' ').title()}")
                    continue
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
