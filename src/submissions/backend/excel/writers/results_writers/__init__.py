"""
Default results writers.
"""
from pprint import pformat
from openpyxl import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
import logging


logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoWriter(DefaultKEYVALUEWriter):

    exclude = ["excluded", "sampleprocedureassocation", "img", "sample"]

    def __init__(self, pydant_obj, proceduretype, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.fill_dictionary = pydant_obj.result
        self.sheet = f"{proceduretype.name[:10]} {pydant_obj.resultstype[:10]}"
        
    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class DefaultResultsSampleWriter(DefaultTABLEWriter):

    exclude = ["excluded", "name", "procedure", "sample", "sampleprocedureassociation", "result", 
               "image", 'img', "plate_barcode", "resultstype", "reagent_lot#", "is_sample"]
    header_order = ["sample_id"]

    def __init__(self, pydant_obj, proceduretype, resultstype: str, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        assert self.proceduretype is not None, "Procedure type must be provided to ResultsSampleWriter"
        self.sheet = f"{proceduretype.name[:10]} {resultstype[:10]}"

    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        logger.debug(f"Pyd_obj: {pformat(self.pydant_obj)}")
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


from .qubit_results_writer import *
from .diomni_pcr_results_writer import *

__all__ = ["DefaultResultsInfoWriter", "DefaultResultsSampleWriter", "DiomniPCRInfoWriter", "DiomniPCRSampleWriter", "QubitInfoWriter", "QubitSampleWriter"]
