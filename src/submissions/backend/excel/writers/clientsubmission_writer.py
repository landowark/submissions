import logging
from pathlib import Path
from pprint import pformat

from openpyxl.workbook import Workbook

from . import DefaultKEYVALUEWriter, DefaultTABLEWriter

logger = logging.getLogger(f"submissions.{__name__}")


class ClientSubmissionInfoWriter(DefaultKEYVALUEWriter):

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        logger.debug(f"{self.__class__.__name__} recruited!")

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        # workbook = super().write_to_workbook(workbook=workbook)
        logger.debug(f"Skipped super.")
        for rng in self.range_dict:
            worksheet = workbook[rng['sheet']]
            for key, value in self.fill_dictionary.items():
                logger.debug(f"Checking: key {key}, value {str(value)[:64]}")
                if isinstance(value, bytes):
                    continue
                try:
                    check = self.check_location(value['location'], rng['sheet'])
                except TypeError:
                    check = False
                if not check:
                    continue
                    # relevant_values[k] = v
                logger.debug(f"Location passed for {value['location']}")
                for location in value['location']:
                    if location['sheet'] != rng['sheet']:
                        continue
                    logger.debug(f"Writing {value} to row {location['row']}, column {location['value_column']}")
                    try:
                        worksheet.cell(location['row'], location['value_column'], value=value['value'])
                    except KeyError:
                        worksheet.cell(location['row'], location['value_column'], value=value['name'])
        return workbook


class ClientSubmissionSampleWriter(DefaultTABLEWriter):

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook)
        for rng in self.range_dict:
            list_worksheet = workbook[rng['sheet']]
            row_count = self.get_row_count(list_worksheet, rng)
            column_names = [(item.value.lower().replace(" ", "_"), item.column) for item in list_worksheet[rng['header_row']] if item.value]
            samples = self.pad_samples_to_length(row_count=row_count, column_names=column_names)
            for sample in samples:
                # logger.debug(f"Writing sample: {sample}")
                write_row = rng['header_row'] + sample.submission_rank
                for column in column_names:
                    if column[0].lower() in ["well", "row", "column"]:
                        continue
                    write_column = column[1]
                    try:
                        # value = sample[column[0]]
                        value = getattr(sample, column[0])
                    except AttributeError:
                        value = ""
                    # logger.debug(f"{column} Writing {value} to row {write_row}, column {write_column}")
                    list_worksheet.cell(row=write_row, column=write_column, value=value)
        return workbook




