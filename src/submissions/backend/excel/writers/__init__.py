import logging
import re
from io import BytesIO
from pathlib import Path
from pprint import pformat
from typing import Any

from openpyxl.reader.excel import load_workbook
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame

from backend.db.models import BaseClass
from backend.validators.pydant import PydBaseClass

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultWriter(object):

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.filepath.stem}>"

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        # self.filepath = output_filepath
        self.pydant_obj = pydant_obj
        self.fill_dictionary = pydant_obj.improved_dict()
        if range_dict:
            self.range_dict = range_dict
        else:
            self.range_dict = self.__class__.default_range_dict

    @classmethod
    def stringify_value(cls, value:Any) -> str:
        match value:
            case x if issubclass(value.__class__, BaseClass):
                value = value.name
            case x if issubclass(value.__class__, PydBaseClass):
                value = value.name
            case dict():
                try:
                    value = value['value']
                except ValueError:
                    try:
                        value = value['name']
                    except ValueError:
                        value = value.__str__()
            case _:
                value = str(value)
        return value

    @classmethod
    def prettify_key(cls, value:str) -> str:
        value = value.replace("type", " type").strip()
        value = value.title()
        return value


    def write_to_workbook(self, workbook: Workbook):
        logger.debug(f"Writing to workbook with {self.__class__.__name__}")
        return workbook


class DefaultKEYVALUEWriter(DefaultWriter):

    default_range_dict = [dict(
        start_row=2,
        end_row=18,
        key_column=1,
        value_column=2,
        sheet="Sample List"
    )]

    @classmethod
    def check_location(cls, locations: list, sheet: str):
        return any([item['sheet'] == sheet for item in locations])

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook)
        for rng in self.range_dict:
            rows = range(rng['start_row'], rng['end_row'] + 1)
            worksheet = workbook[rng['sheet']]
            try:
                for ii, (k, v) in enumerate(self.fill_dictionary.items(), start=rng['start_row']):
                    # match v:
                    #     case x if issubclass(v.__class__, BaseClass):
                    #         v = v.name
                    #     case x if issubclass(v.__class__, PydBaseClass):
                    #         v = v.name
                    #     case dict():
                    #         try:
                    #             v = v['value']
                    #         except ValueError:
                    #             try:
                    #                 v = v['name']
                    #             except ValueError:
                    #                 v = v.__str__()
                    #     case _:
                    #         pass
                    try:
                        worksheet.cell(column=rng['key_column'], row=rows[ii], value=self.prettify_key(k))
                        worksheet.cell(column=rng['value_column'], row=rows[ii], value=self.stringify_value(v))
                    except IndexError:
                        logger.error(f"Not enough rows: {len(rows)} for index {ii}")
            except ValueError as e:
                logger.error(self.fill_dictionary)
                raise e
        return workbook

class DefaultTABLEWriter(DefaultWriter):

    default_range_dict = [dict(
        header_row=19,
        sheet="Sample List"
    )]

    @classmethod
    def get_row_count(cls, worksheet: Worksheet, range_dict:dict):
        if "end_row" in range_dict.keys():
            list_df = DataFrame([item for item in worksheet.values][range_dict['header_row'] - 1:range_dict['end_row'] - 1])
        else:
            list_df = DataFrame([item for item in worksheet.values][range_dict['header_row'] - 1:])
        row_count = list_df.shape[0]
        return row_count

    def pad_samples_to_length(self, row_count, column_names):
        from backend import PydSample
        output_samples = []
        for iii in range(1, row_count + 1):
            logger.debug(f"Submission rank: {iii}")
            if isinstance(self.pydant_obj, list):
                iterator = self.pydant_obj
            else:
                iterator = self.pydant_obj.sample
            try:
                sample = next((item for item in iterator if item.submission_rank == iii))
            except StopIteration:
                sample = PydSample(sample_id="")
                for column in column_names:
                    setattr(sample, column[0], "")
                sample.submission_rank = iii
            logger.debug(f"Appending {sample.sample_id}")
            logger.debug(f"Iterator now: {[item.submission_rank for item in iterator]}")
            output_samples.append(sample)
        return sorted(output_samples, key=lambda x: x.submission_rank)

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook)
        for rng in self.range_dict:
            list_worksheet = workbook[rng['sheet']]
            column_names = [(item.value.lower().replace(" ", "_"), item.column) for item in list_worksheet[rng['header_row']] if item.value]
            for iii, object in enumerate(self.pydant_obj, start=1):
                # logger.debug(f"Writing object: {object}")
                write_row = rng['header_row'] + iii
                for column in column_names:
                    if column[0].lower() in ["well", "row", "column"]:
                        continue
                    write_column = column[1]
                    try:
                        value = getattr(object, column[0].lower().replace(" ", ""))
                    except AttributeError:
                        try:
                            value = getattr(object, column[0].lower().replace("_", ""))
                        except AttributeError:
                            value = ""
                    # logger.debug(f"{column} Writing {value} to row {write_row}, column {write_column}")
                    list_worksheet.cell(row=write_row, column=write_column, value=self.stringify_value(value))
        return workbook


from .clientsubmission_writer import ClientSubmissionInfoWriter, ClientSubmissionSampleWriter




