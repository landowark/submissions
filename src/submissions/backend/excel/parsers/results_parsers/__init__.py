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
    """
    Default parser for results meta information from an Excel worksheet. 
    This parser extracts key-value pairs and processes them according to the specified Pydantic model.

    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    """
    pyd_name = "PydResults"

    def __init__(self, worksheet: Worksheet, results_type: str | None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param results_type: The type of results to be parsed. If None, a default value will be used.
        :type results_type: str | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row' for delineating the parsing range.
        """
        from backend.validators.pydant import PydResults
        self.resultstype = results_type or "Default ResultsType"
        super().__init__(worksheet=worksheet, *args, **kwargs)
        self._pyd_object = PydResults

    @property
    def parsed_info(self) -> Generator[Tuple[str, Any], None, None]:
        """
        Generates key, value tuples for rows in an excel sheet.

        :returns: Generator[tuple, None, None]
        :rtype: Generator[Tuple[str, Any], None, None]
        """
        from backend.validators.pydant import SourcedField
        for key, value in super().parsed_info:
            match value:
                case dict():
                    try:
                        value = value['value']
                    except KeyError:
                        pass
                case SourcedField():
                    value = value.value
                case str() | int() | float() | bool():
                    value = value
                case _:
                    logger.warning(f"Unexpected value type: {type(value)} for key: {key}. Value: {value}")
            yield key, value
        

class DefaultResultsSampleParser(DefaultTABLEParser):
    """
    Default parser for results meta information from an Excel worksheet. 
    This parser extracts column-value pairs  for each table row and processes them according to the specified Pydantic model.
    Ultimate parent class is DefaultTABLEParser

    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar results_type: The type of results to be parsed. If None, a default value will be used.
    :type results_type: str | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments.
    """
    pyd_name = "PydResults"

    def __init__(self, worksheet: Worksheet, results_type: str | None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param results_type: The type of results to be parsed. If None, a default value will be used.
        :type results_type: str | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row' for delineating the parsing range.
        """
        from backend.validators.pydant import PydResults
        self.resultstype = results_type or "Default ResultsType"
        super().__init__(worksheet=worksheet, *args, **kwargs)
        self._pyd_object = PydResults


class DefaultResultsWidgetParser(QDialog):
    """
    Widget to display results information and samples in a GUI dialog. 
    This class extends QDialog to provide a user interface for viewing parsed results data.

    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    """

    pyd_name = "PydResults"

    def __init__(self, results_type:str | None, *args, **kwargs) -> None:
        """
        :param results_type: The type of results to be parsed. If None, a default value will be used.
        :type results_type: str | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row' for delineating the parsing range.
        """
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