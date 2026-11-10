"""
Module for clientsubmission parsing
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from datetime import datetime
from dateutil.parser import parse
from string import ascii_lowercase
from typing import Generator, TYPE_CHECKING, Tuple, Any, List
from openpyxl.worksheet.worksheet import Worksheet
from . import DefaultKEYVALUEParser, DefaultTABLEParser
from backend.validators import ClientSubmissionNamer
from tools import convert_well_to_row_column
if TYPE_CHECKING:
    from backend.db.models import SubmissionType
    from backend.validators.pydant import PydSample


class ClientSubmissionInfoParser(DefaultKEYVALUEParser):
    """
    Object for retrieving submitter info from "Client Info" sheet.

    :cvar range_dict: Dictionary of row/column ranges for parsing
    :type range_dict: dict
    :cvar exclude: List of keys to exclude from parsed info
    :type exclude: list
    :cvar range_dict: Dictionary to hold range information for parsing.
    :vartype range_dict: dict
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar submissiontype: The type of submission to be output. Defaults to None.
    :type submissiontype: SubmissionType | None
    :ivar *args: additional positional arguments.
    :ivar **kwargs: additional keyword arguments.
    """

    range_dict = dict(start_row = 1)
    exclude = ["submitter_info"]

    pyd_name = "PydClientSubmission"

    def __init__(self, worksheet: Worksheet, submissiontype: SubmissionType | None = None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param submissiontype: The type of submission to be output. Defaults to None.
        :type submissiontype: SubmissionType | None
        :param *args: additional positional arguments.
        :param **kwargs: additional keyword arguments.
        """
        # NOTE: parent workbook.file  must be set manually before reaching this step
        namer = ClientSubmissionNamer(filepath=worksheet._parent.file)
        if not submissiontype:
            self.submissiontype = namer.submissiontype
        else:
            self.submissiontype = submissiontype
        super().__init__(worksheet=worksheet, **kwargs)

    @property
    def parsed_info(self) -> Generator[Tuple[str, Any], None, None]:
        """
        Generates key, value tuples for rows in an excel sheet.

        :returns: Generator of key, value tuples
        :rtype: Generator[Tuple[str, Any], None, None]
        """
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
        if isinstance(output.get("submitted_date", {}).get("value", None), str):
            output['submitted_date']['value'] = parse(output['submitted_date']['value'])
        elif isinstance(output.get("submitted_date", {}).get("value", None), datetime):
            pass
        else:
            raise TypeError(f"Unrecognised type for submitted_date: {type(output.get('submitted_date', {}).get('value', None))}")
        output["submitted_date"]['value'] = datetime.combine(output['submitted_date']['value'], datetime.now().time())
        output['endrow'] = self.end_row
        yield from output.items()


class ClientSubmissionSampleParser(DefaultTABLEParser):
    """
    Default parser for a table from an Excel worksheet. 
    Extends DefaultParser to provide functionality for extracting key-value pairs columns in each row of a table.
    
    This parser extracts key (column) and row value pairs and processes them according to the specified Pydantic model.

    :cvar range_dict: Dictionary to hold range information for parsing.
    :vartype range_dict: dict
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar *args: Additional positional arguments.
    :ivar **kwargs: Additional keyword arguments. Assumed to include start_row and end_row
    """

    pyd_name = "PydSample"

    def __init__(self, worksheet: Worksheet, submissiontype: SubmissionType | None = None, *args, **kwargs):
        """
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param submissiontype: SubmissionType object to be used to import parsing rule. Defautls to None. If None will attempt to determine from the input workbook.
        :param *args: Additional positional arguments.
        :param **kwargs: Additional keyword arguments. Assumed to include start_row and end_row.
        """
        namer = ClientSubmissionNamer(filepath=worksheet._parent.file)
        self.submitter_id = kwargs.get("submitter_id", datetime.now().date().strftime("%Y-%m-%d"))
        if not submissiontype:
            self.submissiontype = namer.submissiontype
        else:
            self.submissiontype = submissiontype
        super().__init__(worksheet=worksheet, **kwargs)
        
    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        """
        Generates dictionaries of data from Excel rows.
        
        Overrides parent to convert a alphabetic row to numeric, 
        include sample.rank, sample.sample_id and sample.is_control.

        :returns: {column_header: row column value}
        :rtype: Generator[dict, None, None]
        """
        output = super().parsed_info
        for ii, sample in enumerate(output, start=1):
            try:
                if isinstance(sample["row"], str) and sample["row"].lower() in ascii_lowercase[0:8]:
                    sample["row"], _ = convert_well_to_row_column(sample["row"])
            except KeyError:
                pass
            sample['rank'] = ii
            sample['sample_id'], sample['is_control'] = self.determine_control(sample.get("sample_id", None))
            yield sample

    @staticmethod
    def check_sample_id(sample_id: str | None, submitter_id:str = "") -> Tuple[str, int]:
        """
        Enforces proper sample_id formatting and determines control status (1, 0, -1)

        :param sample_id: The input submitted sample id.
        :type sample_id: str
        :param submitter_id: Original id from the submitter. Used to determine PBS sample naming. Defaults to "".
        :type submitter_id: str
        :return: Parsed sample_id and control type as integer (1 for positive control, 0 for sample, -1 for negative control)
        :rtype: Tuple[str, int]
        """
        if sample_id is None:
            return sample_id, 0
        if not isinstance(sample_id, str):
            sample_id = str(sample_id)
        if sample_id.lower() in ["", "blank", "na", "n/a", "n\\a", "void"]:
            return "BLANK", 0
        if sample_id.lower().startswith(("atcc", "mcs", "pos", "positivecontrol", "poscontrol", "pc")):
            return sample_id, 1
        if sample_id.lower().startswith(("en", "neg", "negcontrol", "negativecontrol", "nc")):
            return sample_id, -1
        if "pbs" in sample_id.lower():
            if sample_id.lower() == "pbs-":
                output = f"PBS-{submitter_id}"
            else:
                output = sample_id
            return output, -1 
        return sample_id, 0

    def determine_control(self, sample_id: str | None) -> Tuple[str, int]:
        """
        Uses ClientSubmissionSampleParser.check_sample_id to enforce proper sample_id formatting and determine control status (1, 0, -1)
        
        :param sample_id: The input submitted sample id.
        :type sample_id: str
        :param submitter_id: Original id from the submitter. Used to determine PBS sample naming. Defaults to "".
        :type submitter_id: str
        :return: Parsed sample_id and control type as integer (1 for positive control, 0 for sample, -1 for negative control)
        :rtype: Tuple[str, int]
        """
        return ClientSubmissionSampleParser.check_sample_id(sample_id=sample_id, submitter_id=self.submitter_id)
        
    def to_pydantic(self) -> List[PydSample]:
        """
        Converts this object into a list of PydSample objects.

        :returns: [self._pyd_object(**sample) for sample in self.parsed_info if sample.get('sample_id', None)]
        :rtype: List[PydSample] 
        """
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample.get('sample_id', None)]


__all__ = ["ClientSubmissionInfoParser", "ClientSubmissionSampleParser"]