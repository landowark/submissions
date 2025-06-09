"""

"""
import logging
from string import ascii_lowercase
from typing import Generator
from tools import row_keys
from . import DefaultKEYVALUEParser, DefaultTABLEParser

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmissionParser(DefaultKEYVALUEParser):
    """
    Object for retrieving submitter info from "sample list" sheet
    """

    default_range_dict = [dict(
        start_row=2,
        end_row=18,
        key_column=1,
        value_column=2,
        sheet="Sample List"
    )]



class SampleParser(DefaultTABLEParser):
    """
    Object for retrieving submitter info from "sample list" sheet
    """

    default_range_dict = [dict(
        header_row=20,
        end_row=116,
        sheet="Sample List"
    )]

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        output = super().parsed_info
        for ii, sample in enumerate(output):
            if isinstance(sample["row"], str) and sample["row"].lower() in ascii_lowercase[0:8]:
                try:
                    sample["row"] = row_keys[sample["row"]]
                except KeyError:
                    pass
            sample['submission_rank'] = ii + 1
            yield sample

    def to_pydantic(self):
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample['sample_id']]
