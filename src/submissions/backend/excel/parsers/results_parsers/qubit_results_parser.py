"""
Results parser for Qubit csv file.
"""
from __future__ import annotations
import logging
from typing import Generator, TYPE_CHECKING
from backend.excel.parsers.results_parsers import DefaultResultsInfoParser, DefaultResultsSampleParser
from openpyxl.worksheet.worksheet import Worksheet
if TYPE_CHECKING:
    from backend.db.models import Procedure

logger = logging.getLogger(f"submissions.{__name__}")


class QubitInfoParser(DefaultResultsInfoParser):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        self.results_type = "Qubit"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type=self.results_type, *args, **kwargs)

    
class QubitSampleParser(DefaultResultsSampleParser):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        self.results_type = "Qubit"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type="Qubit", *args, **kwargs)

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        for item in super().parsed_info:
            item['date_analyzed'] = item['test_date']
            
            yield item
