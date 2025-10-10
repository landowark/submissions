from __future__ import annotations
from pathlib import Path
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from typing import TYPE_CHECKING, Tuple, Generator, Any
import logging
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoParser(DefaultKEYVALUEParser):
    pyd_name = "PydResults"

    def __init__(self, filepath: Path | str, results_type: str, proceduretype: ProcedureType | None = None,
                  *args, **kwargs):
        if results_type:
            self.results_type = results_type
        try:
            sheet = proceduretype.allowed_result_methods[results_type]['info']['sheet']
        except KeyError:
            sheet = 1
        if "start_row" not in kwargs:
            try:
                start_row = proceduretype.allowed_result_methods[results_type]['info']['start_row']
            except KeyError:
                start_row = 1
        else:
            start_row = kwargs.pop('start_row')
        super().__init__(filepath=filepath, proceduretype=proceduretype, sheet=sheet, start_row=start_row, *args,
                         **kwargs)

    @property
    def parsed_info(self) -> Generator[Tuple[str, Any], None, None]:
        for key, value in super().parsed_info:
            try:
                value = value['value']
            except KeyError:
                pass
            yield key, value


class DefaultResultsSampleParser(DefaultTABLEParser):
    pyd_name = "PydResults"

    def __init__(self, filepath: Path | str, results_type: str, proceduretype: ProcedureType | None = None,
                 *args, **kwargs):
        if results_type:
            self.results_type = results_type
        try:
            sheet = proceduretype.allowed_result_methods[results_type]['sample']['sheet']
        except KeyError:
            sheet = 1
        if "start_row" not in kwargs:
            try:
                start_row = proceduretype.allowed_result_methods[results_type]['sample']['header_row']
            except KeyError:
                start_row = 1
        else:
            start_row = kwargs.pop('start_row')
        super().__init__(filepath=filepath, proceduretype=proceduretype, sheet=sheet, start_row=start_row, *args,
                         **kwargs)


from .pcr_results_parser import PCRInfoParser, PCRSampleParser
from .qubit_results_parser import QubitInfoParser, QubitSampleParser
