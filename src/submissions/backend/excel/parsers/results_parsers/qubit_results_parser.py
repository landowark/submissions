"""
Results parser for Qubit csv file.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from typing import Generator, TYPE_CHECKING
from backend.excel.parsers.results_parsers import DefaultResultsInfoParser, DefaultResultsSampleParser
from openpyxl.worksheet.worksheet import Worksheet
if TYPE_CHECKING:
    from backend.db.models import Procedure


class QubitInfoParser(DefaultResultsInfoParser):
    """
    Object to pull data from Design and Analysis PCR export file.
    This parser extracts key-value pairs and processes them according to the specified Pydantic model.
    Ultimate parent class is DefaultKeyValueParser
    
    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar procedure: The procedure associated with the results. If None, a default value will be used.
    :type procedure: Procedure | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row'.
    """

    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param procedure: The procedure associated with the results. If None, a default value will be used.
        :type procedure: Procedure | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row'.
        """
        self.results_type = "Qubit"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type=self.results_type, *args, **kwargs)

    
class QubitSampleParser(DefaultResultsSampleParser):
    """
    Default parser for results meta information from an Excel worksheet. 
    This parser extracts column-value pairs  for each table row and processes them according to the specified Pydantic model.
    Ultimate parent class is DefaultTABLEParser

    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar procedure: The procedure associated with the results. If None, a default value will be used.
    :type procedure: Procedure | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row'.
    """
    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param procedure: The procedure associated with the results. If None, a default value will be used.
        :type procedure: Procedure | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments. Expected to include 'start_row' and 'end_row'.
        """
        self.results_type = "Qubit"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type="Qubit", *args, **kwargs)

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        """
        Generator that yields parsed information from the Excel worksheet. 
        Each item is a dictionary containing key-value pairs extracted from the worksheet, 
        with an additional 'date_analyzed' field set to the value of 'test_date'.

        :returns: A generator of dictionaries containing parsed information for each row in the worksheet.
        :rtype: Generator[dict, None, None]
        """
        for item in super().parsed_info:
            item['date_analyzed'] = item['test_date']
            yield item

__all__ = ["QubitInfoParser", "QubitSampleParser"]