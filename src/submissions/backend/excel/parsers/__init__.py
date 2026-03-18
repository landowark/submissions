"""
Default Parser archetypes.
"""
from __future__ import annotations
import logging, re, csv
from pathlib import Path
from pprint import pformat
from typing import Generator, TYPE_CHECKING, List
from openpyxl.cell import MergedCell
from openpyxl.reader.excel import load_workbook
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame
from backend.validators import pydant
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultParser(object):

    sheets = [dict(sheet = "Client Info", start_row = 1)]

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.filepath.stem}>"

    def __new__(cls, *args, **kwargs):
        """
        Is called before __init__. Ensures filepath is present.
        """
        filepath = kwargs.get('filepath') or args[0]
        if isinstance(filepath, str):
            filepath = Path(filepath)
        try:
            assert filepath.exists()
        except AssertionError:
            raise FileNotFoundError(f"File {filepath} does not exist.")
        instance = super().__new__(cls)
        instance.filepath = filepath
        return instance

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType | None = None, sheets: List[dict] | None = None,
                 *args, **kwargs):
        """

        Args:
            filepath (Path|str): Must be given as a kwarg. eg. filepath=X
            procedure ():
            range_dict ():
            *args ():
            **kwargs ():
        """
        logger.info(f"\n\nHello from {self.__class__.__name__}\n\n")
        if isinstance(filepath, str):
            filepath = Path(filepath)
        self.filepath = filepath
        self.proceduretype = proceduretype
        if self.filepath.suffix == ".xlsx":
            self.workbook = load_workbook(self.filepath, data_only=True)
        # NOTE: convert csv to xlsx for standardization purposes.
        elif self.filepath.suffix == ".csv":
            self.workbook, _ = self.csv2xlsx(self.filepath)
        # self.start_row = self.delineate_start_row(start_row=start_row)
        # self.end_row = self.delineate_end_row(start_row=self.start_row)
        # logger.debug(f"Parsing from {self.start_row} to {self.end_row}")
        if not sheets:
            sheets = self.__class__.sheets
        logger.debug(f"Sheets before {self.__class__.__name__} set: {sheets}")
        for sheet in sheets:
            worksheet: Worksheet = self.get_worksheet(sheet=sheet.get('sheet', 0))
            sheet['start_row'] = self.delineate_start_row(worksheet=worksheet, start_row=sheet.get("start_row", 1))
            sheet['end_row'] = self.delineate_end_row(worksheet=worksheet, start_row=sheet.get("start_row",1))
        self.sheets = sheets
        logger.debug(f"Sheets after {self.__class__.__name__} set: {self.sheets}")
        # try:
        #     self._pyd_object = self.pydant_object
        # except AttributeError:
        #     self._pyd_object = None

    @property
    def _pyd_object(self):
        try:
            return getattr(pydant, f"Pyd{self.__class__.__name__.replace('Parser', '').replace('Info', '')}")
        except AttributeError as e:
            logger.error(
                f"Couldn't get pyd object: Pyd{self.__class__.__name__.replace('Parser', '').replace('Info', '')}, using {self.__class__.pyd_name}")
            try:
                return getattr(pydant, self.__class__.pyd_name)
            except AttributeError:
                logger.error(f"Couldn't get pyd object using pyd_name. Returning None")
                return None
        
    def get_worksheet(self, sheet: Worksheet | str | int = 0):
        match sheet:
            case Worksheet():
                return sheet
            case str():
                return self.workbook[sheet]
            case int():
                return self.workbook.worksheets[sheet - 1]
            case _:
                raise TypeError(f"Invalid type for worksheet retrieval: {type(sheet)}")

    @classmethod
    def csv2xlsx(cls, filepath):
        wb = Workbook()
        ws = wb.active
        with open(filepath, "r") as f:
            reader = csv.reader(f, delimiter=",")
            for row in reader:
                ws.append(row)
        return wb, ws

    def to_pydantic(self):
        data = self.parsed_info
        # logger.debug(f"Data for {self.__class__.__name__}: {pformat(data)}")
        data['filepath'] = self.filepath
        return self._pyd_object(**data)

    @classmethod
    def correct_procedure_type(cls, proceduretype: str | ProcedureType) -> ProcedureType:
        """
        Attempts to get the correct proceduretype through query.
        
        Args:
            proceduretype (str): Name of the desired proceduretype
        
        Returns: 
            ProcedureType: The instance of the desired proceduretype
        """
        from backend.db.models import ProcedureType
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        return proceduretype

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
    def delineate_end_row(cls, worksheet: Worksheet, start_row: int = 1):
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
        
        for iii, sheet in enumerate(self.sheets):
            logger.debug(f"Running sheet: {sheet}")
            worksheet: Worksheet = self.get_worksheet(sheet.get('sheet', 0))
            start_row = sheet.get('start_row', self.delineate_start_row(worksheet=worksheet))
            logger.debug(f"Using start row: {start_row}")
            # NOTE: Update start_row of sheet to reflect reality.
            self.sheets[iii]['start_row'] = start_row
            end_row = sheet.get('end_row', self.delineate_end_row(worksheet=worksheet, start_row=start_row))
            logger.debug(f"Using end row: {end_row}")
            # NOTE: Update end_row of sheet to reflect reality.
            self.sheets[iii]['end_row'] = end_row
            rows = range(start_row, end_row)
            for row in rows:
                check_row = [item for item in worksheet.rows][row-1]
                if any([isinstance(cell, MergedCell) for cell in check_row]):
                    continue
                key = worksheet.cell(row, 1).value
                if key:
                    # NOTE: If there are more than 3 spaces in the key, continue
                    if key.count(" ") > 3:
                        continue
                    # NOTE: Remove anything in brackets.
                    key = re.sub(r"\(.*\)", "", key)
                    key = key.lower().replace(":", "").strip().replace(" ", "_")
                    value = worksheet.cell(row, 2).value
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
        
        for iii, sheet in enumerate(self.sheets):
            logger.debug(f"Parsing sheet: {sheet}")
            worksheet: Worksheet = self.get_worksheet(sheet.get('sheet', 0))
            start_row = sheet.get('start_row', self.delineate_start_row(worksheet=worksheet))
            end_row = sheet.get('end_row', self.delineate_end_row(worksheet=worksheet, start_row=start_row))
            logger.debug(f"DF construction: start row: {start_row}, end row: {end_row}")
            self.sheets[iii]['start_row'] = start_row
            self.sheets[iii]['end_row'] = end_row
            df = DataFrame(
                [item for item in worksheet.values][start_row - 1: end_row - 1])
            df.columns = df.iloc[0]
            df = df[1:]
            df = df.dropna(axis=1, how='all')
            for ii, row in enumerate(df.iterrows()):
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
