"""
Default results writers.
"""
from openpyxl import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from backend.db.models import ProcedureType
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoWriter(DefaultKEYVALUEWriter):

    pass


class DefaultResultsSampleWriter(DefaultTABLEWriter):

    def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        
        associations = getattr(pydant_obj, f"{pydant_obj.__class__.__name__.lower()}sampleassociation")
        associations = [item for item in associations if item.results]
        output = []
        for assoc in associations:
            for result in assoc.results:
                result.result.update({"sample_id": assoc.sample.sample_id})
            output.append(result.result)
        self.pydant_obj = output

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        try:
            self.worksheet = workbook[f"{self.proceduretype.name[:15]} Results"]
        except KeyError:
            self.worksheet = workbook.create_sheet(f"{self.proceduretype.name[:15]} Results")
        return workbook


from .qubit_results_writer import QubitInfoWriter, QubitSampleWriter
from .diomni_pcr_results_writer import DiomniPCRInfoWriter, DiomniPCRSampleWriter
