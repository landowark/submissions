"""
Module for default excel writers
"""
from __future__ import annotations
import logging, sys
from datetime import datetime, date
from pprint import pformat
from typing import Any, TYPE_CHECKING
import numpy as np
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame
from backend.db.models import BaseClass
from openpyxl.utils.dataframe import dataframe_to_rows
from backend.validators.pydant import PydBaseClass
from tools import flatten_list, sort_dict_by_list, row_map, handle_keys
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultWriter(object):

    def __repr__(self):
        try:
            return f"{self.__class__.__name__}<{self.filepath.stem}>"
        except AttributeError:
            return f"{self.__class__.__name__}<Unknown Filepath>"

    def __init__(self, pydant_obj, *args, **kwargs):
        self.pydant_obj = pydant_obj
        self.proceduretype = kwargs.get("proceduretype", None)

    @classmethod
    def stringify_value(cls, value: Any) -> str:
        if isinstance(value, dict):
            try:
                value = value['value']
            except (KeyError, ValueError):
                try:
                    value = value['name']
                except (KeyError, ValueError):
                    return
        match value:
            case x if issubclass(value.__class__, BaseClass):
                value = value.name
            case x if issubclass(value.__class__, PydBaseClass):
                value = value.name
            case bytes(): 
                value = None
            case list():
                value = "\\n".join([str(item) for item in value])
            case datetime() | date():
                try:
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    value = "Time not available."
            case _:
                value = str(value)
        return value

    @classmethod
    def prettify_key(cls, key: str) -> str:
        key = key.replace("type", " type").strip()
        key = key.replace("role", " role").strip()
        key = key.replace("version", " version").strip()
        key = key.replace("lot", " lot").strip()
        key = key.replace("_", " ")
        key = key.title()
        key = key.replace(" Id", " ID")
        return key

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs):
        if not start_row:
            try:
                start_row = self.__class__.start_row
            except AttributeError as e:
                logger.error(f"Couldn't get start row due to {e}")
                start_row = 1
        if not sheet:
            sheet = self.__class__.sheet
        self.sheet = sheet
        sheetnames = workbook.sheetnames
        if isinstance(sheetnames, property):
            try:
                sheetnames = sheetnames.fget(workbook)
            except Exception as e:
                logger.error(f"Couldn't resolve workbook sheetnames property due to {e}")
                sheetnames = []
        if self.sheet not in sheetnames:
            try:
                self.worksheet = workbook["Sheet"]
                self.worksheet.title = self.sheet
            except KeyError:
                self.worksheet = workbook.create_sheet(self.sheet)
        else:
            self.worksheet = workbook[self.sheet]
        self.worksheet = self.prewrite(self.worksheet, start_row=start_row)
        self.start_row = self.delineate_start_row(start_row=start_row)
        # NOTE: Declared in child classes
        self.end_row = self.delineate_end_row(start_row=start_row)
        return workbook

    def delineate_start_row(self, start_row: int = 1) -> int:
        """
        Gets the first black row.
        Args:
            start_row (int): row to start looking at.

        Returns:
            int
        """
        for iii, row in enumerate(self.worksheet.iter_rows(min_row=start_row), start=start_row):
            if all([item.value is None for item in row]):
                return iii
        if self.worksheet.max_row == 1:
            return self.worksheet.max_row + 1
        else:
            return self.worksheet.max_row + 2

    def prewrite(self, worksheet: Worksheet, start_row: int) -> Worksheet:
        return worksheet

    def columns_best_fit(self, worksheet: Worksheet) -> None:
        """
        Make all columns best fit
        """
        for col in worksheet.columns:
            setlen = 0
            column = col[0].column_letter  # Get the column name
            for cell in col:
                if len(str(cell.value)) > setlen:
                    setlen = len(str(cell.value))
            set_col_width = setlen + 5
            # Note: Setting the column width
            worksheet.column_dimensions[column].width = set_col_width
        return worksheet


