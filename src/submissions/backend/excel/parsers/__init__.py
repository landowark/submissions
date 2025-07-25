"""

"""
from __future__ import annotations
import logging, re
from pathlib import Path
from typing import Generator, Tuple, TYPE_CHECKING

from openpyxl.reader.excel import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
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

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType | None = None, range_dict: dict | None = None,
                 *args, **kwargs):
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
        self.workbook = load_workbook(self.filepath, data_only=True)
        if not range_dict:
            self.range_dict = self.__class__.default_range_dict
        else:
            self.range_dict = range_dict
        logger.debug(f"Default parser range dict: {self.range_dict}")
        for item in self.range_dict:
            item['worksheet'] = self.workbook[item['sheet']]

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

    @classmethod
    def delineate_end_row(cls, worksheet: Worksheet, start_row: int = 1):
        for iii, row in enumerate(worksheet.iter_rows(min_row=start_row), start=1):
            if all([item.value is None for item in row]):
                return iii


class DefaultKEYVALUEParser(DefaultParser):
    # default_range_dict = [dict(
    #     start_row=2,
    #     end_row=18,
    #     key_column=1,
    #     value_column=2,
    #     sheet="Sample List"
    # )]

    # default_range_dict = [dict(sheet="Sample List", start_row=2)]

    @property
    def parsed_info(self):
        for item in self.range_dict:
            item['end_row'] = self.delineate_end_row(item['worksheet'], start_row=item['start_row'])
            rows = range(item['start_row'], item['end_row'])
            # item['start_row'] = item['end_row']
            # del item['end_row']
            for row in rows:
                key = item['worksheet'].cell(row, 1).value
                if key:
                    # Note: Remove anything in brackets.
                    key = re.sub(r"\(.*\)", "", key)
                    key = key.lower().replace(":", "").strip().replace(" ", "_")
                    value = item['worksheet'].cell(row, 2).value
                    missing = False if value else True
                    location_map = dict(row=row, key_column=1, value_column=2,
                                        sheet=item['sheet'])
                    value = dict(value=value, location=location_map, missing=missing)
                    logger.debug(f"Yielding {value} for {key}")
                    yield key, value



class DefaultTABLEParser(DefaultParser):
    default_range_dict = [dict(
        header_row=18,
        sheet="Sample List"
    )]

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        for item in self.range_dict:
            # list_worksheet = self.workbook[item['sheet']]
            list_worksheet = item['worksheet']
            if "end_row" in item.keys():
                list_df = DataFrame(
                    [item for item in list_worksheet.values][item['header_row'] - 1:item['end_row'] - 1])
            else:
                list_df = DataFrame([item for item in list_worksheet.values][item['header_row'] - 1:])
            list_df.columns = list_df.iloc[0]
            list_df = list_df[1:]
            list_df = list_df.dropna(axis=1, how='all')
            for ii, row in enumerate(list_df.iterrows()):
                output = {}
                for key, value in row[1].to_dict().items():
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
