"""
Default writers for procedures.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from openpyxl.workbook import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter


class ProcedureInfoWriter(DefaultKEYVALUEWriter):

    def __init__(self, pydant_obj, *args, **kwargs):
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        # Put comment back in due to exclusion.
        self.fill_dictionary['comment'] = pydant_obj.comment
        self.sheet = f"{self.proceduretype.name[:20]} Quality"

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureReagentWriter(DefaultTABLEWriter):

    def __init__(self, pydant_obj, *args, **kwargs):
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, actual_objs_type="reagentlot", *args, **kwargs)
        self.sheet = f"{self.proceduretype.name[:20]} Quality"

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureEquipmentWriter(DefaultTABLEWriter):

    def __init__(self, pydant_obj, *args, **kwargs):
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, actual_objs_type="equipment", *args, **kwargs)
        self.sheet = f"{self.proceduretype.name[:20]} Quality"

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureSampleWriter(DefaultTABLEWriter):

    def __init__(self, pydant_obj, *args, **kwargs):
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.proceduretype.name[:20]} Quality"
        self.pydant_obj = self.pad_procedure_samples_to_length()
        self.excluded = self.pydant_obj[0].class_config.excluded
        self.key_value_order = self.pydant_obj[0].class_config.key_value_order
        
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
                            sample = PydProcedureSampleAssociation(sample=sample, procedure=self.pydant_obj, procedure_rank=iii, row=sample.row, column=sample.column)
                        except StopIteration:
                            sample = PydProcedureSampleAssociation(sample="", procedure=self.pydant_obj, procedure_rank=iii, row=rrr, column=ccc)
                    output_samples.append(sample)
                    iii += 1
            return sorted(output_samples, key=lambda x: (x.column, x.row))


__all__ = ["ProcedureInfoWriter", "ProcedureReagentWriter", "ProcedureEquipmentWriter", "ProcedureSampleWriter"]