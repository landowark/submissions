"""
Writers for PCR results from Design and Analysis Software
"""
from __future__ import annotations
import logging
from pprint import pformat
from typing import Generator
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Alignment, Font, PatternFill
from pandas import DataFrame
from . import DefaultResultsInfoWriter, DefaultResultsSampleWriter

logger = logging.getLogger(f"submissions.{__name__}")


class DiomniPCRInfoWriter(DefaultResultsInfoWriter):

    pass

    

class DiomniPCRSampleWriter(DefaultResultsSampleWriter):

    # def write_to_workbook(self, workbook: Workbook) -> Workbook:
    #     workbook = super().write_to_workbook(workbook)
    #     resultstype = next((item for item in self.proceduretype.allowed_result_methods if item['name'] == "Diomni PCR"), dict(header_row=1))
    #     header_row = resultstype.get('header_row', 1)
    #     proto_columns = [(1, "sample"), (2, "target")]
    #     columns = []
    #     for iii, header in enumerate(self.column_headers, start=3):
    #         self.worksheet.cell(row=header_row, column=iii, value=header.replace("_", " ").title())
    #         columns.append((iii, header))
    #     columns = sorted(columns, key=lambda x: x[0])
    #     columns = proto_columns + columns
    #     all_results = flatten_list([[item for item in self.rearrange_results(result)] for result in self.pydant_obj])
    #     if len(all_results) > 0 :
    #         self.worksheet.cell(row=header_row, column=1, value="Sample")
    #         self.worksheet.cell(row=header_row, column=2, value="Target")
    #     for iii, item in enumerate(all_results, start=1):
    #         row = header_row + iii
    #         for k, v in item.items():
    #             column = next((col[0] for col in columns if col[1]==k), None)
    #             cell = self.worksheet.cell(row=row, column=column)
    #             cell.value = v
    #             cell.alignment = Alignment(horizontal='left')
    #     return workbook

    # @classmethod
    # def rearrange_results(cls, result) -> Generator[dict, None, None]:
    #     for target, values in result.result.items():
    #         if not isinstance(values, dict):
    #             continue
    #         values['target'] = target
    #         values['sample'] = result.sampleprocedureassociation.sample.sample_id
    #         yield values

    # @property
    # def column_headers(self):
    #     output = []
    #     for item in self.pydant_obj:
    #         dicto: dict = item.result
    #         for value in dicto.values():
    #             if not isinstance(value, dict):
    #                 continue
    #             for key in value.keys():
    #                 output.append(key)
    #     return sorted(list(set(output)))

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None, start_row: int = 1, *args, **kwargs) -> Workbook:
        # super().write_to_workbook(workbook, sheet, start_row, *args, **kwargs)
        font = Font(bold=True, color="ffffffff", size=16)
        fill = PatternFill(start_color='376589', end_color='376589', fill_type="solid")
        align = Alignment(horizontal="center")
        start_row += 1
        self.start_row = start_row + 1
        try:
            self.worksheet = workbook[self.sheet]
        except KeyError:
            self.worksheet = workbook.create_sheet(title=self.sheet)
        for df in self.create_results_dataframes():
            rows = dataframe_to_rows(df, index=False)
            cell = self.worksheet.cell(row=start_row, column=1, value=df.caption)
            cell.font = font
            cell.fill = fill
            cell.alignment = align
            for row_data in rows:
                start_row += 1
                for col_idx, value in enumerate(row_data, start=1):
                    self.worksheet.cell(row=start_row, column=col_idx, value=value)
                # Move to the next row immediately after writing the columns
        self.postwrite(worksheet=self.worksheet)
        return workbook


    def create_results_dataframes(self) -> Generator[DataFrame, None, None]:
        """Flattens PydResults objects into a unified DataFrame.

        Each target (e.g., N1, N2) becomes a distinct row.
        """
        
        sheets = {key for obj in self.pydant_obj for key in obj.result.keys()}
        logger.debug(sheets)
        for sheet in sheets:
            all_rows = []
            for obj in self.pydant_obj:
                # Extract base metadata from the object
                metadata = {
                    "resultstype": obj.resultstype,
                    "procedure": obj.procedure,
                    "sample": obj.sample,
                }
                # Navigate to the target dictionary
                target_call = obj.result.get(sheet, {})
                if isinstance(target_call, dict):
                    for target_name, target_data in target_call.items():
                        # Merge metadata, the target key, and target metrics
                        row_data = {"Sample ID": metadata['sample'], "Target": target_name, **target_data}
                        all_rows.append(row_data)
            # Convert the list of dictionaries into a DataFrame
            df = DataFrame(all_rows)
            if df.empty:
                continue
            df.caption = sheet
            logger.debug(df)
            yield df
