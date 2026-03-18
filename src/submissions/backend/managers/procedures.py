"""
Module for manager of Procedure object.
"""
from __future__ import annotations
from pprint import pformat
import logging, sys
from openpyxl import load_workbook
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from backend.managers import DefaultManager
from typing import TYPE_CHECKING
from pathlib import Path
from backend.excel.parsers import procedure_parsers
from backend.excel.writers import procedure_writers, results_writers
if TYPE_CHECKING:
    from backend.db.models import Procedure, ProcedureType
    from backend.validators.pydant import PydProcedure

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultProcedureManager(DefaultManager):

    def __init__(self, parent, input_object: Path | str | Procedure | PydProcedure | dict | Worksheet | None = None,
                 proceduretype: str | ProcedureType | None = None):
        from backend.db.models import ProcedureType, Procedure
        from backend.validators.pydant import PydProcedure
        self.proceduretype = proceduretype
        if isinstance(input_object, str):
            input_object = Path(input_object).absolute()
        match input_object:
            # case Procedure():
            #     self.procedure = input_object.to_pydantic()
            # case PydProcedure():
            #     self.procedure = input_object
            case dict():
                input_object = Procedure.query_or_create(**input_object).to_pydantic()
            case Path():
                wb = load_workbook(input_object)
                if self.proceduretype is None:
                    raise TypeError("Need a proceduretype to parse from file.")
                else:
                    actual = next((sheet for sheet in wb.sheetnames if sheet.removesuffix(" Quality") == self.proceduretype), None)
                    if actual is not None:
                        input_object = wb[actual]
                    else:
                        raise TypeError("Need a proceduretype to parse from file.")
                    input_object = self.parse(worksheet = input_object)
            case Worksheet():
                input_object = self.parse(worksheet = input_object)
        if isinstance(input_object, Worksheet):

        # self.procedure = input_object
        # This is the sql object
        super().__init__(parent=parent, input_object=input_object)

    def parse(self, worksheet: Worksheet):
        try:
            info_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}InfoParser")
        except AttributeError:
            info_parser = procedure_parsers.ProcedureInfoParser
        self.info_parser = info_parser(worksheet=worksheet)
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
        self.sample_writer = sample_writer(pydant_obj=self.pyd, proceduretype=self.proceduretype)
        workbook = self.sample_writer.write_to_workbook(workbook, start_row=self.equipment_writer.end_row)
        # # TODO: Find way to group results by result_type.
        for result in self.pyd.result:
            Writer = getattr(results_writers, f"{result.result_type}InfoWriter")
            res_info_writer = Writer(pydant_obj=result, proceduretype=self.proceduretype)
            workbook = res_info_writer.write_to_workbook(workbook=workbook)
        for result in self.pyd.sample_results:
            logger.debug(f"Sample result: {pformat(type(result))}")
            Writer = getattr(results_writers, f"{result.resultstype}SampleWriter")
            res_sample_writer = Writer(pydant_obj=self.procedure, proceduretype=self.proceduretype)
            workbook = res_sample_writer.write_to_workbook(workbook=workbook)
        return workbook
