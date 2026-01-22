"""
Default procedure parsers (currently unused).
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from backend.excel.parsers import DefaultTABLEParser, DefaultKEYVALUEParser
import logging
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")

"""
TODO

- range dicts should hopefully not be necessary in this type of parser. Hopefully all procedure parsers are the same.
"""


class ProcedureInfoParser(DefaultKEYVALUEParser):

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType | None=None, *args, **kwargs):
        from backend.validators.pydant import PydProcedure
        proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(filepath=filepath, proceduretype=proceduretype, *args, **kwargs)
        self._pyd_object = PydProcedure


class ProcedureSampleParser(DefaultTABLEParser):

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType|None=None, range_dict: dict | None = None, *args, **kwargs):
        from backend.validators.pydant import PydSample
        proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(filepath=filepath, procedure=proceduretype, *args, **kwargs)
        self._pyd_object = PydSample


class ProcedureReagentParser(DefaultTABLEParser):

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType|None=None, *args, **kwargs):
        from backend.validators.pydant import PydReagent
        proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(filepath=filepath, proceduretype=proceduretype, *args, **kwargs)
        self._pyd_object = PydReagent

    @property
    def parsed_info(self):
        output = super().parsed_info
        for item in output:
            if not item['lot']:
                continue
            item['reagentrole'] = item['reagent_role']
            yield item

class ProcedureEquipmentParser(DefaultTABLEParser):

    def __init__(self, filepath: Path | str, proceduretype: ProcedureType|None=None, *args, **kwargs):
        from backend.validators.pydant import PydEquipment
        proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(filepath=filepath, proceduretype=proceduretype, *args, **kwargs)
        self._pyd_object = PydEquipment

    @property
    def parsed_info(self):
        output = super().parsed_info
        for item in output:
            if not item['name']:
                continue
            from backend.db.models import Equipment, Process
            from backend.validators.pydant import PydTips, PydProcess
            eq = Equipment.query(name=item['name'])
            item['asset_number'] = eq.asset_number
            item['nickname'] = eq.nickname
            process = Process.query(name=item['process'])
            if item['tips']:
                item['tips'] = [PydTips(name=item['tips'], tiprole=process.tiprole[0].name)]
            item['equipmentrole'] = item['equipment_role']
            yield item
