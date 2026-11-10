"""
Default writers for procedures.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from openpyxl.workbook import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from backend.validators.pydant import PydProcedure, PydProcedureSampleAssociation


class ProcedureInfoWriter(DefaultKEYVALUEWriter):
    """
    Derived from DefaultKEYVALUEWriter to handle writing of PydProcedure objects as Key | Value pairs to Excel files.

    :ivar pydantic_object: Object to be written to file.
    """
        
    def __init__(self, pydant_obj: PydProcedure, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydProcedure
        """
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        # Put comment back in due to exclusion.
        self.fill_dictionary['comment'] = pydant_obj.comment
        self.sheet = f"{self.proceduretype.name[:20]} Quality"

    def write_to_workbook(self, workbook: Workbook, 
                          start_row: int = 1, *args, **kwargs) -> Workbook:
        """
        Write to a named sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        DO NOT REMOVE THIS! Even though it seems redundant, it's needed for the proper worksheet naming and spacing.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureReagentWriter(DefaultTABLEWriter):
    """
    Derived from DefaultTABLEWriter to handle writing of ProcedureReagentAssociations as to rows of Excel files. One object per row.

    :ivar pydantic_object: Object to be written to file.
    """

    def __init__(self, pydant_obj: PydProcedure, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydProcedure
        """
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, actual_objs_type="reagentlot", *args, **kwargs)
        self.sheet = f"{self.proceduretype.name[:20]} Quality"

    def write_to_workbook(self, workbook: Workbook, start_row: int = 1, *args, **kwargs) -> Workbook:
        """
        Write to a self.sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        DO NOT REMOVE THIS! Even though it seems redundant, it's needed for the proper worksheet naming and spacing.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureEquipmentWriter(DefaultTABLEWriter):
    """
    Derived from DefaultTABLEWriter to handle writing of ProcedureEquipmentAssociations as to rows of Excel files. One object per row.

    :ivar pydantic_object: Object to be written to file.
    """
    def __init__(self, pydant_obj: PydProcedure, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydProcedure
        """
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, actual_objs_type="equipment", *args, **kwargs)
        self.sheet = f"{self.proceduretype.name[:20]} Quality"

    def write_to_workbook(self, workbook: Workbook, start_row: int = 1, *args, **kwargs) -> Workbook:
        """
        Write to a self.sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        DO NOT REMOVE THIS! Even though it seems redundant, it's needed for the proper worksheet naming and spacing.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook


class ProcedureSampleWriter(DefaultTABLEWriter):
    """
    Derived from DefaultTABLEWriter to handle writing of ProcedureSampleAssociations as to rows of Excel files. One object per row.

    :ivar pydantic_object: Object to be written to file.
    """
    def __init__(self, pydant_obj: PydProcedure, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydProcedure
        """
        self.proceduretype = pydant_obj.proceduretype
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.sheet = f"{self.proceduretype.name[:20]} Quality"
        self.pydant_obj = self.pad_procedure_samples_to_length()
        self.excluded = self.pydant_obj[0].class_config.excluded
        self.key_value_order = self.pydant_obj[0].class_config.key_value_order
        
    def write_to_workbook(self, workbook: Workbook, start_row: int = 1, *args, **kwargs) -> Workbook:
        """
        Write to a self.sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.sheet, start_row=start_row)
        return workbook

    def pad_procedure_samples_to_length(self) -> List[PydProcedureSampleAssociation]:
        """
        Creates blank PydClientSubmissionSampleAssociation objects to fill in blank rows.

        :returns: Padded list of objects sorted by column and row (or procedure_rank as fallback).
        :rtype: List[PydProcedureSampleAssociation]
        """
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