"""

"""
from pathlib import Path
from backend.validators import PydResults
from backend.db.models import Procedure, Results
from backend.excel.parsers.pcr_parser import PCRSampleParser, PCRInfoParser
from frontend.widgets.functions import select_open_file
from . import DefaultResults

class PCR(DefaultResults):

    def __init__(self, procedure: Procedure, fname:Path|str|None=None):
        self.procedure = procedure
        if not fname:
            self.fname = select_open_file(file_extension="xlsx")
        elif isinstance(fname, str):
            self.fname = Path(fname)
        self.info_parser = PCRInfoParser(filepath=fname)
        self.sample_parser = PCRSampleParser(filepath=fname)

    def build_procedure(self):
        results = PydResults(parent=self.procedure)
        results.results =


