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
        self.sheet = f"{proceduretype.name[:20]} Results"
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

    exclude = ["excluded", "name", "procedure", "sample", "sampleprocedureassociation", "result"]
    header_order = ["sample_id"]

    def __init__(self, pydant_obj, proceduretype: ProcedureType, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        # self.procedure = self.pydant_obj.name
        self.sheet = f"{proceduretype.name[:20]} Results"
        # print(self.pydant_obj)

    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        print(f"Starting row: {start_row}")
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook

    # def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
    #     # NOTE: pydant_obj should be a list of all sample results
    #     super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
    #     # print(pydant_obj.__dict__)
    #     # associations = getattr(pydant_obj, f"{pydant_obj.__class__.__name__.lower()}sampleassociation")
    #     # associations = [item for item in associations if item.results]
    #     output = []
    #     # for assoc in associations:
    #     pydant_obj.result.update({"sample_id": result.sample.sample_id})
    #     output.append(result.result)
    #     self.pydant_obj = output

    # def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
    #                       start_row: int | None = None, *args, **kwargs) -> Workbook:
    #     try:
    #         self.worksheet = workbook[f"{self.proceduretype.name[:20]} Results"]
    #     except KeyError:
    #         self.worksheet = workbook.create_sheet(f"{self.proceduretype.name[:20]} Results")
    #     workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet,
    #                       start_row=None, *args, **kwargs)
    #     return workbook


from .qubit_results_writer import QubitInfoWriter, QubitSampleWriter
from .diomni_pcr_results_writer import DiomniPCRInfoWriter, DiomniPCRSampleWriter
