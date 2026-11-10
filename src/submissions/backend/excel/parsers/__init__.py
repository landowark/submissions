"""
Default Parser archetypes.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from re import sub as rsub
from typing import Generator
from openpyxl.cell import MergedCell
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame


class DefaultParser(object):
    """
    Default parser archetype for Excel worksheets. 

    This class provides methods to delineate start and end rows, 
    fix keys, and parse data from Excel worksheets.

    :cvar range_dict: Dictionary to hold range information for parsing.
    :vartype range_dict: dict
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar start_row: The starting row for parsing. Defaults to 1.
    :type start_row: int
    :ivar end_row: The ending row for parsing. If None, it will be determined automatically.
    :type end_row: int | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments.
    """

    range_dict = dict(start_row = 1)

    def __repr__(self) -> str:
        """
        :returns: {self.__class__.__name__}<{self.worksheet.title}>
        """
        return f"{self.__class__.__name__}<{self.worksheet.title}>"

    def __init__(self, worksheet: Worksheet, start_row: int = 1, end_row: int | None = None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param start_row: The starting row for parsing. Defaults to 1.
        :type start_row: int
        :param end_row: The ending row for parsing. If None, it will be determined automatically.
        :type end_row: int | None
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments.
        """
        logger.info(f"\n\nHello from {self.__class__.__name__}\n\n")
        self.worksheet = worksheet
        self.start_row = self.delineate_start_row(worksheet=worksheet, start_row=start_row)
        if end_row is None:
            self.end_row = self.delineate_end_row(worksheet=worksheet, start_row=self.start_row)
        else:
            self.end_row = self.delineate_end_row(worksheet=worksheet, start_row=end_row)
        assert self.start_row <= self.end_row
        
    @classmethod
    def delineate_start_row(cls, worksheet: Worksheet, start_row: int = 1) -> int:
        """
        Determines the start row by finding the first non-empty row.

        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param start_row: The row number to start searching from. Defaults to 1.
        :type start_row: int
        :returns: Start row number
        :rtype: int
        """
        for iii, row in enumerate(worksheet.iter_rows(min_row=start_row), start=start_row):
            if not all([item.value is None for item in row]):
                return iii
        return worksheet.min_row

    @classmethod
    def delineate_end_row(cls, worksheet: Worksheet, start_row: int = 1) -> int:
        """
        Determines the end row by finding the first empty row.

        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param start_row: The row number to start searching from. Defaults to 1.
        :type start_row: int
        :returns: End row number
        :rtype: int
        """
        for iii, row in enumerate(worksheet.iter_rows(min_row=start_row), start=start_row):
            if all([item.value is None for item in row]):
                return iii
        return worksheet.max_row + 1
    
    @staticmethod
    def fix_key(key: str) -> str | None:
        """
        Enforce a consistent key format by removing unwanted characters and normalizing whitespace.

        :param key: The original key string.
        :type key: str
        :returns: Normalized key string or None if the key is invalid.
        :rtype: str | None
        """
        key = rsub(r"\(.*\)", "", key)
        key = rsub(r"\s+", "_", key.lower().replace(":", "").strip())
        if key.count("_") > 3:
            logger.warning(f"There are more than 3 spaces in {key}, skipping")
            return None
        match key:
            case "comments":
                return "comment"
            case _:
                return key


class DefaultKEYVALUEParser(DefaultParser):
    """
    Default parser for key-value pairs from an Excel worksheet. 
    Extends DefaultParser to provide functionality for extracting key-value pairs from specified rows and columns. 
    
    This parser extracts key-value pairs and processes them according to the specified Pydantic model.

    :cvar range_dict: Dictionary to hold range information for parsing.
    :vartype range_dict: dict
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar start_row: The starting row for parsing. Defaults to 1.
    :type start_row: int
    :ivar end_row: The ending row for parsing. If None, it will be determined automatically.
    :type end_row: int | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments.
    """

    @property
    def parsed_info(self) -> Generator[tuple, None, None]:
        """
        Generates key, value tuples for rows in an excel sheet.

        :returns: Generator[tuple, None, None]
        :rtype: Generator[Tuple[str, Any], None, None]
        """
        rows = range(self.start_row, self.end_row)
        for row in rows:
            check_row = [item for item in self.worksheet.rows][row-1]
            if any([isinstance(cell, MergedCell) for cell in check_row]):
                continue
            key = self.worksheet.cell(row, 1).value
            if key:
                key = self.fix_key(key)
                # NOTE: If there are more than 3 spaces in the key, continue
                if not key:
                    continue
                value = self.worksheet.cell(row, 2).value
                missing = False if value else True
                value = dict(value=value, missing=missing)
                yield key, value

    def to_pydantic(self):
        """
        Converts the parsed key-value pairs into a _pyd_object instance.

        ***NOTE*** _pyd_object is set in child classes.

        :returns: Pydantic Model
        :rtype: _pyd_object
        """
        return self._pyd_object({k:v for k,v in self.parsed_info})


class DefaultTABLEParser(DefaultParser):
    """
    Default parser for a table from an Excel worksheet. 
    Extends DefaultParser to provide functionality for extracting key-value pairs columns in each row of a table.
    
    This parser extracts key (column) and row value pairs and processes them according to the specified Pydantic model.

    :cvar range_dict: Dictionary to hold range information for parsing.
    :vartype range_dict: dict
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar start_row: The starting row for parsing. Defaults to 1.
    :type start_row: int
    :ivar end_row: The ending row for parsing. If None, it will be determined automatically.
    :type end_row: int | None
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments.
    """
    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        """
        Generates dictionaries of data from Excel rows.

        :returns: {column_header: row column value}
        :rtype: Generator[dict, None, None]
        """
        rows = list(self.worksheet.iter_rows(
            min_row=self.start_row,
            max_row=self.end_row - 1,
            values_only=True
        ))
        if not rows:
            return
        df = DataFrame(rows[1:], columns=rows[0])
        df = df.dropna(axis=1, how='all')
        for row in df.iterrows():
            output = {}
            for key, value in row[1].to_dict().items():
                if isinstance(key, str):
                    key = self.fix_key(key)
                if key:    
                    output[key] = value
            yield output

    def to_pydantic(self, **kwargs):
        """
        Converts the parsed key-value pairs in rows into a list of _pyd_object instances.

        ***NOTE*** _pyd_object is set in child classes.

        :returns: Pydantic Model
        :rtype: List[pyd_object]
        """
        return [self._pyd_object(**output) for output in self.parsed_info]


from .procedure_parsers import *
from .results_parsers import *
from .clientsubmission_parser import *

__all__ = ["DefaultKEYVALUEParser", "DefaultTABLEParser", "ProcedureInfoParser", "ProcedureSampleParser", "ProcedureReagentParser", "ProcedureEquipmentParser",
           "DefaultResultsInfoParser", "DefaultResultsSampleParser", "DiomniPCRInfoParser", "DiomniPCRSampleParser", "QubitInfoParser", "QubitSampleParser",
           "ClientSubmissionInfoParser", "ClientSubmissionSampleParser"]