"""
Parser for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from datetime import datetime
from typing import Generator, List, TYPE_CHECKING, Tuple
from dateutil.parser import parse
from backend.excel.parsers.results_parsers import DefaultResultsInfoParser, DefaultResultsSampleParser
from functools import cached_property
from openpyxl.worksheet.worksheet import Worksheet
from tools import convert_well_to_row_column
if TYPE_CHECKING:
    from submissions.backend.db.models.procedures import Procedure


class DiomniPCRInfoParser(DefaultResultsInfoParser):
    """
    Class to parse meta information from Diomni PCR results in an Excel worksheet.
    This parser extracts key-value pairs and processes them according to the specified Pydantic model.

    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar procedure: The associated procedure object. If None, it will be determined from the worksheet.
    :type procedure: Procedure | None
    
    """
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
    """
    Object to pull data from Design and Analysis PCR export file. Ultimate parent class: DefaultTABLEParser
    This parser extracts column-value pairs for each table row and processes them according to the specified Pydantic model.
    
    :cvar pyd_name: Name of the Pydantic model associated with this parser.
    :type pyd_name: str
    :ivar worksheet: The Excel worksheet to parse.
    :type worksheet: Worksheet
    :ivar date_analyzed: The date and time when the analysis was performed. If None, it will be determined from the worksheet.
    :type date_analyzed: datetime | None
    :ivar procedure: The associated procedure object. If None, it will be determined from the worksheet.
    :type procedure: Procedure | None
    """

    def __init__(self, worksheet: Worksheet, date_analyzed: datetime | None = None, procedure: Procedure | None = None, *args, **kwargs):
        """        
        :param worksheet: The Excel worksheet to parse.
        :type worksheet: Worksheet
        :param date_analyzed: The date and time when the analysis was performed. If None, it will be determined from the worksheet.
        :type date_analyzed: datetime | None
        :param procedure: The associated procedure object. If None, it will be determined from the worksheet.
        :type procedure: Procedure | None
        """
        self.resultstype = "Diomni PCR"
        self.procedure = procedure
        self.date_analyzed = date_analyzed
        super().__init__(worksheet=worksheet, results_type=self.resultstype, *args, **kwargs)

    @cached_property
    def parsed_info(self) -> List[Tuple]:
        """
        Returns the parsed information as a list of tuples.
        Caches the result upon first access.

        :returns: list(self._generate_parsed_info())
        :rtype: List[Tuple] 
        """
        return list(self._generate_parsed_info())

    def _generate_parsed_info(self) -> Generator[dict, None, None]:
        """
        Generates dictionaries of data from Excel rows, standardizes well keys, and constructs unique sample dictionaries.

        :returns: Generator of results dictionaries for each unique sample.
        :rtype: Generator[dict, None, None]
        """
        output = [item for item in super().parsed_info]
        output = self.standardize_well_keys(output)
        try:
            sample_names: List[dict] = self.construct_unique_sample_dict(output)
        except KeyError as e:
            sample_names = []
            logger.exception(f"Error occurred while constructing unique sample dictionary: {e}")
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
                    logger.exception(f"Error occurred while converting well position to row and column: {e}")
            yield {sample.get('sample'): multi}

    @classmethod
    def standardize_well_keys(cls, input_list: List[dict]) -> List[dict]:
        """
        Standardizes keys for fields related to well positions in a list of dictionaries. 
        It checks for the presence of 'well' or 'wells' keys and moves their values to a new key 'well_position'.

        :param input_list: List of dictionaries containing sample data.
        :type input_list: List[dict]
        :returns: List of dictionaries with standardized well position keys.
        :rtype: List[dict]
        """
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
        """
        Assigns a well position key to the output dictionary based on the presence of specific keys in the source dictionary.
        It prioritizes the keys in the order of "well_position", "well", and "wells". If none of these keys are present, it assigns None to the "well" key in the output.

        :param source_dict: The source dictionary containing sample data.
        :type source_dict: dict
        :returns: A dictionary with the assigned well position key and sample information.
        :rtype: dict
        """
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
    def construct_unique_sample_dict(cls, input_list: List[dict]) -> List[dict]:
        """
        Makes a list of unique sample dictionaries based on the 'sample' and 'well_position' keys from the input list of dictionaries.
        It uses the assign_well_key method to standardize the well position key for each dictionary
        and ensures that only unique combinations of 'sample' and 'well_position' are included in the output list.

        :param input_list: List of dictionaries containing sample data.
        :type input_list: List[dict]
        :returns: List of unique sample dictionaries with standardized well position keys.
        :rtype: List[dict]
        """
        output = []
        for item in input_list:
            entry = cls.assign_well_key(item)
            if entry not in output:
                output.append(entry)
        return output

__all__ = ["DiomniPCRInfoParser", "DiomniPCRSampleParser"]