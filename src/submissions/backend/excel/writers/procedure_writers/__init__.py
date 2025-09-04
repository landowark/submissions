"""
Default
"""
from __future__ import annotations
import logging, sys
from pprint import pformat
from openpyxl.workbook import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter

logger = logging.getLogger(f"submissions.{__name__}")

class ProcedureInfoWriter(DefaultKEYVALUEWriter):

    start_row = 1
    header_order = []
    exclude = ['control', 'equipment', 'excluded', 'id', 'misc_info', 'plate_map', 'possible_kits',
               'procedureequipmentassociation', 'procedurereagentassociation', 'proceduresampleassociation', 'proceduretipsassociation', 'reagent',
               'reagentrole', 'results', 'sample', 'tips']

    def __init__(self, pydant_obj, *args, **kwargs):

        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)

        self.fill_dictionary = {k: v for k, v in self.fill_dictionary.items() if k not in self.__class__.exclude}

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=f"{self.pydant_obj.proceduretype.name} Quality")
        return workbook


class ProcedureReagentWriter(DefaultTABLEWriter):

    exclude = ["id", "comments", "missing"]
    header_order = ["reagentrole", "name", "lot", "expiry"]

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name} Quality"
        self.pydant_obj = self.pydant_obj.reagent

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet)
        return workbook


class ProcedureEquipmentWriter(DefaultTABLEWriter):

    exclude = ['id']
    header_order = ['equipmentrole', 'name', 'asset_number', 'process', 'tips']

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name} Quality"
        self.pydant_obj = self.pydant_obj.equipment

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet)
        return workbook


class ProcedureSampleWriter(DefaultTABLEWriter):

    exclude = ['id', 'enabled', 'name', "submission_rank"]
    header_order = ['procedure_rank', 'sample_id']

    def __init__(self, pydant_obj, range_dict: dict | None = None, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, range_dict=range_dict, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name} Quality"
        self.pydant_obj = self.pad_samples_to_length(row_count=pydant_obj.max_sample_rank, mode="procedure")

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet)
        return workbook
