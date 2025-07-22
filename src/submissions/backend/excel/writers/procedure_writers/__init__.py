from __future__ import annotations
import logging
from pprint import pformat

from openpyxl.workbook import Workbook

from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter

logger = logging.getLogger(f"submissions.{__name__}")

class ProcedureInfoWriter(DefaultKEYVALUEWriter):

    default_range_dict = [dict(
        start_row=1,
        end_row=6,
        key_column=1,
        value_column=2,
        sheet=""
    )]

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        exclude = ['control', 'equipment', 'excluded', 'id', 'misc_info', 'plate_map', 'possible_kits', 'procedureequipmentassociation',
                   'procedurereagentassociation', 'proceduresampleassociation', 'proceduretipsassociation', 'reagent', 'reagentrole',
                   'results', 'sample', 'tips']
        self.fill_dictionary = {k: v for k, v in self.fill_dictionary.items() if k not in exclude}
        logger.debug(pformat(self.fill_dictionary))
        for rng in self.range_dict:
            if "sheet" not in rng or rng['sheet'] == "":
                rng['sheet'] = f"{pydant_obj.proceduretype.name} Quality"


class ProcedureReagentWriter(DefaultTABLEWriter):

    default_range_dict = [dict(
        header_row=8
    )]

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        for rng in self.range_dict:
            if "sheet" not in rng:
                rng['sheet'] = f"{pydant_obj.proceduretype.name} Quality"
        self.pydant_obj = self.pydant_obj.reagent


class ProcedureEquipmentWriter(DefaultTABLEWriter):

    default_range_dict = [dict(
        header_row=14
    )]

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        for rng in self.range_dict:
            if "sheet" not in rng:
                rng['sheet'] = f"{pydant_obj.proceduretype.name} Quality"
        self.pydant_obj = self.pydant_obj.equipment


class ProcedureSampleWriter(DefaultTABLEWriter):

    default_range_dict = [dict(
        header_row=21
    )]

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        for rng in self.range_dict:
            if "sheet" not in rng:
                rng['sheet'] = f"{pydant_obj.proceduretype.name} Quality"
        self.pydant_obj = self.pydant_obj.sample

    def write_to_workbook(self, workbook: Workbook) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook)
        for rng in self.range_dict:
            list_worksheet = workbook[rng['sheet']]
            row_count = self.get_row_count(list_worksheet, rng)
            column_names = [(item.value.lower().replace(" ", "_"), item.column) for item in
                            list_worksheet[rng['header_row']] if item.value]
            samples = self.pad_samples_to_length(row_count=row_count, column_names=column_names)
            # samples = self.pydant_obj
            logger.debug(f"Samples: {[item.submission_rank for item in samples]}")
            for sample in samples:
                logger.debug(f"Writing sample: {sample}")
                write_row = rng['header_row'] + sample.submission_rank
                for column in column_names:
                    if column[0].lower() in ["well"]:#, "row", "column"]:
                        continue
                    write_column = column[1]
                    try:
                        value = getattr(sample, column[0])
                    except KeyError:
                        value = ""
                    logger.debug(f"{column} Writing {value} to row {write_row}, column {write_column}")
                    list_worksheet.cell(row=write_row, column=write_column, value=value)
        return workbook
