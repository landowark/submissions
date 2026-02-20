"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
import logging
from pathlib import Path
from backend.db.models import Procedure
from backend.excel.parsers.results_parsers.diomni_pcr_results_parser import DiomniPCRSampleParser, DiomniPCRInfoParser
# from backend.excel.writers.results_writers.pcr_results_writer import PCRInfoWriter, PCRSampleWriter
from . import DefaultResultsManager

logger = logging.getLogger(f"submissions.{__name__}")

class DiomniPCRManager(DefaultResultsManager):

    def __init__(self, procedure: Procedure, parent, fname: Path | str | None = None):
        super().__init__(procedure=procedure, parent=parent, fname=fname)
        self.parse()

    def parse(self):
        self.info_parser = DiomniPCRInfoParser(filepath=self.fname, procedure=self.procedure)
        self.sample_parser = DiomniPCRSampleParser(filepath=self.fname, procedure=self.procedure,
                                             start_row=self.info_parser.end_row, date_analyzed=self.info_parser.date_analyzed)
