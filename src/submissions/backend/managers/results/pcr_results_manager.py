"""

"""
from __future__ import annotations
import logging
from io import BytesIO
from pathlib import Path
from typing import Tuple, List, TYPE_CHECKING

from openpyxl.reader.excel import load_workbook

from backend.db.models import Procedure
from backend.excel.parsers.results_parsers.pcr_results_parser import PCRSampleParser, PCRInfoParser
from backend.excel.writers.results_writers.pcr_results_writer import PCRInfoWriter, PCRSampleWriter
from . import DefaultResultsManager
if TYPE_CHECKING:
    from backend.validators.pydant import PydResults

logger = logging.getLogger(f"submissions.{__name__}")

class PCRManager(DefaultResultsManager):

    def __init__(self, procedure: Procedure, parent, fname: Path | str | None = None):
        super().__init__(procedure=procedure, parent=parent, fname=fname)
        self.parse()

    def parse(self):
        self.info_parser = PCRInfoParser(filepath=self.fname, procedure=self.procedure)
        self.sample_parser = PCRSampleParser(filepath=self.fname, procedure=self.procedure)

    def write(self):
        workbook = load_workbook(BytesIO(self.procedure.proceduretype.template_file))
        self.info_writer = PCRInfoWriter(pydant_obj=self.procedure.to_pydantic(), proceduretype=self.procedure.proceduretype)
        workbook = self.info_writer.write_to_workbook(workbook)
        self.sample_writer = PCRSampleWriter(pydant_obj=self.procedure.to_pydantic(), proceduretype=self.procedure.proceduretype)






