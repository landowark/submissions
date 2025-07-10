from __future__ import annotations
import logging
from backend.managers import DefaultManager
from typing import TYPE_CHECKING
from pathlib import Path
from backend.excel.parsers import procedure_parsers
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultProcedureManager(DefaultManager):

    def __init__(self, proceduretype: "ProcedureType"|str, parent, input_object: Path | str | None = None):
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        self.proceduretype = proceduretype
        super().__init__(parent=parent, input_object=input_object)


    def parse(self):
        try:
            info_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}InfoParser")
        except AttributeError:
            info_parser = procedure_parsers.DefaultInfoParser
        self.info_parser = info_parser(filepath=self.fname, proceduretype=self.proceduretype)
        try:
            reagent_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}ReagentParser")
        except AttributeError:
            reagent_parser = procedure_parsers.DefaultReagentParser
        self.reagent_parser = reagent_parser(filepath=self.fname, proceduretype=self.proceduretype)
        try:
            sample_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}SampleParser")
        except AttributeError:
            sample_parser = procedure_parsers.DefaultSampleParser
        self.sample_parser = sample_parser(filepath=self.fname, proceduretype=self.proceduretype)
        try:
            equipment_parser = getattr(procedure_parsers, f"{self.proceduretype.name.replace(' ', '')}EquipmentParser")
        except AttributeError:
            equipment_parser = procedure_parsers.DefaultEquipmentParser
        self.equipment_parser = equipment_parser(filepath=self.fname, proceduretype=self.proceduretype)
        self.to_pydantic()

    def to_pydantic(self):
        self.procedure = self.info_parser.to_pydantic()
        self.reagents = self.reagent_parser.to_pydantic()
        self.samples = self.sample_parser.to_pydantic()
        self.equipment = self.equipment_parser.to_pydantic()