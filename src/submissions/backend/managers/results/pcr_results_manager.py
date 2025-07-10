"""

"""
import logging
from pathlib import Path
from backend.db.models import Procedure
from backend.excel.parsers.results_parsers.pcr_results_parser import PCRSampleParser, PCRInfoParser
from . import DefaultResultsManager

logger = logging.getLogger(f"submissions.{__name__}")

class PCRManager(DefaultResultsManager):

    def __init__(self, procedure: Procedure, parent, fname:Path|str|None=None):
        super().__init__(procedure=procedure, parent=parent, fname=fname)
        self.info_parser = PCRInfoParser(filepath=self.fname, procedure=self.procedure)
        self.sample_parser = PCRSampleParser(filepath=self.fname, procedure=self.procedure)
        self.build_info()
        self.build_samples()

    def build_info(self):
        procedure_info = self.info_parser.to_pydantic()
        procedure_info.results_type = self.__class__.__name__
        procedure_sql = procedure_info.to_sql()
        procedure_sql.save()

    def build_samples(self):
        samples = self.sample_parser.to_pydantic()
        for sample in samples:
            sample.results_type = self.__class__.__name__
            sql = sample.to_sql()
            sql.save()
