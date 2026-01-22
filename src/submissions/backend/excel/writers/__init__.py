"""
Module for default excel writers
"""
from __future__ import annotations
from operator import itemgetter
import logging, sys
from datetime import datetime, date
from pprint import pformat
from typing import Any, Literal
from openpyxl.styles import Alignment, PatternFill
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame
from backend.db.models import BaseClass, ProcedureType
from backend.validators.pydant import PydBaseClass
from tools import flatten_list, create_plate_grid, sort_dict_by_list

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultWriter(object):

    def __repr__(self):
        try:
            return f"{self.__class__.__name__}<{self.filepath.stem}>"
        except AttributeError:
            return f"{self.__class__.__name__}<Unknown Filepath>"

    def __init__(self, pydant_obj, proceduretype: ProcedureType | None = None, *args, **kwargs):
        self.pydant_obj = pydant_obj
        self.proceduretype = proceduretype
        logger.debug(f"{proceduretype} -> {self.proceduretype}")

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
            case bytes() | list():
                value = None
            case datetime() | date():
                value = value.strftime("%Y-%m-%d %H:%M:%S")
            case _:
                value = str(value)
        return value

    @classmethod
    def prettify_key(cls, key: str) -> str:
        key = key.replace("type", " type").strip()
        key = key.replace("_", " ")
        key = key.title()
        key = key.replace("Id", "ID")
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
        if self.sheet not in workbook.sheetnames:
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
        data_length = len(self.fill_dictionary)
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
            self.worksheet.cell(column=1, row=ii, value=self.prettify_key(k))
            self.worksheet.cell(column=2, row=ii, value=value)
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        worksheet = self.columns_best_fit(worksheet=worksheet)
        return worksheet


class DefaultTABLEWriter(DefaultWriter):
    sheet = "Client Info"
    start_row = 19
    header_order = []
    exclude = []

    def get_row_count(self, start_row: int = 1):
        list_df = DataFrame([item for item in self.worksheet.values][start_row - 1:])
        row_count = list_df.shape[0]
        return row_count

    def delineate_end_row(self, start_row: int = 1) -> int:
        end_row = start_row + len(self.pydant_obj) + 1
        return end_row

    # def pad_samples_to_length(self, row_count,
    #                           mode: Literal["submission", "procedure"] = "submission"):  #, column_names):
    #     from backend.validators.pydant import PydProcedureSampleAssociation
    #     output_samples = []
    #     for iii in range(1, row_count + 1):
    #         if isinstance(self.pydant_obj, list):
    #             iterator = self.pydant_obj
    #         else:
    #             if mode == "submission":
    #                 iti = "clientsubmission"
    #             else:
    #                 iti = mode
    #             iterator = getattr(self.pydant_obj.sql_instance, f"{iti}sampleassociation")
    #         try:
    #             sample = next((item.to_pydantic() for item in iterator if getattr(item, f"{mode}_rank") == iii))
    #         except StopIteration:
    #             sample = PydProcedureSampleAssociation(sample_id="")
    #             setattr(sample, f"{mode}_rank", iii)
    #             if mode == "procedure":
    #                 if all([item.row for item in self.pydant_obj.sample]):
    #                     rows, columns = self.pydant_obj.rows_columns_count
    #                     grid = create_plate_grid(rows=rows, columns=columns)
    #                     sample.row, sample.column = grid[sample.procedure_rank]
    #         output_samples.append(sample)
    #     logger.debug(f"Padded samples: {pformat(output_samples)}")
    #     return sorted(output_samples, key=lambda x: getattr(x, f"{mode}_rank"))

    
            
    

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row, *args, **kwargs)
        self.header_list = self.sort_header_row(list(set(flatten_list([item.fields for item in self.pydant_obj]))))
        logger.debug(f"Header list: {self.header_list}")
        self.worksheet = self.write_header_row(worksheet=self.worksheet)
        for iii, object in enumerate(self.pydant_obj, start=1):
            write_row = self.start_row + iii
            for header in self.header_list:
                try:
                    column = next((cell for cell in self.worksheet[self.start_row] if
                                   cell.value == header.replace("_", " ").title()))
                except StopIteration:
                    logger.warning(f'Could not find column for {header.replace("_", " ").title()}')
                    continue
                column = column.column
                try:
                    value = object.improved_dict[header.lower().replace(" ", "")]
                except (AttributeError, KeyError) as e:
                    try:
                        value = object.improved_dict[header.lower().replace(" ", "_")]
                    except (AttributeError, KeyError):
                        value = ""
                # logger.debug(f"Value for {header} = {value}")
                value = self.stringify_value(value)
                # logger.debug(f"Output value: {value}")
                self.worksheet.cell(row=write_row, column=column, value=value)
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    @classmethod
    def sort_header_row(cls, header_list: list) -> list:
        output = []
        for item in cls.header_order:
            if item in [header for header in header_list if header not in cls.exclude]:
                output.append(header_list.pop(header_list.index(item)))
        return output + sorted([item for item in header_list if item not in cls.exclude])

    def write_header_row(self, worksheet: Worksheet) -> Worksheet:
        for iii, header in enumerate(self.header_list, start=1):
            worksheet.cell(row=self.start_row, column=iii, value=header.replace("_", " ").title())
            worksheet.cell(row=self.start_row, column=iii).alignment = Alignment(horizontal='center')
            worksheet.cell(row=self.start_row, column=iii).fill = PatternFill(start_color='2DE733', end_color='2DE733', fill_type="solid")
        return worksheet

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        worksheet = self.columns_best_fit(worksheet=worksheet)
        return worksheet


from .procedure_writers import ProcedureInfoWriter, ProcedureSampleWriter, ProcedureReagentWriter, ProcedureEquipmentWriter
from .results_writers import (
    PCRInfoWriter, PCRSampleWriter,
    QubitInfoWriter, QubitSampleWriter
)
from .clientsubmission_writer import ClientSubmissionInfoWriter, ClientSubmissionSampleWriter
