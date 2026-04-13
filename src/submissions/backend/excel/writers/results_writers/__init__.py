"""
Default results writers.
"""
from openpyxl import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from backend.db.models import ProcedureType
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.validators.pydant import PydProcedureSampleAssociation

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoWriter(DefaultKEYVALUEWriter):

    exclude = ["excluded", "sampleprocedureassocation", "img", "sample"]

    def __init__(self, pydant_obj, proceduretype: ProcedureType, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        # self.procedure = self.pydant_obj.name
        self.sheet = f"{proceduretype.name[:10]} {pydant_obj.resultstype[:10]}"
        # print(self.pydant_obj)

    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class DefaultResultsSampleWriter(DefaultTABLEWriter):

    # def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
    #     super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
    #     self.proceduretype = proceduretype
    #     self.worksheet = None

    exclude = ["excluded", "name", "procedure", "sample", "sampleprocedureassociation", "result", 
               "image", 'img', "plate_barcode", "resultstype", "reagent_lot#"]
    header_order = ["sample_id"]

    def __init__(self, pydant_obj, proceduretype: ProcedureType, resultstype: str, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        assert self.proceduretype is not None, "Procedure type must be provided to ResultsSampleWriter"
        self.sheet = f"{proceduretype.name[:10]} {resultstype[:10]}"

    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook

    

from .qubit_results_writer import QubitInfoWriter, QubitSampleWriter
from .diomni_pcr_results_writer import DiomniPCRInfoWriter, DiomniPCRSampleWriter
