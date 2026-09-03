"""
Module for default results manager
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from .. import DefaultManager
# from backend.db.models import Procedure
from frontend.widgets import select_open_file
from pathlib import Path
from frontend.widgets import ExcelSheetSelector
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from PIL import Image
from typing import Generator, List
from backend.validators.pydant import PydResults, PydProcedure


class DefaultResultsManager(DefaultManager):

    _pyd_object = PydResults

    def __init__(self, procedure: PydProcedure, parent, input_object: Path | str ):
        self.procedure = procedure
        if not input_object:
            input_object = select_open_file(title="Select Excel File", filetypes="Excel Files (*.xlsx)")
        input_object = Path(input_object) if isinstance(input_object, str) else input_object
        wb = load_workbook(input_object) if isinstance(input_object, (str, Path)) else input_object
        wb.file = input_object
        super().__init__(parent=parent, input_object=wb)

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
            input_object = select_open_file(filetypes="Image Files (*.png *.jpg *.jpeg *.tif *.tiff)")
        input_object = Path(input_object) if isinstance(input_object, str) else input_object
        input_object = Image.open(input_object) if isinstance(input_object, (str, Path)) else input_object
        super().__init__(parent=parent, input_object=input_object)


from .diomni_pcr_results_manager import *
from .qubit_results_manager import *
from .gelbox_results_manager import *

__all__ = ["DefaultResultsManager", "DiomniPCRManager", "QubitManager", "GelManager"]
