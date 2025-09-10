"""
Module for manager of Procedure object.
"""
from __future__ import annotations
import logging, sys
from openpyxl.workbook import Workbook
from backend.managers import DefaultManager
from typing import TYPE_CHECKING
from pathlib import Path
from backend.excel.parsers import procedure_parsers
from backend.excel.writers import procedure_writers, results_writers
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultProcedureManager(DefaultManager):

    def __init__(self, proceduretype: "ProcedureType"|str, parent, input_object: Path | str | None = None):
        from backend.db.models import ProcedureType
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        self.proceduretype = proceduretype
        super().__init__(parent=parent, input_object=input_object)


    def parse(self):
        try:
            info_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}InfoParser")
        except AttributeError:
            info_parser = procedure_parsers.ProcedureInfoParser
        self.info_parser = info_parser(filepath=self.fname, proceduretype=self.proceduretype)
        try:
            reagent_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}ReagentParser")
        except AttributeError:
            reagent_parser = procedure_parsers.ProcedureReagentParser
        self.reagent_parser = reagent_parser(filepath=self.fname, proceduretype=self.proceduretype)
        try:
            sample_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}SampleParser")
        except AttributeError:
            sample_parser = procedure_parsers.ProcedureSampleParser
        self.sample_parser = sample_parser(filepath=self.fname, proceduretype=self.proceduretype)
        try:
            equipment_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}EquipmentParser")
        except AttributeError:
            equipment_parser = procedure_parsers.ProcedureEquipmentParser
        self.equipment_parser = equipment_parser(filepath=self.fname, proceduretype=self.proceduretype)
        self.to_pydantic()

    def to_pydantic(self):
        self.procedure = self.info_parser.to_pydantic()
        self.reagents = self.reagent_parser.to_pydantic()
        self.samples = self.sample_parser.to_pydantic()
        self.equipment = self.equipment_parser.to_pydantic()

    def write(self, workbook: Workbook) -> Workbook:
        try:
            info_writer = getattr(procedure_writers, f"{self.proceduretype.name.replace(' ', '')}InfoWriter")
        except AttributeError:
            info_writer = procedure_writers.ProcedureInfoWriter
        self.info_writer = info_writer(pydant_obj=self.pyd)
        workbook = self.info_writer.write_to_workbook(workbook)
        try:
            reagent_writer = getattr(procedure_writers, f"{self.proceduretype.name.replace(' ', '')}ReagentWriter")
        except AttributeError:
            reagent_writer = procedure_writers.ProcedureReagentWriter
        self.reagent_writer = reagent_writer(pydant_obj=self.pyd)
        workbook = self.reagent_writer.write_to_workbook(workbook, start_row=self.info_writer.end_row)
        try:
            equipment_writer = getattr(procedure_writers, f"{self.proceduretype.name.replace(' ', '')}EquipmentWriter")
        except AttributeError:
            equipment_writer = procedure_writers.ProcedureEquipmentWriter
        self.equipment_writer = equipment_writer(pydant_obj=self.pyd)
        workbook = self.equipment_writer.write_to_workbook(workbook, start_row=self.reagent_writer.end_row)
        try:
            sample_writer = getattr(procedure_writers, f"{self.proceduretype.name.replace(' ', '')}SampleWriter")
        except AttributeError:
            sample_writer = procedure_writers.ProcedureSampleWriter
        self.sample_writer = sample_writer(pydant_obj=self.pyd)
        workbook = self.sample_writer.write_to_workbook(workbook, start_row=self.equipment_writer.end_row)
        # # TODO: Find way to group results by result_type.
        for result in self.pyd.result:
            Writer = getattr(results_writers, f"{result.result_type}InfoWriter")
            res_info_writer = Writer(pydant_obj=result, proceduretype=self.proceduretype)
            workbook = res_info_writer.write_to_workbook(workbook=workbook)
        return workbook
