"""
Default Parser archetypes.
"""
from __future__ import annotations
import logging, re
from pprint import pformat
from typing import Generator
from openpyxl.cell import MergedCell
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultParser(object):

    range_dict = dict(start_row = 1)

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.worksheet.title}>"

    def __init__(self, worksheet: Worksheet, start_row: int = 1, end_row: int | None = None, *args, **kwargs):
        """

        Args:
            filepath (Path|str): Must be given as a kwarg. eg. filepath=X
            procedure ():
            range_dict ():
            *args ():
            **kwargs ():
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

        Returns:
            int: Start row number
        """
        for iii, row in enumerate(worksheet.iter_rows(min_row=start_row), start=start_row):
            if not all([item.value is None for item in row]):
                return iii
        return worksheet.min_row

    @classmethod
    def delineate_end_row(cls, worksheet: Worksheet, start_row: int = 1) -> int:
        """
        Determines the end row by finding the first empty row.

        Returns:
            int: End row number
        """
        for iii, row in enumerate(worksheet.iter_rows(min_row=start_row), start=start_row):
            if all([item.value is None for item in row]):
                return iii
        return worksheet.max_row + 1


class DefaultKEYVALUEParser(DefaultParser):

    @property
    def parsed_info(self) -> Generator[tuple, None, None]:
        """
        Generates key, value tuples for rows in an excel sheet.

        Returns:
            Generator[tuple, None, None]: (key, value) tuple.
        """
        rows = range(self.start_row, self.end_row)
        for row in rows:
            check_row = [item for item in self.worksheet.rows][row-1]
            if any([isinstance(cell, MergedCell) for cell in check_row]):
                continue
            key = self.worksheet.cell(row, 1).value
            if key:
                # NOTE: Remove anything in brackets.
                key = re.sub(r"\(.*\)", "", key)
                key = re.sub(r"\s+", "_", key.lower().replace(":", "").strip())
                # NOTE: If there are more than 3 spaces in the key, continue
                if key.count(" ") > 3:
                    logger.warning(f"There are more than 3 spaces in {key}, skipping")
                    continue
                value = self.worksheet.cell(row, 2).value
                missing = False if value else True
                value = dict(value=value, missing=missing)
                yield key, value


class DefaultTABLEParser(DefaultParser):

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        """
        Generates dictionaries of data from Excel rows.

        Returns:
            Generator[dict, None, None]: {column_header: row column value}
        """
        df = DataFrame(
            [item for item in self.worksheet.values][self.start_row - 1: self.end_row - 1])
        df.columns = df.iloc[0]
        df = df[1:]
        df = df.dropna(axis=1, how='all')
        for row in df.iterrows():
            output = {}
            for key, value in row[1].to_dict().items():
                if isinstance(key, str):
                    key = key.lower().replace(" ", "_")
                    key = re.sub(r"_(\(.*\)|#)", "", key)
                output[key] = value
            yield output

    def to_pydantic(self, **kwargs):
        return [self._pyd_object(**output) for output in self.parsed_info]


from .procedure_parsers import ProcedureInfoParser, ProcedureSampleParser, ProcedureReagentParser, ProcedureEquipmentParser
from .results_parsers import (
    DefaultResultsInfoParser, DefaultResultsSampleParser,
    DiomniPCRSampleParser, DiomniPCRInfoParser,
    QubitInfoParser, QubitSampleParser
)
from .clientsubmission_parser import ClientSubmissionSampleParser, ClientSubmissionInfoParser
