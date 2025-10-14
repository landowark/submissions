"""
Default results writers.
"""
from openpyxl import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from backend.db.models import ProcedureType
from tools import flatten_list


class DefaultResultsInfoWriter(DefaultKEYVALUEWriter):

    pass

class DefaultResultsSampleWriter(DefaultTABLEWriter):

    def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        self.pydant_obj = flatten_list([sample.results for sample in pydant_obj.sample])

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        try:
            self.worksheet = workbook[f"{self.proceduretype.name[:15]} Results"]
        except KeyError:
            self.worksheet = workbook.create_sheet(f"{self.proceduretype.name[:15]} Results")
        return workbook


from .qubit_results_writer import QubitInfoWriter, QubitSampleWriter
from .pcr_results_writer import PCRInfoWriter, PCRSampleWriter
