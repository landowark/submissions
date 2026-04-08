"""

"""
from __future__ import annotations
import logging
from pathlib import Path
from backend.db.models import Procedure
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from tools import get_application_from_parent
from frontend.widgets.functions import select_open_file
from backend.excel.parsers.results_parsers.qubit_results_parser import QubitSampleParser, QubitInfoParser
# from backend.excel.writers.results_writers.qubit_results_writer import QubitInfoWriter, QubitSampleWriter
from . import DefaultResultsManager


logger = logging.getLogger(f"submissions.{__name__}")

class QubitManager(DefaultResultsManager):

    def __init__(self, procedure: Procedure, parent, input_object: Path | str | Workbook | Worksheet | None = None):
        if input_object is None:
            input_object = select_open_file(file_extension="csv", obj=get_application_from_parent(parent))
        super().__init__(procedure=procedure, parent=parent, input_object=input_object)
        self.parse()

    def parse(self):
        if isinstance(self.input_object, Workbook):
             worksheet = self.get_worksheet(1)
        elif isinstance(self.input_object, Worksheet):
            worksheet = self.input_object
        else:
            raise TypeError(f"Unknown input object type: {type(self.input_object)}")
        self.info_parser = QubitInfoParser(worksheet=worksheet, procedure=self.procedure)
        self.sample_parser = QubitSampleParser(worksheet=worksheet, procedure=self.procedure)
