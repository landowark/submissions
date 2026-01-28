"""

"""
from __future__ import annotations
import logging
from pathlib import Path
from backend.db.models import Procedure
from backend.excel.parsers.results_parsers.qubit_results_parser import QubitSampleParser, QubitInfoParser
# from backend.excel.writers.results_writers.qubit_results_writer import QubitInfoWriter, QubitSampleWriter
from . import DefaultResultsManager


logger = logging.getLogger(f"submissions.{__name__}")

class QubitManager(DefaultResultsManager):

    def __init__(self, procedure: Procedure, parent, fname: Path | str | None = None):
        super().__init__(procedure=procedure, parent=parent, fname=fname, extension="csv")
        self.parse()

    def parse(self):
        self.info_parser = QubitInfoParser(filepath=self.fname, procedure=self.procedure)
        self.sample_parser = QubitSampleParser(filepath=self.fname, procedure=self.procedure, start_row=self.info_parser.end_row)
