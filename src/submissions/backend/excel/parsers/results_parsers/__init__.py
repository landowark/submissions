""" 
Default parsers for results 
"""
from __future__ import annotations
from pathlib import Path
from openpyxl.worksheet.worksheet import Worksheet
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from typing import TYPE_CHECKING, Tuple, Generator, Any, List
import logging
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoParser(DefaultKEYVALUEParser):
    pyd_name = "PydResults"

    def __init__(self, worksheet: Worksheet, results_type: str, *args, **kwargs):
        from backend.db.models import ResultsType
        if results_type:
            self.results_type = ResultsType.query(name=results_type)
        super().__init__(worksheet=worksheet, *args, **kwargs)

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

    def __init__(self, worksheet: Worksheet, results_type: str, *args, **kwargs):
        from backend.db.models import ResultsType
        if results_type:
            self.results_type = ResultsType.query(name=results_type)
        super().__init__(worksheet=worksheet, *args, **kwargs)


from .diomni_pcr_results_parser import DiomniPCRInfoParser, DiomniPCRSampleParser
from .qubit_results_parser import QubitInfoParser, QubitSampleParser
