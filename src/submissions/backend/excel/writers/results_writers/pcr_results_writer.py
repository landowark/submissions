import logging
from pathlib import Path
from typing import Generator

from openpyxl import Workbook
from openpyxl.styles import Alignment

from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from tools import flatten_list

logger = logging.getLogger(f"submissions.{__name__}")

class PCRInfoWriter(DefaultKEYVALUEWriter):

    default_range_dict = [dict(
        start_row=1,
        end_row=24,
        key_column=1,
        value_column=2,
        sheet="Results"
    )]

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        worksheet = workbook[f"{self.proceduretype.name} Results"]
        for key, value in self.fill_dictionary['result'].items():
            logger.debug(f"Filling in {key} with {value}")
            worksheet.cell(value['location']['row'], value['location']['key_column'], value=key.replace("_", " ").title())
            worksheet.cell(value['location']['row'], value['location']['value_column'], value=value['value'])
        return workbook


class PCRSampleWriter(DefaultTABLEWriter):

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        worksheet = workbook[f"{self.proceduretype.name} Results"]
        header_row = self.proceduretype.allowed_result_methods['PCR']['sample']['header_row']
        proto_columns = [(1, "sample"), (2, "target")]
        columns = []
        for iii, header in enumerate(self.column_headers, start=3):
            worksheet.cell(row=header_row, column=iii, value=header.replace("_", " ").title())
            columns.append((iii, header))
        columns = sorted(columns, key=lambda x: x[0])
        columns = proto_columns + columns
        logger.debug(columns)
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
            values['target'] = target
            values['sample'] = result.sample_id
            yield values

    @property
    def column_headers(self):
        output = []
        for item in self.pydant_obj:
            logger.debug(item)
            dicto: dict = item.result
            for value in dicto.values():
                for key in value.keys():
                    output.append(key)
        return sorted(list(set(output)))









