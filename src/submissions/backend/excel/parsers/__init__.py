"""

"""
from __future__ import annotations
import logging, re
from pathlib import Path
from typing import Generator, TYPE_CHECKING
from openpyxl.cell import MergedCell
from openpyxl.reader.excel import load_workbook
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
        logger.debug(f"\n\nHello from {self.__class__.__name__}\n\n")
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
        self.workbook = load_workbook(self.filepath, data_only=True)
        self.worksheet = self.workbook[self.sheet]
        self.start_row = self.delineate_start_row(start_row=start_row)
        self.end_row = self.delineate_end_row(start_row=self.start_row)
        logger.debug(f"Start row: {self.start_row}, End row: {self.end_row}")

    def to_pydantic(self):
        # data = {key: value['value'] for key, value in self.parsed_info.items()}
        data = self.parsed_info
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
        return self.worksheet.max_row


class DefaultKEYVALUEParser(DefaultParser):

    sheet = "Client Info"
    start_row = 1

    @property
    def parsed_info(self):

        rows = range(self.start_row, self.end_row)
        for row in rows:
            check_row = [item for item in self.worksheet.rows][row-1]
            logger.debug(f"Checking row {row-1}, {check_row} for merged cells.")
            if any([isinstance(cell, MergedCell) for cell in check_row]):
                continue
            key = self.worksheet.cell(row, 1).value
            if key:
                # Note: Remove anything in brackets.
                key = re.sub(r"\(.*\)", "", key)
                key = key.lower().replace(":", "").strip().replace(" ", "_")
                value = self.worksheet.cell(row, 2).value
                missing = False if value else True
                # location_map = dict(row=row, key_column=1, value_column=2, sheet=self.worksheet.title)
                value = dict(value=value, missing=missing)#, location=location_map)
                logger.debug(f"Yielding {value} for {key}")
                yield key, value


class DefaultTABLEParser(DefaultParser):

    sheet = "Client Info"
    start_row = 18

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        logger.debug(f"creating dataframe from {self.start_row} to {self.end_row}")
        df = DataFrame(
            [item for item in self.worksheet.values][self.start_row - 1:self.end_row - 1])
        df.columns = df.iloc[0]
        df = df[1:]
        df = df.dropna(axis=1, how='all')
        for ii, row in enumerate(df.iterrows()):
            output = {}
            # for key, value in row[1].to_dict().items():
            for key, value in row[1].details_dict().items():
                if isinstance(key, str):
                    key = key.lower().replace(" ", "_")
                    key = re.sub(r"_(\(.*\)|#)", "", key)
                # logger.debug(f"Row {ii} values: {key}: {value}")
                output[key] = value
            yield output

    def to_pydantic(self, **kwargs):
        return [self._pyd_object(**output) for output in self.parsed_info]


from .clientsubmission_parser import ClientSubmissionSampleParser, ClientSubmissionInfoParser
from backend.excel.parsers.results_parsers.pcr_results_parser import PCRInfoParser, PCRSampleParser