class DefaultKEYVALUEWriter(DefaultWriter):
    sheet = "Client Info"
    start_row = 2
    exclude = []
    key_order = []

    def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        self.fill_dictionary = self.pydant_obj.improved_dict

    def delineate_end_row(self, start_row: int = 1):
        data_length = len([key for key in self.fill_dictionary.keys() if key not in self.__class__.exclude])
        return data_length + start_row

    @classmethod
    def check_location(cls, locations: list, sheet: str):
        return any([item['sheet'] == sheet for item in locations])

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row)
        dictionary = {k: v for k, v in self.fill_dictionary.items() if k not in self.__class__.exclude}
        dictionary =  sort_dict_by_list(dictionary=dictionary, order_list=self.key_order)
        for ii, (k, v) in enumerate(dictionary.items(), start=self.start_row):
            value = self.stringify_value(value=v)
            if value is None:
                continue
            self.worksheet.cell(column=1, row=ii, value=handle_keys(k))
            self.worksheet.cell(column=2, row=ii, value=self.stringify_value(value))
        self.worksheet = self.postwrite(self.worksheet)
        
        return workbook

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        worksheet = self.columns_best_fit(worksheet=worksheet)
        return worksheet


class DefaultTABLEWriter(DefaultWriter):

    sheet = "Client Info"
    # start_row = 19
    # header_order = []
    # exclude = []

    def get_row_count(self, start_row: int = 1):
        list_df = DataFrame([item for item in self.worksheet.values][start_row - 1:])
        row_count = list_df.shape[0]
        return row_count

    def delineate_end_row(self, start_row: int = 1) -> int:
        end_row = start_row + len(self.pydant_obj) + 2
        return end_row

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row, *args, **kwargs)
        self.header_list = self.sort_header_row(list(set(flatten_list([item.fields for item in self.pydant_obj]))))
        records = [getattr(item, 'improved_dict', {}) for item in self.pydant_obj]
        df = DataFrame(records)[self.header_list]
        df.replace("", np.nan, inplace=True)
        # Identify columns where ALL values are zero
        is_all_zero = (df == 0).all()

        # Identify columns where ANY value is a list
        is_list_col = df.map(lambda x: isinstance(x, list)).all()

        # Drop columns that meet either condition
        df = df.loc[:, ~(is_all_zero | is_list_col)]
        # Drop columns where all values are NaN (the data is empty)
        df.dropna(axis=1, how='all', inplace=True)
        df.fillna("", inplace=True)
        # Rename column Headers.
        # df.columns = df.columns.str.replace('_', ' ').str.title()
        df = df.rename(columns=handle_keys)

        rows = dataframe_to_rows(df, index=False, header=True)
        for r_idx, row in enumerate(rows, start_row + 1 ):
            for c_idx, value in enumerate(row, 1):
                self.worksheet.cell(row=r_idx, column=c_idx, value=self.stringify_value(value))
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    @classmethod
    def sort_header_row(cls, header_list: list) -> list:
        output = []
        for item in cls.header_order:
            if item in [header for header in header_list if header not in cls.exclude]:
                output.append(header_list.pop(header_list.index(item)))
        return output + sorted([item for item in header_list if item not in cls.exclude])

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        worksheet = self.columns_best_fit(worksheet=worksheet)
        worksheet = self.colour_start_row(worksheet=worksheet)
        return worksheet
    
    def colour_start_row(self, worksheet: Worksheet) -> Worksheet:
        font = Font(bold=True, color="ffffffff")
        fill = PatternFill(start_color='376589', end_color='376589', fill_type="solid")
        align = Alignment(horizontal="center")
        logger.debug(self.start_row)
        for cell in worksheet[self.start_row]:
            cell.font = font
            cell.fill = fill
            cell.alignment = align
        return worksheet




from .procedure_writers import ProcedureInfoWriter, ProcedureSampleWriter, ProcedureReagentWriter, ProcedureEquipmentWriter
from .results_writers import (
    DiomniPCRInfoWriter, DiomniPCRSampleWriter,
    QubitInfoWriter, QubitSampleWriter
)
from .clientsubmission_writer import ClientSubmissionInfoWriter, ClientSubmissionSampleWriter
