"""
Module for default results manager
"""
from __future__ import annotations
import logging
from .. import DefaultManager
from backend.db.models import Procedure
from pathlib import Path
from frontend.widgets import ExcelSheetSelector
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from typing import Generator, List
from backend.validators.pydant import PydResults


logger = logging.getLogger(f"submission.{__name__}")

class DefaultResultsManager(DefaultManager):

    _pyd_object = PydResults

    def __init__(self, procedure: Procedure, parent, input_object: Path | str | Workbook):
        self.procedure = procedure
        super().__init__(parent=parent, input_object=input_object)

    @classmethod
    def get_sheets_for_parsing(cls, workbook: Workbook) -> List[Worksheet]:
        """
        Returns a dict of sheet names to be parsed. Override in child class if specific sheets are required.
        """
        dlg = ExcelSheetSelector(workbook=workbook)
        if dlg.exec():
            selected_sheets = dlg.get_selected_sheets()
            logger.info(f"Selected sheets: {selected_sheets}")
            return selected_sheets
        else:
            logger.warning(f"No sheets selected, cancelling.")
            return []
    
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
        return self._pyd_object(result={k: v for k, v in self.info.items()}, resultstype=self.resultstype, date_analyzed=self.info_parser.date_analyzed, parent=self.procedure)

    def samples_to_pydantic(self) -> Generator[PydResults, None, None]:
        """
        Samples must be in the format List[dict], where each dict has a single key which is the sample name, 
        and the value is a dict with keys 'result', 'resultstype', and 'date_analyzed'. 
        This is to accommodate multiple samples with the same name but different well positions.
        """
        for sample in self.samples:
            for sample_name, sample_info in sample.items():
                try:
                    procedure_name = self.procedure.name
                except AttributeError:
                    procedure_name = None
                sample = dict(sample=sample_name, procedure=procedure_name, row=sample_info.get('row'), column=sample_info.get('column'))
                yield self._pyd_object(sample=sample_name, resultstype=self.resultstype, parent=self.procedure, **sample_info)
    

from .diomni_pcr_results_manager import DiomniPCRManager
from .qubit_results_manager import QubitManager
