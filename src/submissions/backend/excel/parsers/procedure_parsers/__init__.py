from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING


from backend.excel.parsers import DefaultTABLEParser, DefaultKEYVALUEParser
if TYPE_CHECKING:
    from backend.db.models import ProcedureType


class ProcedureInfoParser(DefaultKEYVALUEParser):

    default_range_dict = [dict(
        start_row=1,
        end_row=6,
        key_column=1,
        value_column=2,
        sheet=""
    )]

    def __init__(self, filepath: Path | str, proceduretype: "ProcedureType"|None=None, range_dict: dict | None = None, *args, **kwargs):
        from backend.validators.pydant import PydProcedure
        proceduretype = self.correct_procedure_type(proceduretype)
        if not range_dict:
            range_dict = proceduretype.info_map
            if not range_dict:
                range_dict = self.__class__.default_range_dict
                for item in range_dict:
                    item['sheet'] = proceduretype.name
        super().__init__(filepath=filepath, proceduretype=proceduretype, range_dict=range_dict, *args, **kwargs)
        self._pyd_object = PydProcedure


class ProcedureSampleParser(DefaultTABLEParser):

    default_range_dict = [dict(
        header_row=41,
        sheet=""
    )]

    def __init__(self, filepath: Path | str, proceduretype: "ProcedureType"|None=None, range_dict: dict | None = None, *args, **kwargs):
        from backend.validators.pydant import PydSample
        proceduretype = self.correct_procedure_type(proceduretype)
        if not range_dict:
            range_dict = proceduretype.sample_map
            if not range_dict:
                range_dict = self.__class__.default_range_dict
                for item in range_dict:
                    item['sheet'] = proceduretype.name
        super().__init__(filepath=filepath, procedure=proceduretype, range_dict=range_dict, *args, **kwargs)
        self._pyd_object = PydSample


class ProcedureReagentParser(DefaultTABLEParser):

    default_range_dict = [dict(
        header_row=17,
        end_row=29,
        sheet=""
    )]

    def __init__(self, filepath: Path | str, proceduretype: "ProcedureType"|None=None, range_dict: dict | None = None, *args, **kwargs):
        from backend.validators.pydant import PydReagent
        proceduretype = self.correct_procedure_type(proceduretype)
        if not range_dict:
            range_dict = proceduretype.sample_map
            if not range_dict:
                range_dict = self.__class__.default_range_dict
                for item in range_dict:
                    item['sheet'] = proceduretype.name
        super().__init__(filepath=filepath, proceduretype=proceduretype, range_dict=range_dict, *args, **kwargs)
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

    default_range_dict = [dict(
        header_row=32,
        end_row=39,
        sheet=""
    )]

    def __init__(self, filepath: Path | str, proceduretype: "ProcedureType"|None=None, range_dict: dict | None = None, *args, **kwargs):
        from backend.validators.pydant import PydEquipment
        proceduretype = self.correct_procedure_type(proceduretype)
        if not range_dict:
            range_dict = proceduretype.sample_map
            if not range_dict:
                range_dict = self.__class__.default_range_dict
                for item in range_dict:
                    item['sheet'] = proceduretype.name
        super().__init__(filepath=filepath, proceduretype=proceduretype, range_dict=range_dict, *args, **kwargs)
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
