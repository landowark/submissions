""" 
Default parsers for results 
"""
from __future__ import annotations
from openpyxl.worksheet.worksheet import Worksheet
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from typing import Tuple, Generator, Any
import logging


logger = logging.getLogger(f"submissions.{__name__}")


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


from .diomni_pcr_results_parser import DiomniPCRInfoParser, DiomniPCRSampleParser
from .qubit_results_parser import QubitInfoParser, QubitSampleParser
