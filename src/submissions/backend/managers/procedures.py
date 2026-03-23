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

    def parse(self):
        try:
            info_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}InfoParser")
        except AttributeError:
            info_parser = procedure_parsers.ProcedureInfoParser
        self.info_parser = info_parser(worksheet=self.input_object)
        
        try:
            reagent_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}ReagentParser")
        except AttributeError:
            reagent_parser = procedure_parsers.ProcedureReagentParser
        self.reagent_parser = reagent_parser(worksheet=self.input_object, start_row=self.info_parser.end_row)
        try:
            equipment_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}EquipmentParser")
        except AttributeError:
            equipment_parser = procedure_parsers.ProcedureEquipmentParser
        self.equipment_parser = equipment_parser(worksheet=self.input_object, start_row=self.reagent_parser.end_row)
        try:
            sample_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}SampleParser")
        except AttributeError:
            sample_parser = procedure_parsers.ProcedureSampleParser
        self.sample_parser = sample_parser(worksheet=self.input_object, start_row=self.equipment_parser.end_row)
        
        # self.to_pydantic()

    def to_pydantic(self) -> PydProcedure:
        from backend.validators.pydant import PydProcedure, PydProcedureReagentLotAssociation, PydSample, PydProcedureEquipmentAssociation
        self.procedure = PydProcedure(**{k:v for k, v in self.info_parser.parsed_info})
        self.procedure.reagentlot = [PydProcedureReagentLotAssociation(procedure=self.procedure, **item) for item in self.reagent_parser.parsed_info]
        self.procedure.sample = [PydSample(**sample) for sample in self.sample_parser.parsed_info]
        self.procedure.equipment = [PydProcedureEquipmentAssociation(procedure=self.procedure, **item) for item in self.equipment_parser.parsed_info]
        return self.procedure

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
