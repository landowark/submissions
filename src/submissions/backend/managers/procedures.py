"""
Module for manager of Procedure object.
"""
from __future__ import annotations
from pprint import pformat
import logging, sys
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from backend.managers import DefaultManager
from typing import TYPE_CHECKING, Literal
from pathlib import Path
from backend.excel.parsers import procedure_parsers, DefaultParser
from backend.excel.writers import procedure_writers, results_writers
if TYPE_CHECKING:
    from backend.db.models import ProcedureType
    from backend.validators.pydant import PydProcedureType
    from backend.db.models import BaseClass
    from backend.validators.pydant import PydBaseClass

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultProcedureManager(DefaultManager):

    _DEFAULT_PARSERS = {
        "info":      procedure_parsers.ProcedureInfoParser,
        "reagent":   procedure_parsers.ProcedureReagentParser,
        "equipment": procedure_parsers.ProcedureEquipmentParser,
        "sample":    procedure_parsers.ProcedureSampleParser,
    }

    _DEFAULT_WRITERS = {
        "info":      procedure_writers.ProcedureInfoWriter,
        "reagent":   procedure_writers.ProcedureReagentWriter,
        "equipment": procedure_writers.ProcedureEquipmentWriter,
        "sample":    procedure_writers.ProcedureSampleWriter,
        "results":   results_writers.DefaultResultsInfoWriter
    }

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
            case _ if issubclass(input_object.__class__, pydant.PydBaseClass):
                self.pyd.sample = [sample.to_pydantic() for sample in input_object.sql_instance.sample]
                self.pyd.results = [result.to_pydantic() for result in input_object.sql_instance.results]
            case _ if issubclass(input_object.__class__, BaseClass):
                self.pyd.sample = [sample.to_pydantic() for sample in input_object.sample]
                self.pyd.results = [result.to_pydantic() for result in input_object.results]

    @property
    def _pyd_object(self):
        from backend.validators.pydant import PydProcedure
        return PydProcedure

    def _resolve_operator(self, operation: Literal['parse', 'write'], role: str) -> type:
        """
        Look up a named parser for this procedure type, falling back to the default.
        Logs a clear warning when a custom parser is not found, rather than silently
        catching AttributeError.
        """
        class_name = f"{self.proceduretype.name.replace(' ', '')}{role.title()}{operation.title()}r"
        cls = getattr(procedure_parsers, class_name, None)
        if cls is None:
            logger.debug(f"No custom parser '{class_name}', using default.")
            match operation:
                case "parse":
                    cls = self._DEFAULT_PARSERS[role]
                case "write":
                    cls = self._DEFAULT_WRITERS[role]
                case _:
                    cls = DefaultParser
        return cls
    
    def parse(self):
        self.info_parser      = self._resolve_operator("parse", "info")(worksheet=self.input_object)
        self.reagent_parser   = self._resolve_operator("parse", "reagent")(worksheet=self.input_object, start_row=self.info_parser.end_row)
        self.equipment_parser = self._resolve_operator("parse","equipment")(worksheet=self.input_object, start_row=self.reagent_parser.end_row)
        self.sample_parser    = self._resolve_operator("parse","sample")(worksheet=self.input_object, start_row=self.equipment_parser.end_row)
        from backend.validators.pydant import PydProcedure, PydProcedureReagentLotAssociation, PydSample, PydProcedureEquipmentAssociation
        self.procedure = self.info_parser.to_pydantic()
        self.procedure.reagentlot = self.reagent_parser.to_pydantic()
        self.procedure.sample = self.sample_parser.to_pydantic()
        self.procedure.equipment = self.equipment_parser.to_pydantic()
        return self.procedure

    def write(self, workbook: Workbook) -> Workbook:
        self.info_writer = self._resolve_operator("write", "info")(pydant_obj=self.pyd)
        workbook = self.info_writer.write_to_workbook(workbook)
        self.reagent_writer = self._resolve_operator("write", "reagent")(pydant_obj=self.pyd)
        workbook = self.reagent_writer.write_to_workbook(workbook, start_row=self.info_writer.end_row)
        self.equipment_writer = self._resolve_operator("write", "equipment")(pydant_obj=self.pyd)
        workbook = self.equipment_writer.write_to_workbook(workbook, start_row=self.reagent_writer.end_row)
        self.sample_writer = self._resolve_operator("write", "sample")(pydant_obj=self.pyd, proceduretype=self.proceduretype)
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
                    Writer = getattr(results_writers, f"{resulttype_name.replace(" ", "")}InfoWriter")
                except AttributeError:
                    logger.error(f"Couldn't get {resulttype_name.replace(" ", "")}InfoWriter, using DefaultResultsInfoWriter")
                    Writer = results_writers.DefaultResultsInfoWriter
                res_info_writer = Writer(pydant_obj=info_result, proceduretype=self.proceduretype)
                workbook = res_info_writer.write_to_workbook(workbook=workbook)
                grouped_writer['info'] = res_info_writer
            # The sample writer should take as pydant_object, results as pydantic objects from each proceduresampleassociation in the procedure
            sample_results = [res.to_pydantic() if hasattr(res, "to_pydantic") else res for res in parents['sample']]
            if len(sample_results) > 0:
                try:
                    Writer = getattr(results_writers, f"{resulttype_name.replace(" ", "")}SampleWriter")
                except AttributeError:
                    logger.error(f"Couldn't get {resulttype_name.replace(" ", "")}SampleWriter, using DefaultResultsSampleWriter")
                    Writer = results_writers.DefaultResultsSampleWriter
                res_sample_writer = Writer(pydant_obj=sample_results, resultstype=resulttype_name, proceduretype=self.proceduretype)
                try:
                    new_start_row = res_info_writer.end_row
                except UnboundLocalError:
                    new_start_row = 1
                workbook = res_sample_writer.write_to_workbook(workbook=workbook, start_row=new_start_row)
                grouped_writer['sample'] = res_sample_writer
            self.result_writers.append(grouped_writer)
        return workbook

__all__ = ["DefaultProcedureManager"]