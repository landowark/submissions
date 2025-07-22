"""

"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Tuple, List, TYPE_CHECKING
from backend.db.models import Procedure
from backend.excel.parsers.results_parsers.pcr_results_parser import PCRSampleParser, PCRInfoParser
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





