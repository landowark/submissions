from __future__ import annotations
from pathlib import Path
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from typing import TYPE_CHECKING
import logging
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoParser(DefaultKEYVALUEParser):
    pyd_name = "PydResults"

    def __init__(self, filepath: Path | str, proceduretype: "ProcedureType" | None = None,
                 results_type: str | None = "PCR", *args, **kwargs):
        if results_type:
            self.results_type = results_type
        sheet = proceduretype.allowed_result_methods[results_type]['info']['sheet']
        start_row = proceduretype.allowed_result_methods[results_type]['info']['start_row']
        super().__init__(filepath=filepath, proceduretype=proceduretype, sheet=sheet, start_row=start_row, *args,
                         **kwargs)


class DefaultResultsSampleParser(DefaultTABLEParser):
    pyd_name = "PydResults"

    def __init__(self, filepath: Path | str, proceduretype: "ProcedureType" | None = None,
                 results_type: str | None = "PCR", *args, **kwargs):
        if results_type:
            self.results_type = results_type
        sheet = proceduretype.allowed_result_methods[results_type]['sample']['sheet']
        start_row = proceduretype.allowed_result_methods[results_type]['sample']['start_row']
        super().__init__(filepath=filepath, proceduretype=proceduretype, sheet=sheet, start_row=start_row, *args,
                         **kwargs)


from .pcr_results_parser import PCRInfoParser, PCRSampleParser
