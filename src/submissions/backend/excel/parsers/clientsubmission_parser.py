"""
Module for clientsubmission parsing
"""
from __future__ import annotations
from pprint import pformat
import logging, sys
from datetime import datetime
from string import ascii_lowercase
from typing import Generator, TYPE_CHECKING
from openpyxl.worksheet.worksheet import Worksheet
from tools import row_keys
from . import DefaultKEYVALUEParser, DefaultTABLEParser
from backend.validators import ClientSubmissionNamer
if TYPE_CHECKING:
    from backend.db.models import SubmissionType

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmissionInfoParser(DefaultKEYVALUEParser):#, SubmissionTyperMixin):
    """
    Object for retrieving submitter info from "Client Info" sheet
    """

    range_dict = dict(start_row = 1)
    exclude = ["submitter_info"]

    pyd_name = "PydClientSubmission"

    def __init__(self, worksheet: Worksheet, submissiontype: SubmissionType | None = None, *args, **kwargs):
        # NOTE: parent workbook.file  must be set manually before reaching this step
        namer = ClientSubmissionNamer(filepath=worksheet._parent.file)
        if not submissiontype:
            self.submissiontype = namer.submissiontype
        else:
            self.submissiontype = submissiontype
        super().__init__(worksheet=worksheet, **kwargs)

    @property
    def parsed_info(self):
        output = {k: v for k, v in super().parsed_info if k not in self.exclude}
        try:
            output['clientlab'] = output['client_lab']
        except KeyError:
            pass
        try:
            output['submissiontype'] = output['submission_type']
            output['submissiontype']['value'] = self.submissiontype.name.title()
        except KeyError:
            pass
        try:
            check = isinstance(output['submitted_date']['value'], datetime)
        except KeyError as e:
            logger.error(output.keys())
            raise e
        if check:
            output['submitted_date']['value'] = output['submitted_date']['value'].date()
        output['endrow'] = self.end_row
        return output


class ClientSubmissionSampleParser(DefaultTABLEParser):#, SubmissionTyperMixin):
    """
    Object for retrieving submitter samples from "sample list" sheet
    """

    sheets = [ dict(
                sheet = "Client Info",
                start_row = 18) 
            ]
    

    pyd_name = "PydSample"

    def __init__(self, worksheet: Worksheet, submissiontype: SubmissionType | None = None, *args, **kwargs):
        namer = ClientSubmissionNamer(filepath=worksheet._parent.file)
        if not submissiontype:
            self.submissiontype = namer.submissiontype
        else:
            self.submissiontype = submissiontype
        super().__init__(worksheet=worksheet, **kwargs)
        
    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        output = super().parsed_info
        for ii, sample in enumerate(output, start=1):
            try:
                if isinstance(sample["row"], str) and sample["row"].lower() in ascii_lowercase[0:8]:
                    sample["row"] = row_keys[sample["row"]]
            except KeyError:
                pass
            sample['rank'] = ii
            sample['is_control'] = self.determine_control(sample.get("sample_id", None))
            yield sample

    @classmethod
    def determine_control(cls, sample_id: str | None) -> int:
        if sample_id is None:
            return 0
        if sample_id.lower() in ["", "blank", "na", "n/a", "n\\a"]:
            return 0
        if sample_id.lower().startswith(("atcc", "mcs", "pos", "positivecontrol", "poscontrol", "pc")):
            return 1
        if sample_id.lower().startswith(("en", "neg", "negcontrol", "negativecontrol", "nc")):
            return -1
        if "pbs" in sample_id.lower():
            return -1
        return 0
        
    def to_pydantic(self):
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample.get('sample_id', None)]
