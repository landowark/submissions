"""
Parser for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
import logging
from datetime import datetime
from pprint import pformat
from typing import Generator, List, TYPE_CHECKING, Tuple
from dateutil.parser import parse
from backend.excel.parsers.results_parsers import DefaultResultsInfoParser, DefaultResultsSampleParser
from functools import cached_property
from openpyxl.worksheet.worksheet import Worksheet
from tools import convert_well_to_row_column
if TYPE_CHECKING:
    from backend.db.models.procedures import Procedure

logger = logging.getLogger(f"submissions.{__name__}")


class DiomniPCRInfoParser(DefaultResultsInfoParser):

    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        self.resultstype = "Diomni PCR"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type=self.resultstype, *args, **kwargs)
        date_analyzed = next((v for k,v in self.parsed_info if k == "analysis_date/time"),
                             datetime.combine(datetime.today(), datetime.min.time()))
        if not isinstance(date_analyzed, datetime):
            date_analyzed = parse(date_analyzed, tzinfos={"CDT":"America/Winnipeg"})
        self.date_analyzed = date_analyzed
        

class DiomniPCRSampleParser(DefaultResultsSampleParser):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, worksheet: Worksheet, date_analyzed: datetime | None = None, procedure: Procedure | None = None, *args, **kwargs):
        self.resultstype = "Diomni PCR"
        self.procedure = procedure
        self.date_analyzed = date_analyzed
        super().__init__(worksheet=worksheet, results_type=self.resultstype, *args, **kwargs)

    @cached_property
    def parsed_info(self) -> List[Tuple]:
        return list(self._generate_parsed_info())

    def _generate_parsed_info(self) -> Generator[dict, None, None]:
        output = [item for item in super().parsed_info]
        output = self.standardize_well_keys(output)
        try:
            sample_names: List[dict] = self.construct_unique_sample_dict(output)
        except KeyError as e:
            sample_names = []
            logger.error(f"Error occurred while constructing unique sample dictionary: {e}")
        for sample in sample_names:
            multi = dict(resultstype="Diomni PCR", date_analyzed=self.date_analyzed, result={})
            samples_of_interest = [item for item in output if item['sample'] == sample.get('sample') and item.get("well_position") == sample.get("well_position")]
            for soi in samples_of_interest:
                if self.worksheet.title not in multi['result'].keys():
                    multi['result'][self.worksheet.title] = {}
                if "target" in soi:
                    multi['result'][self.worksheet.title][soi['target']] = {k: v for k, v in soi.items() if k != "target" and k != "sample"}
                else:
                    multi['result'][self.worksheet.title].update({k:v for k, v in soi.items() if k != "sample"})
                try:
                    multi["row"], multi["column"] = convert_well_to_row_column(soi['well_position'])
                except (KeyError, TypeError) as e:
                    logger.error(f"Error occurred while converting well position to row and column: {e}")
            yield {sample.get('sample'): multi}

    @classmethod
    def standardize_well_keys(cls, input_list: List[dict]):
        # Process each dictionary in the list
        for entry in input_list:
            # Check for 'well' or 'wells' and move the value to 'well position'
            if "well" in entry and "well_position" not in entry:
                entry["well_position"] = entry.pop("well")
            elif "wells" in entry:
                entry["well_position"] = entry.pop("wells")
        return input_list

    @classmethod
    def assign_well_key(cls, source_dict):
        # List keys in the order of priority
        priority_keys = ["well_position", "well", "wells"]
        output = dict(sample=source_dict.get("sample", None))
        # Iterate and assign the first one found
        for key in priority_keys:
            if key in source_dict:
                output["well_position"] = source_dict[key]
                return output
        # Fallback if no keys exist
        output["well"] = None
        return output

    @classmethod
    def construct_unique_sample_dict(cls, input_list) -> list:
        output = []
        for item in input_list:
            entry = cls.assign_well_key(item)
            if entry not in output:
                output.append(entry)
        return output
