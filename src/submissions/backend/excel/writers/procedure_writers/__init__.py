"""
Default writers for procedures.
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
               'reagentrole', 'results', 'sample', 'tips', 'reagentlot', 'platemap', "procedurereagentlotassociation", "result", "sample_results"]

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.fill_dictionary = {k: v for k, v in self.fill_dictionary.items() if k not in self.__class__.exclude}

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=f"{self.pydant_obj.proceduretype.name[:20]} Quality", start_row=start_row)
        return workbook


class ProcedureReagentWriter(DefaultTABLEWriter):

    exclude = ["id", "comments", "missing", "active", "name", "reagentlot", "procedure", "excluded", "reagentlotprocedureassociation", "procedurereagentlotassociation", "reagent_name"]
    header_order = ["reagentrole", "reagent", "lot", "expiry"]


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
               "equipmentprocedureassociation", "excluded", "procedureequipmenttipslotassociation", "asset_number",
               "start_time", "end_time", "manufacturer", "ref", "process", "serial_number"]
    header_order = ['equipmentrole', 'equipment', 'processversion', 'tipslot']

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.pydant_obj.proceduretype.name[:20]} Quality"
        output = self.pydant_obj.equipment
        self.pydant_obj = output

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureSampleWriter(DefaultTABLEWriter):

    exclude = ['id', 'enabled', 'name', "submission_rank", 'background_color', "is_control", "well_id", "sample", "sample_location", 
               "sample_type", "clientsubmission", "excluded", "procedure", "rank", "results", "run", "sampleclientsubmissionassociation",
               "sampleprocedureassociation", "samplerunassociation", "control_type"]
    header_order = ['procedure_rank', 'sample_id', 'row', 'column']

    def __init__(self, pydant_obj, *args, **kwargs):
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.procedure = self.pydant_obj.name
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
        if rows == 0 or columns == 0:
            for iii in range(1, self.pydant_obj.max_sample_rank + 1):
                try:
                    sample = next(item.to_pydantic() for item in self.pydant_obj.sql_instance.proceduresampleassociation if item.procedure_rank == iii)
                except StopIteration:
                    try:
                        sample = next(item for item in self.pydant_obj.sample if item.rank == iii)
                        sample = PydProcedureSampleAssociation(sample=sample, procedure=self.procedure, procedure_rank=iii, row=sample.row, column=sample.column)
                    except StopIteration:
                        sample = PydProcedureSampleAssociation(sample="", procedure=self.procedure, procedure_rank=iii, row=0, column=0)
                output_samples.append(sample)
            return sorted(output_samples, key=lambda x: x.procedure_rank)
        else:
            iii = 1
            for ccc in range(1, columns + 1):
                for rrr in range(1, rows + 1):
                    try:
                        sample = next(item.to_pydantic() for item in self.pydant_obj.sql_instance.proceduresampleassociation if item.column == ccc and item.row == rrr)
                    except StopIteration:
                        try:
                            sample = next(item for item in self.pydant_obj.sample if item.column == ccc and item.row == rrr)
                            sample = PydProcedureSampleAssociation(sample=sample, procedure=self.procedure, procedure_rank=iii, row=sample.row, column=sample.column)
                        except StopIteration:
                            sample = PydProcedureSampleAssociation(sample="", procedure=self.procedure, procedure_rank=iii, row=rrr, column=ccc)
                    output_samples.append(sample)
                    iii += 1
            return sorted(output_samples, key=lambda x: (x.column, x.row))
        