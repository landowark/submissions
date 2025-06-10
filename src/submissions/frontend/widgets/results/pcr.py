"""

"""
import logging
from pathlib import Path
from backend.validators import PydResults
from backend.db.models import Procedure, Results
from backend.excel.parsers.pcr_parser import PCRSampleParser, PCRInfoParser
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent
from . import DefaultResults

logger = logging.getLogger(f"submissions.{__name__}")

class PCR(DefaultResults):

    def __init__(self, procedure: Procedure, parent, fname:Path|str|None=None):
        logger.debug(f"FName before correction: {fname}")
        self.procedure = procedure
        if not fname:
            self.fname = select_open_file(file_extension="xlsx", obj=get_application_from_parent(parent))
        elif isinstance(fname, str):
            self.fname = Path(fname)
        logger.debug(f"FName after correction: {fname}")
        self.info_parser = PCRInfoParser(filepath=self.fname, procedure=self.procedure)
        self.sample_parser = PCRSampleParser(filepath=self.fname, procedure=self.procedure)
        self.build_procedure()
        self.build_samples()

    def build_procedure(self):
        procedure_info = self.info_parser.to_pydantic()
        procedure_sql = procedure_info.to_sql()
        procedure_sql.save()

    def build_samples(self):
        samples = self.sample_parser.to_pydantic()
        for sample in samples:
            sql = sample.to_sql()
            sql.save()
