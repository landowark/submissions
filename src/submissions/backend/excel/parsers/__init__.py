"""

"""
import logging, re
from pathlib import Path
from typing import Generator, Tuple
from openpyxl import load_workbook
from pandas import DataFrame
from backend.validators import pydant
from backend.db.models import Procedure

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultParser(object):

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.filepath.stem}>"

    def __init__(self, filepath: Path | str, procedure: Procedure|None=None, range_dict: dict | None = None, *args, **kwargs):
        self.procedure = procedure
        try:
            self._pyd_object = getattr(pydant, f"Pyd{self.__class__.__name__.replace('Parser', '')}")
        except AttributeError:
            self._pyd_object = pydant.PydResults
        if isinstance(filepath, str):
            self.filepath = Path(filepath)
        else:
            self.filepath = filepath
        self.workbook = load_workbook(self.filepath, data_only=True)
        if not range_dict:
            self.range_dict = self.__class__.default_range_dict
        else:
            self.range_dict = range_dict
        for item in self.range_dict:
            item['worksheet'] = self.workbook[item['sheet']]

    def to_pydantic(self):
        data = {key: value for key, value in self.parsed_info}
        data['filepath'] = self.filepath
        return self._pyd_object(**data)


class DefaultKEYVALUEParser(DefaultParser):

    default_range_dict = [dict(
        start_row=2,
        end_row=18,
        key_column=1,
        value_column=2,
        sheet="Sample List"
    )]



    @property
    def parsed_info(self) -> Generator[Tuple, None, None]:
        for item in self.range_dict:
            rows = range(item['start_row'], item['end_row'] + 1)
            for row in rows:
                key = item['worksheet'].cell(row, item['key_column']).value
                if key:
                    # Note: Remove anything in brackets.
                    key = re.sub(r"\(.*\)", "", key)
                    key = key.lower().replace(":", "").strip().replace(" ", "_")
                    value = item['worksheet'].cell(row, item['value_column']).value
                    value = dict(value=value, missing=False if value else True)
                    yield key, value


class DefaultTABLEParser(DefaultParser):

    default_range_dict = [dict(
        header_row=20,
        end_row=116,
        sheet="Sample List"
    )]

    @property
    def parsed_info(self):
        for item in self.range_dict:
            list_worksheet = self.workbook[item['sheet']]
            list_df = DataFrame([item for item in list_worksheet.values][item['header_row'] - 1:])
            list_df.columns = list_df.iloc[0]
            list_df = list_df[1:]
            list_df = list_df.dropna(axis=1, how='all')
            for ii, row in enumerate(list_df.iterrows()):
                output = {key.lower().replace(" ", "_"): value for key, value in row[1].to_dict().items()}
                yield output

    def to_pydantic(self, **kwargs):
        return [self._pyd_object(**output) for output in self.parsed_info]

from .submission_parser import *
