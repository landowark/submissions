"""
Default Parser archetypes.
"""
from __future__ import annotations
import logging, re, csv
from pathlib import Path
from pprint import pformat
from typing import Generator, TYPE_CHECKING
from openpyxl.cell import MergedCell
from openpyxl.reader.excel import load_workbook
from openpyxl.workbook import Workbook
from pandas import DataFrame
from backend.validators import pydant
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultParser(object):

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.filepath.stem}>"

    def __new__(cls, *args, **kwargs):
        filepath = kwargs['filepath']
        if isinstance(filepath, str):
            filepath = Path(filepath)
        try:
            assert filepath.exists()
        except AssertionError:
            raise FileNotFoundError(f"File {filepath} does not exist.")
        instance = super().__new__(cls)
        instance.filepath = filepath
        return instance

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType | None = None, sheet: str | None = None,
                 start_row: int = 1, *args, **kwargs):
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
        try:
            self._pyd_object = getattr(pydant,
                                       f"Pyd{self.__class__.__name__.replace('Parser', '').replace('Info', '')}")
        except AttributeError as e:
            logger.error(
                f"Couldn't get pyd object: Pyd{self.__class__.__name__.replace('Parser', '').replace('Info', '')}, using {self.__class__.pyd_name}")
            self._pyd_object = getattr(pydant, self.__class__.pyd_name)
        if not sheet:
            sheet = self.__class__.sheet
        self.sheet = sheet
        if not start_row:
            start_row = self.__class__.start_row
        if self.filepath.suffix == ".xlsx":
            self.workbook = load_workbook(self.filepath, data_only=True)
            self.worksheet = self.workbook[self.sheet]
        elif self.filepath.suffix == ".csv":
            self.workbook, self.worksheet = self.csv2xlsx(self.filepath)
        self.start_row = self.delineate_start_row(start_row=start_row)
        self.end_row = self.delineate_end_row(start_row=self.start_row)

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
        logger.debug(f"Data for {self.__class__.__name__}: {pformat(data)}")
        data['filepath'] = self.filepath
        return self._pyd_object(**data)

    @classmethod
    def correct_procedure_type(cls, proceduretype: str | "ProcedureType"):
        from backend.db.models import ProcedureType
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        return proceduretype

    def delineate_start_row(self, start_row: int = 1):
        for iii, row in enumerate(self.worksheet.iter_rows(min_row=start_row), start=start_row):
            if not all([item.value is None for item in row]):
                return iii
        return self.worksheet.min

    def delineate_end_row(self, start_row: int = 1):
        for iii, row in enumerate(self.worksheet.iter_rows(min_row=start_row), start=start_row):
            if all([item.value is None for item in row]):
                return iii
        return self.worksheet.max_row + 1


class DefaultKEYVALUEParser(DefaultParser):

    sheet = "Client Info"
    start_row = 1

    @property
    def parsed_info(self):
        rows = range(self.start_row, self.end_row)
        for row in rows:
            check_row = [item for item in self.worksheet.rows][row-1]
            if any([isinstance(cell, MergedCell) for cell in check_row]):
                continue
            key = self.worksheet.cell(row, 1).value
            if key:
                # Note: Remove anything in brackets.
                if key.count(" ") > 3:
                    continue
                key = re.sub(r"\(.*\)", "", key)
                key = key.lower().replace(":", "").strip().replace(" ", "_")
                value = self.worksheet.cell(row, 2).value
                missing = False if value else True
                value = dict(value=value, missing=missing)#, location=location_map)
                yield key, value


class DefaultTABLEParser(DefaultParser):

    sheet = "Client Info"
    start_row = 18

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        df = DataFrame(
            [item for item in self.worksheet.values][self.start_row - 1:self.end_row - 1])
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
    PCRSampleParser, PCRInfoParser
)
from .clientsubmission_parser import ClientSubmissionSampleParser, ClientSubmissionInfoParser
from .results_parsers.pcr_results_parser import PCRInfoParser, PCRSampleParser
