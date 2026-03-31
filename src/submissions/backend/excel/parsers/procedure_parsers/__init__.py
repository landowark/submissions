"""
Default procedure parsers (currently unused).
"""
from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING, Generator
from backend.excel.parsers import DefaultTABLEParser, DefaultKEYVALUEParser
import logging
from openpyxl.worksheet.worksheet import Worksheet
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")

"""
TODO

- range dicts should hopefully not be necessary in this type of parser. Hopefully all procedure parsers are the same.
"""


class ProcedureInfoParser(DefaultKEYVALUEParser):

    def __init__(self, worksheet: Worksheet, start_row: int =1, end_row: int | None = None, *args, **kwargs):
        from backend.validators.pydant import PydProcedure
        # proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(worksheet=worksheet, start_row=start_row, end_row=end_row, *args, **kwargs)
        self._pyd_object = PydProcedure

    @property
    def parsed_info(self) -> Generator[tuple, None, None]:
        for item in super().parsed_info:
            if item[0] == "procedure_type":
                yield ("proceduretype", item[1])
            else:
                yield item        


class ProcedureSampleParser(DefaultTABLEParser):

    def __init__(self, worksheet: Worksheet, start_row: int =1, end_row: int | None = None, *args, **kwargs):
        from backend.validators.pydant import PydSample
        # proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(worksheet=worksheet, start_row=start_row, end_row=end_row, *args, **kwargs)
        self._pyd_object = PydSample

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        for ii, sample in enumerate(super().parsed_info, start=1):
            sample['rank'] = ii
            yield sample


class ProcedureReagentParser(DefaultTABLEParser):

    def __init__(self, worksheet: Worksheet, start_row: int =1, end_row: int | None = None, *args, **kwargs):
        from backend.validators.pydant import PydReagent
        # proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(worksheet=worksheet, start_row=start_row, end_row=end_row, *args, **kwargs)
        self._pyd_object = PydReagent

    @property
    def parsed_info(self):
        output = super().parsed_info
        for item in output:
            if not item['lot']:
                continue
            item['reagentrole'] = item.pop('reagent_role', "NA")
            item['reagent'] = item.pop('reagent_name', "NA")
            yield item

class ProcedureEquipmentParser(DefaultTABLEParser):

    def __init__(self, worksheet: Worksheet, start_row: int =1, end_row: int | None = None, *args, **kwargs):
        from backend.validators.pydant import PydEquipment
        # proceduretype = self.correct_procedure_type(proceduretype)
        super().__init__(worksheet=worksheet, start_row=start_row, end_row=end_row, *args, **kwargs)
        self._pyd_object = PydEquipment

    @property
    def parsed_info(self):
        from backend.db.models import Equipment
        output = super().parsed_info
        for item in output:
            equipment = item.get('equipment', None)
            if equipment is None :
                continue
            # print(f"Querying {equipment}")
            eq = Equipment.query(name=equipment)
            item['asset_number'] = eq.asset_number
            item['nickname'] = eq.nickname
            item['processversion'] = item.pop("process_version", None)
            item['tipslot'] = item.pop("tips_lot", None)
            item['equipmentrole'] = item.pop('equipment_role', None)
            yield item
