"""

"""
from __future__ import annotations
import logging
from pathlib import Path
from backend.db.models import Procedure
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from frontend.widgets.results_sample_matcher import ResultsSampleMatcher
from tools import get_application_from_parent
from frontend.widgets.functions import select_open_file
from backend.excel.parsers.results_parsers.qubit_results_parser import QubitSampleParser, QubitInfoParser
from . import DefaultResultsManager


logger = logging.getLogger(f"submissions.{__name__}")

class QubitManager(DefaultResultsManager):

    resultstype = "Qubit"

    def __init__(self, procedure: Procedure, parent, input_object: Path | str | Workbook | Worksheet | None = None):
        if input_object is None:
            input_object = select_open_file(file_extension="csv", obj=get_application_from_parent(parent))
        super().__init__(procedure=procedure, parent=parent, input_object=input_object)
        self.sample_matcher()

    def sample_matcher(self):
        dlg = ResultsSampleMatcher(
            parent=None,
            results_var_name="original_sample_conc.",
            results=self.sample_parser.parsed_info,
            samples=self.procedure.proceduresampleassociation,
            procedure=self.procedure,
            results_type="Qubit"
        )
        if dlg.exec():
            for result in dlg.output:
                result.save()

    def procedure_to_pydantic(self) -> None:
        """
        Qubit doesn't produce procedure-level results, so this method returns None.
        """
        return None

    def parse(self):
        if isinstance(self.input_object, Workbook):
             worksheet = self.get_worksheet(1)
        elif isinstance(self.input_object, Worksheet):
            worksheet = self.input_object
        else:
            raise TypeError(f"Unknown input object type: {type(self.input_object)}")
        self.info_parser = QubitInfoParser(worksheet=worksheet, procedure=self.procedure)
        self.sample_parser = QubitSampleParser(worksheet=worksheet, procedure=self.procedure)
        self.info = {k:v for k, v in self.info_parser.parsed_info}
        self.samples = [item for item in self.sample_parser.parsed_info]

__all__ = ["QubitManager"]