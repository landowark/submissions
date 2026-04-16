"""
Module for manager of Procedure object.
"""
from __future__ import annotations
from pprint import pformat
import logging, sys
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from backend.managers import DefaultManager
from typing import TYPE_CHECKING
from pathlib import Path
from backend.excel.parsers import procedure_parsers
from backend.excel.writers import procedure_writers, results_writers
if TYPE_CHECKING:
    from backend.db.models import ProcedureType
    from backend.validators.pydant import PydProcedureType
    from backend.db.models import BaseClass
    from backend.validators.pydant import PydBaseClass

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultProcedureManager(DefaultManager):

    def __init__(self, parent, input_object: Path | str | PydBaseClass | BaseClass | Workbook | Worksheet | None = None,
                 proceduretype: str | ProcedureType | PydProcedureType | None = None, **kwargs):
        from backend.db.models import ProcedureType, BaseClass
        from backend.validators import pydant
        if proceduretype is None:
            try:
                proceduretype = input_object.proceduretype
            except AttributeError:
                proceduretype = None
        match proceduretype:
            case str():
                proceduretype = ProcedureType.query(name=proceduretype, limit=1)
                if isinstance(proceduretype, ProcedureType):
                    self.proceduretype = proceduretype.to_pydantic()
                else:
                    self.proceduretype = None
            case ProcedureType():
                self.proceduretype = proceduretype.to_pydantic()
            case  _:
                self.proceduretype = proceduretype
        assert self.proceduretype is not None, "Procedure type must be provided to ProcedureManager"
        super().__init__(parent, input_object, **kwargs)
        match input_object:
            case x if issubclass(input_object.__class__, pydant.PydBaseClass):
                self.pyd.sample = [sample.to_pydantic() for sample in input_object.sql_instance.sample]
                self.pyd.results = [result.to_pydantic() for result in input_object.sql_instance.results]
            case x if issubclass(input_object.__class__, BaseClass):
                self.pyd.sample = [sample.to_pydantic() for sample in input_object.sample]
                self.pyd.results = [result.to_pydantic() for result in input_object.results]
            
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
        self.result_writers = []
        for resulttype_name, parents in self.pyd.sql_instance.grouped_results.items():
            grouped_writer = {}
            info_result = parents['info']
            try:
                info_result = info_result.to_pydantic()
            except AttributeError:
                info_result = None
            if info_result is not None:
                try:
                    Writer = getattr(results_writers, f"{resulttype_name}InfoWriter")
                except AttributeError:
                    Writer = results_writers.DefaultResultsInfoWriter
                res_info_writer = Writer(pydant_obj=info_result, proceduretype=self.proceduretype)
                workbook = res_info_writer.write_to_workbook(workbook=workbook)
                grouped_writer['info'] = res_info_writer
            # The sample writer should take as pydant_object, results as pydantic objects from each proceduresampleassociation in the procedure
            sample_results = [res.to_pydantic() for res in parents['sample']]
            if len(sample_results) > 0:
                try:
                    Writer = getattr(results_writers, f"{resulttype_name}SampleWriter")
                except AttributeError:
                    Writer = results_writers.DefaultResultsSampleWriter
                res_sample_writer = Writer(pydant_obj=sample_results, resultstype=resulttype_name, proceduretype=self.proceduretype)
                try:
                    new_start_row = res_info_writer.end_row + 1
                except UnboundLocalError:
                    new_start_row = 1
                workbook = res_sample_writer.write_to_workbook(workbook=workbook, start_row=new_start_row)
                grouped_writer['sample'] = res_sample_writer
            self.result_writers.append(grouped_writer)
        return workbook
