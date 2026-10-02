"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from pathlib import Path
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from backend.excel.parsers.results_parsers.diomni_pcr_results_parser import DiomniPCRSampleParser, DiomniPCRInfoParser
from tools import get_application_from_parent
from frontend.widgets import select_open_file
from . import DefaultResultsManager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.validators.pydant import PydProcedure


class DiomniPCRManager(DefaultResultsManager):

    resultstype = "Diomni PCR"

    def __init__(self, procedure: PydProcedure, parent, input_object: Path | str | Workbook | Worksheet | None = None):
        if input_object is None:
            input_object = select_open_file(filetypes="Excel Files (*.xlsx)", obj=get_application_from_parent(parent))
        super().__init__(procedure=procedure, parent=parent, input_object=input_object)
        
    def parse(self):
        self.info = {}
        samples = []
        # Sheets are selected from sheetnames in the workbookby user with a gui window.
        for sheet in self.get_sheets_for_parsing(workbook=self.input_object):
            self.info_parser = DiomniPCRInfoParser(worksheet=sheet, procedure=self.procedure)
            """ 
            Info parser performs DefaultResultsInfoParser.parsed_info and returns a generator of tuples. The generator is converted to a dictionary and stored in self.info.
            In short, DefaultKEYVALUEParser takes a range of rows and takes the first column as keys and the second column as values. It returns a generator of tuples. 
            The generator is converted to a dictionary and stored in self.info.
            """
            self.info.update({k:v for k, v in self.info_parser.parsed_info})
            self.sample_parser = DiomniPCRSampleParser(worksheet=sheet, procedure=self.procedure, start_row=self.info_parser.end_row, date_analyzed=self.info_parser.date_analyzed)
            """
            Sample parser performs DiomniPCRSampleParser._generate_parsed_info and returns a generator of dictionaries. The generator is converted to a list and stored in samples.
            In short, DefaultTABLEParser takes a range of rows and takes the first row as keys and the subsequent rows as values. It returns a generator of dictionaries.
            The generator is converted to a list and stored in samples.
            """
            samples.extend([item for item in self.sample_parser.parsed_info])
        sample_names = list(set([list(item.keys())[0] for item in samples]))
        self.samples = []
        for sample_name in sample_names:
            dict_ = {sample_name: {}}
            samples_of_interest = [item for item in samples if list(item.keys())[0] == sample_name]
            for soi in samples_of_interest:
                dict_[sample_name] = self.deep_merge(dict_[sample_name], soi[sample_name])
            self.samples.append(dict_)
            
__all__ = ["DiomniPCRManager"]