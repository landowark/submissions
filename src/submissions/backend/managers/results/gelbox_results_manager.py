"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from backend.managers.results import DefaultImageManager


class GelManager(DefaultImageManager):

    resultstype = "Gel Box"
            
    def parse(self):
        self.info = {}
        samples = []
        for sheet in self.get_sheets_for_parsing(workbook=self.input_object):
            self.info_parser = DiomniPCRInfoParser(worksheet=sheet, procedure=self.procedure)
            self.info.update({k:v for k, v in self.info_parser.parsed_info})
            self.sample_parser = DiomniPCRSampleParser(worksheet=sheet, procedure=self.procedure, start_row=self.info_parser.end_row, date_analyzed=self.info_parser.date_analyzed)
            samples.extend([item for item in self.sample_parser.parsed_info])
        sample_names = list(set([list(item.keys())[0] for item in samples]))
        self.samples = []
        for sample_name in sample_names:
            dict_ = {sample_name: {}}
            samples_of_interest = [item for item in samples if list(item.keys())[0] == sample_name]
            for soi in samples_of_interest:
                dict_[sample_name] = self.deep_merge(dict_[sample_name], soi[sample_name])
            self.samples.append(dict_)
            
__all__ = ["GelBoxManager"]