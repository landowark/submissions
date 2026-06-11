"""
Module for clientsubmission parsing
"""
from __future__ import annotations
from pprint import pformat
import logging, sys
from datetime import datetime, time
from string import ascii_lowercase
from typing import Generator, TYPE_CHECKING, Tuple
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
        output["submitted_date"]['value'] = datetime.combine(output['submitted_date']['value'], datetime.now().time())
        output['endrow'] = self.end_row
        return output


class ClientSubmissionSampleParser(DefaultTABLEParser):#, SubmissionTyperMixin):
    """
    Object for retrieving submitter samples from "sample list" sheet
    """

    pyd_name = "PydSample"

    def __init__(self, worksheet: Worksheet, submissiontype: SubmissionType | None = None, *args, **kwargs):
        namer = ClientSubmissionNamer(filepath=worksheet._parent.file)
        self.submitter_id = kwargs.get("submitter_id", datetime.now().date().strftime("%Y-%m-%d"))
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
            sample['sample_id'], sample['is_control'] = self.determine_control(sample.get("sample_id", None))
            yield sample

    def determine_control(self, sample_id: str | None) -> Tuple[str, int]:
        if sample_id is None:
            return sample_id, 0
        if not isinstance(sample_id, str):
            sample_id = str(sample_id)
        if sample_id.lower() in ["", "blank", "na", "n/a", "n\\a"]:
            return "BLANK", 0
        if sample_id.lower().startswith(("atcc", "mcs", "pos", "positivecontrol", "poscontrol", "pc")):
            return sample_id, 1
        if sample_id.lower().startswith(("en", "neg", "negcontrol", "negativecontrol", "nc")):
            return sample_id, -1
        if "pbs" in sample_id.lower():
            if sample_id.lower() == "pbs-":
                output = f"PBS-{self.submitter_id}"
            else:
                output = sample_id
            return output, -1
        return sample_id, 0
        
    def to_pydantic(self):
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample.get('sample_id', None)]
