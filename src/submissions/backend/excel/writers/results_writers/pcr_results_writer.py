from __future__ import annotations
import logging
from pathlib import Path
from pprint import pformat
from typing import Generator, TYPE_CHECKING

from openpyxl import Workbook
from openpyxl.styles import Alignment

from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from tools import flatten_list
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")

class PCRInfoWriter(DefaultKEYVALUEWriter):

    start_row = 1

    def __init__(self, pydant_obj, proceduretype: "ProcedureType" | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, proceduretype=proceduretype, *args, **kwargs)
        self.fill_dictionary = self.pydant_obj.improved_dict()['result']
        logger.debug(pformat(self.fill_dictionary))

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=f"{self.proceduretype.name} Results")
    #     if not start_row:
    #         try:
    #             start_row = self.__class__.start_row
    #         except AttributeError as e:
    #             logger.error(f"Couldn't get start row due to {e}")
    #             start_row = 1
    #     # worksheet = workbook[f"{self.proceduretype.name} Results"]
    #     self.worksheet = workbook.create_sheet(f"{self.proceduretype.name} Results")
    #     self.worksheet = self.prewrite(self.worksheet, start_row=start_row)
    #     # self.start_row = self.delineate_start_row(start_row=start_row)
    #     # self.end_row = self.delineate_end_row(start_row=start_row)
    #     # for key, value in self.fill_dictionary['result'].items():
    #     #     # logger.debug(f"Filling in {key} with {value}")
    #     #     self.worksheet.cell(value['location']['row'], value['location']['key_column'], value=key.replace("_", " ").title())
    #     #     self.worksheet.cell(value['location']['row'], value['location']['value_column'], value=value['value'])
        return workbook


class PCRSampleWriter(DefaultTABLEWriter):

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        worksheet = workbook[f"{self.proceduretype.name} Results"]
        header_row = self.proceduretype.allowed_result_methods['PCR']['sample']['start_row']
        proto_columns = [(1, "sample"), (2, "target")]
        columns = []
        for iii, header in enumerate(self.column_headers, start=3):
            worksheet.cell(row=header_row, column=iii, value=header.replace("_", " ").title())
            columns.append((iii, header))
        columns = sorted(columns, key=lambda x: x[0])
        columns = proto_columns + columns
        # logger.debug(columns)
        all_results = flatten_list([[item for item in self.rearrange_results(result)] for result in self.pydant_obj])
        if len(all_results) > 0 :
            worksheet.cell(row=header_row, column=1, value="Sample")
            worksheet.cell(row=header_row, column=2, value="Target")
        for iii, item in enumerate(all_results, start=1):
            row = header_row + iii
            for k, v in item.items():
                column = next((col[0] for col in columns if col[1]==k), None)
                cell = worksheet.cell(row=row, column=column)
                cell.value = v
                cell.alignment = Alignment(horizontal='left')
        return workbook

    @classmethod
    def rearrange_results(cls, result) -> Generator[dict, None, None]:
        for target, values in result.result.items():
            if not isinstance(values, dict):
                continue
            values['target'] = target
            values['sample'] = result.sample_id
            yield values

    @property
    def column_headers(self):
        output = []
        for item in self.pydant_obj:
            # logger.debug(item)
            dicto: dict = item.result
            for value in dicto.values():
                if not isinstance(value, dict):
                    # logger.debug(f"Will not include {value} in column headers.")
                    continue
                for key in value.keys():
                    output.append(key)
        return sorted(list(set(output)))









