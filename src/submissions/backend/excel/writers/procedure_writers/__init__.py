"""
Default writers for procedures.
"""
from __future__ import annotations
from operator import itemgetter
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
               'reagentrole', 'results', 'sample', 'tips', 'reagentlot', 'platemap']

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.fill_dictionary = {k: v for k, v in self.fill_dictionary.items() if k not in self.__class__.exclude}

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=f"{self.pydant_obj.proceduretype.name[:20]} Quality")
        return workbook


class ProcedureReagentWriter(DefaultTABLEWriter):

    exclude = ["id", "comments", "missing", "active", "name", "reagent", "reagentlot", "procedure", "excluded", "reagentlotprocedureassociation"]
    header_order = ["reagentrole", "reagent_name", "lot", "expiry"]

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name[:20]} Quality"
        self.pydant_obj = self.pydant_obj.reagentlot

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureEquipmentWriter(DefaultTABLEWriter):

    exclude = ['id', "equipment_role", "name", "nickname", "procedure", "equipmentequipmentroleassociation", 
               "equipmentprocedureassociation", "excluded", "procedureequipmenttipslotassociation"]
    header_order = ['equipmentrole', 'equipment', 'asset_number', 'processversion', 'tipslot', 'start_time', 'end_time']

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name[:20]} Quality"
        output = []
        for equipment in self.pydant_obj.equipment:
            equipment.tipslot = "\n".join([str(item) for item in equipment.tipslot])
            output.append(equipment)
        self.pydant_obj = output

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureSampleWriter(DefaultTABLEWriter):

    exclude = ['id', 'enabled', 'name', "submission_rank", 'background_color', "is_control", "well_id", "sample", "sample_location", 
               "sample_type", "clientsubmission", "excluded", "procedure", "rank", "results", "run", "sampleclientsubmissionassociation",
               "sampleprocedureassociation", "samplerunassociation"]
    header_order = ['procedure_rank', 'sample_id']

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name[:20]} Quality"
        self.pydant_obj = self.pad_procedure_samples_to_length()

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook

    def pad_procedure_samples_to_length(self):
        from backend.validators.pydant import PydProcedureSampleAssociation
        output_samples = []
        rows = self.proceduretype.plate_rows
        columns = self.proceduretype.plate_columns
        logger.debug(type(self.pydant_obj))
        if rows == 0 or columns == 0:
            for iii in range(1, self.pydant_obj.max_sample_rank + 1):
                try:
                    sample = next(item.to_pydantic() for item in self.pydant_obj.sql_instance.proceduresampleassociation if item.procedure_rank == iii)
                except StopIteration:
                    sample = PydProcedureSampleAssociation(sample="", procedure=self.proceduretype.name, procedure_rank=iii, row=0, column=0)
                output_samples.append(sample)
            return sorted(output_samples, key=lambda x: x.procedure_rank)
        else:
            iii = 1
            for ccc in range(1, columns + 1):
                for rrr in range(1, rows + 1):
                    try:
                        sample = next(item.to_pydantic() for item in self.pydant_obj.sql_instance.proceduresampleassociation if item.column == ccc and item.row == rrr)
                    except StopIteration:
                        sample = PydProcedureSampleAssociation(sample="", procedure=self.proceduretype.name, procedure_rank=iii, row=rrr, column=ccc)
                    output_samples.append(sample)
                    iii += 1
            return sorted(output_samples, key=lambda x: (x.column, x.row))        