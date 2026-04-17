"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
import logging
from pathlib import Path
from pprint import pformat
from backend.excel.parsers.results_parsers.diomni_pcr_results_parser import DiomniPCRSampleParser, DiomniPCRInfoParser
from . import DefaultResultsManager

logger = logging.getLogger(f"submissions.{__name__}")

class DiomniPCRManager(DefaultResultsManager):

    def __init__(self, procedure: Procedure, parent, input_object: Path | str | None = None):
        super().__init__(procedure=procedure, parent=parent, input_object=input_object)
        self.resultstype = "Diomni PCR"
   
    def parse(self):
        self.info = {}
        samples = []
        for sheet in self.get_sheets_for_parsing(workbook=self.input_object):
            info_parser = DiomniPCRInfoParser(worksheet=sheet, procedure=self.procedure)
            self.info.update({k:v for k, v in info_parser.parsed_info})
            self.sample_parser = DiomniPCRSampleParser(worksheet=sheet, procedure=self.procedure, start_row=info_parser.end_row, date_analyzed=info_parser.date_analyzed)
            samples.extend([item for item in self.sample_parser.parsed_info])
        sample_names = list(set([list(item.keys())[0] for item in samples]))
        self.samples = []
        for sample_name in sample_names:
            dict_ = {sample_name: {}}
            samples_of_interest = [item for item in samples if list(item.keys())[0] == sample_name]
            for soi in samples_of_interest:
                dict_[sample_name] = self.deep_merge(dict_[sample_name], soi[sample_name])
            self.samples.append(dict_)
            