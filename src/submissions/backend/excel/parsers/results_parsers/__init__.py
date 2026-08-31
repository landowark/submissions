""" 
Default parsers for results 
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt
from openpyxl.worksheet.worksheet import Worksheet
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from typing import Tuple, Generator, Any


class DefaultResultsInfoParser(DefaultKEYVALUEParser):
    pyd_name = "PydResults"

    def __init__(self, worksheet: Worksheet, results_type: str | None, *args, **kwargs):
        from backend.validators.pydant import PydResults
        self.resultstype = results_type or "Default ResultsType"
        super().__init__(worksheet=worksheet, *args, **kwargs)
        self._pyd_object = PydResults

    @property
    def parsed_info(self) -> Generator[Tuple[str, Any], None, None]:
        for key, value in super().parsed_info:
            try:
                value = value['value']
            except KeyError:
                pass
            yield key, value
        

class DefaultResultsSampleParser(DefaultTABLEParser):
    pyd_name = "PydResults"

    def __init__(self, worksheet: Worksheet, results_type: str | None, *args, **kwargs):
        from backend.validators.pydant import PydResults
        self.resultstype = results_type or "Default ResultsType"
        super().__init__(worksheet=worksheet, *args, **kwargs)
        self._pyd_object = PydResults


class DefaultResultsWidgetParser(QDialog):

    pyd_name = "PydResults"

    def __init__(self, results_type:str | None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        
        # Optional: ensure it stays resizable
        self.setWindowState(Qt.WindowState.WindowNoState)
        from backend.validators.pydant import PydResults
        self.resultstype = results_type or "Default ResultsType"
        self._pyd_object = PydResults


from .diomni_pcr_results_parser import *
from .qubit_results_parser import *
from .gelbox_results_parser import *

__all__ = ["DefaultResultsInfoParser", "DefaultResultsSampleParser", 
           "DiomniPCRInfoParser", "DiomniPCRSampleParser", "QubitInfoParser", 
           "QubitSampleParser", "GelBoxParser"]