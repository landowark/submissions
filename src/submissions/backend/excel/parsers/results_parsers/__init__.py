""" 
Default parsers for results 
"""
from __future__ import annotations
from pathlib import Path
from backend.excel.parsers import DefaultKEYVALUEParser, DefaultTABLEParser
from typing import TYPE_CHECKING, Tuple, Generator, Any, List
import logging
if TYPE_CHECKING:
    from backend.db.models import ProcedureType

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultResultsInfoParser(DefaultKEYVALUEParser):
    pyd_name = "PydResults"

    def __init__(self, filepath: Path | str, results_type: str, proceduretype: ProcedureType | None = None,  sheets: List[dict] = [],
                  *args, **kwargs):
        from backend.db.models import ResultsType
        if results_type:
            self.results_type = ResultsType.query(name=results_type)
        # try:
        #     sheets = self.results_type.info.get("sheet", [dict(sheet=0)])
        # except AttributeError:
        #     sheets = [dict(sheet=0)]
        # if "start_row" not in kwargs:
        #     start_row = self.results_type.info.get('start_row', 1)
        # else:
        #     start_row = kwargs.pop('start_row')
        super().__init__(filepath=filepath, proceduretype=proceduretype, sheets=sheets, *args,
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

    def __init__(self, filepath: Path | str, results_type: str, proceduretype: ProcedureType | None = None, sheets: List[dict] = [],
                 *args, **kwargs):
        from backend.db.models import ResultsType
        if results_type:
            self.results_type = ResultsType.query(name=results_type)
        # try:
        #     sheet = self.results_type.samples.get("sheet", 1)
        # except AttributeError:
        #     sheet = 1
        # if "start_row" not in kwargs:
        #     start_row = self.results_type.samples.get('header_row', 1)
        # else:
        #     start_row = kwargs.pop('start_row')
        super().__init__(filepath=filepath, proceduretype=proceduretype, sheets=sheets, *args,
                         **kwargs)


from .diomni_pcr_results_parser import DiomniPCRInfoParser, DiomniPCRSampleParser
from .qubit_results_parser import QubitInfoParser, QubitSampleParser
