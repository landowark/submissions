"""
Module for default results manager
"""
from __future__ import annotations
import csv
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from .. import DefaultManager
# from backend.db.models import Procedure
# from frontend.widgets import select_open_file
from pathlib import Path
# from frontend.widgets import ExcelSheetSelector
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image
from typing import Generator, List
from backend.validators.pydant import PydResults, PydProcedure


class QtResultsUI(object):
      """
      The dialogs the results managers need, shown with Qt. The web UI passes webui.results.WebResultsUI instead.
      """

      @staticmethod
      def choose_file(filetypes: str, parent=None) -> Path | None:
          from frontend.widgets import select_open_file
          from tools import get_application_from_parent
          return select_open_file(filetypes=filetypes, obj=get_application_from_parent(parent) if parent is not None else None)

      @staticmethod
      def choose_sheets(workbook: Workbook) -> List[Worksheet]:
          from frontend.widgets import ExcelSheetSelector
          dlg = ExcelSheetSelector(workbook=workbook)
          if dlg.exec():
              return dlg.get_selected_sheets()
          return []

      @staticmethod
      def match_samples(procedure, results: list, results_var_name: str, results_type: str) -> list:
          """
          :return: Results objects to save, or [] if cancelled.
          """
          from frontend.widgets.results_sample_matcher import ResultsSampleMatcher
          dlg = ResultsSampleMatcher(parent=None, results_var_name=results_var_name, results=results,
                                     samples=procedure.proceduresampleassociation, procedure=procedure,
                                     results_type=results_type)
          return dlg.output if dlg.exec() else []
      

class DefaultResultsManager(DefaultManager):

    _pyd_object = PydResults

    def __init__(self, procedure: PydProcedure, parent, input_object: Path | str, ui=None):
        self.procedure = procedure
        self.ui = ui or QtResultsUI()
        input_object = Path(input_object) if isinstance(input_object, str) else input_object
        if not input_object or not input_object.exists():
            input_object = self.ui.choose_file(filetypes="Excel Files (*.xlsx)", parent=parent)
        if input_object is None:
            raise FileNotFoundError("No results file selected.")
        if input_object.suffix == ".csv":
            input_object, _ = self.csv2xlsx(input_object)
            # ws = wb.active
            # with open(input_object, 'r', encoding='utf-8') as f:
            #     reader = csv.reader(f)
            #     for row in reader:
            #         ws.append(row)
            # input_object = wb
        wb = load_workbook(input_object) if isinstance(input_object, (str, Path)) else input_object
        wb.file = input_object
        super().__init__(parent=parent, input_object=wb)

    def get_sheets_for_parsing(self, workbook: Workbook) -> List[Worksheet]:
        """
        Returns the sheets to be parsed, chosen by the user. Override in child class if specific sheets are required.
        """
        selected_sheets = self.ui.choose_sheets(workbook)
        if selected_sheets:
            logger.info(f"Selected sheets: {selected_sheets}")
        else:
            logger.warning(f"No sheets selected, cancelling.")
        return selected_sheets
    
    @classmethod
    def deep_merge(cls, destination, source):
        """
        Recursively merge two dictionaries. Values from dict_b will overwrite those in dict_a when keys conflict, except when both values are dictionaries, in which case they will be merged recursively.
        """
        result = destination.copy()
        for key, value in source.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = cls.deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def procedure_to_pydantic(self) -> PydResults:
        procedure = self.procedure.name.value if hasattr(self.procedure.name, "value") else self.procedure.name
        return self._pyd_object(result={k: v for k, v in self.info.items()}, resultstype=self.resultstype, date_analyzed=self.info_parser.date_analyzed, procedure=procedure, is_sample=False)

    def samples_to_pydantic(self) -> Generator[PydResults, None, None]:
        """
        Samples must be in the format List[dict], where each dict has a single key which is the sample name, 
        and the value is a dict with keys 'result', 'resultstype', and 'date_analyzed'. 
        This is to accommodate multiple samples with the same name but different well positions.
        """
        for sample in self.samples:
            for sample_name, sample_info in sample.items():
                procedure_name = self.procedure.name.value if hasattr(self.procedure.name, "value") else self.procedure.name
                sample = dict(sample=sample_name, procedure=procedure_name, row=sample_info.get('row'), column=sample_info.get('column'))
                yield self._pyd_object(sample=sample_name, procedure=procedure_name, is_sample=True, **sample_info)


class DefaultImageManager(DefaultManager):

    def __init__(self, procedure: PydProcedure, parent, input_object: Path | str | Image | None):
        self.procedure = procedure
        if not input_object:
            from frontend.widgets import select_open_file
            input_object = select_open_file(filetypes="Image Files (*.png *.jpg *.jpeg *.tif *.tiff)")
        input_object = Path(input_object) if isinstance(input_object, str) else input_object
        input_object = Image.open(input_object) if isinstance(input_object, (str, Path)) else input_object
        super().__init__(parent=parent, input_object=input_object)


from .diomni_pcr_results_manager import *
from .qubit_results_manager import *
from .gelbox_results_manager import *

__all__ = ["DefaultResultsManager", "DiomniPCRManager", "QubitManager", "GelManager"]
