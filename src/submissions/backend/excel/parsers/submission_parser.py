"""

"""
import logging, re
from pathlib import Path
from typing import Generator, Tuple
from pandas import DataFrame

from . import DefaultParser

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmissionParser(DefaultParser):
    """
    Object for retrieving submitter info from "sample list" sheet
    """

    def __init__(self, filepath: Path | str, range_dict: dict | None = None):
        super().__init__(filepath=filepath, range_dict=range_dict)
        self.worksheet = self.workbook[self.range_dict['sheet']]
        self.rows = range(self.range_dict['start_row'], self.range_dict['end_row'] + 1)

    @property
    def parsed_info(self) -> Generator[Tuple, None, None]:
        for row in self.rows:
            key = self.worksheet.cell(row, self.range_dict['key_column']).value
            if key:
                key = re.sub(r"\(.*\)", "", key)
                key = key.lower().replace(":", "").strip().replace(" ", "_")
                value = self.worksheet.cell(row, self.range_dict['value_column']).value
                value = dict(value=value, missing=False if value else True)
                yield key, value

    def to_pydantic(self):
        data = {key: value for key, value in self.parsed_info}
        data['filepath'] = self.filepath
        return self._pyd_object(**data)


class SampleParser(DefaultParser):
    """
    Object for retrieving submitter info from "sample list" sheet
    """

    default_range_dict = dict(
        header_row=20,
        end_row=116,
        list_sheet="Sample List"
    )

    def __init__(self, filepath: Path | str, range_dict: dict | None = None):
        super().__init__(filepath=filepath, range_dict=range_dict)
        self.list_worksheet = self.workbook[self.range_dict['list_sheet']]
        self.list_df = DataFrame([item for item in self.list_worksheet.values][self.range_dict['header_row'] - 1:])
        self.list_df.columns = self.list_df.iloc[0]
        self.list_df = self.list_df[1:]
        self.list_df = self.list_df.dropna(axis=1, how='all')

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        for ii, row in enumerate(self.list_df.iterrows()):
            sample = {key.lower().replace(" ", "_"): value for key, value in row[1].to_dict().items()}
            sample['submission_rank'] = ii + 1
            yield sample

    def to_pydantic(self):
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample['sample_id']]
