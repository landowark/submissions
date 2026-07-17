"""
Default results writers.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from openpyxl import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter


class DefaultResultsInfoWriter(DefaultKEYVALUEWriter):

    exclude = ["excluded", "sampleprocedureassocation", "img", "sample"]

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.fill_dictionary = pydant_obj.result
        self.write_sheet = pydant_obj.write_sheet_name
        
    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.write_sheet, start_row=start_row)
        return workbook


class DefaultResultsSampleWriter(DefaultTABLEWriter):

    exclude = ["excluded", "name", "procedure", "sample", "sampleprocedureassociation", "result", 
               "image", 'img', "plate_barcode", "resultstype", "reagent_lot#", "is_sample"]
    header_order = ["sample_id"]

    def __init__(self, pydant_obj, proceduretype, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        if isinstance(self.pydant_obj, list):
            self.write_sheet = self.pydant_obj[0].write_sheet_name
        else:
            self.write_sheet = self.pydant_obj.write_sheet_name

    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        logger.debug(f"Pyd_obj: {pformat(self.pydant_obj)}")
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.write_sheet, start_row=start_row)
        return workbook


from .qubit_results_writer import *
from .diomni_pcr_results_writer import *

__all__ = ["DefaultResultsInfoWriter", "DefaultResultsSampleWriter", "DiomniPCRInfoWriter", "DiomniPCRSampleWriter", "QubitInfoWriter", "QubitSampleWriter"]
