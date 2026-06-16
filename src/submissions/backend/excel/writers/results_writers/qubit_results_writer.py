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

    def write_to_workbook(self, workbook: Workbook, *args, **kwargs) -> Workbook:
        return workbook


class QubitSampleWriter(DefaultResultsSampleWriter):

    
    header_order = ["sample_id", "original_sample_conc."]

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None, start_row: int = 1, *args, **kwargs) -> Workbook:
        start_row -= 1
        workbook = super().write_to_workbook(workbook, sheet, start_row, *args, **kwargs)
        return workbook

    
__all__ = ["QubitInfoWriter", "QubitSampleWriter"]