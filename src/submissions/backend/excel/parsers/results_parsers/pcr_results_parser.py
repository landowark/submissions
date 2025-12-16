"""
Parser for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
import logging
from datetime import datetime
from pprint import pformat
from typing import Generator, TYPE_CHECKING
from dateutil.parser import parse
from backend.excel.parsers.results_parsers import DefaultResultsInfoParser, DefaultResultsSampleParser
from pathlib import Path
if TYPE_CHECKING:
    from backend.validators.pydant import PydSample

logger = logging.getLogger(f"submissions.{__name__}")


class PCRInfoParser(DefaultResultsInfoParser):

    def __init__(self, filepath: Path | str, procedure=None, **kwargs):
        self.results_type = "PCR"
        self.procedure = procedure
        super().__init__(filepath=filepath, proceduretype=self.procedure.proceduretype, results_type=self.results_type)
        date_analyzed = next((v for k,v in self.parsed_info if k == "analysis_date/time"),
                             datetime.combine(datetime.today(), datetime.min.time()))
        if not isinstance(date_analyzed, datetime):
            date_analyzed = parse(date_analyzed, tzinfos={"CDT":"America/Winnipeg"})
        self.date_analyzed = date_analyzed

    def to_pydantic(self):
        data = dict(results={k: v for k, v in self.parsed_info}, filepath=self.filepath,
                    result_type=self.results_type)
        return self._pyd_object(**data, date_analyzed=self.date_analyzed, parent=self.procedure)


class PCRSampleParser(DefaultResultsSampleParser):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, filepath: Path | str, date_analyzed: datetime, sheet: str | None = None, start_row: int = 1,  procedure=None, **kwargs):
        self.results_type = "PCR"
        self.procedure = procedure
        self.date_analyzed = date_analyzed
        super().__init__(filepath=filepath, proceduretype=self.procedure.proceduretype, results_type=self.results_type)

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        output = [item for item in super().parsed_info]
        sample_names = list(set([item['sample'] for item in output]))
        for sample in sample_names:
            multi = dict(result_type="PCR")
            sois = [item for item in output if item['sample'] == sample]
            for soi in sois:
                multi[soi['target']] = {k: v for k, v in soi.items() if k != "target" and k != "sample"}
            yield {sample: multi}

    def to_pydantic(self) -> Generator["PydSample", None, None]:
        from backend.db.models import ProcedureSampleAssociation
        for item in self.parsed_info:
            # logger.debug(f"PCRSampleParser parsed info: {pformat(item.keys())}")
            # NOTE: Ensure that only samples associated with the procedure are used.
            try:
                sample_obj = next(
                    (sample for sample in self.procedure.sample if sample.sample_id == list(item.keys())[0]))
            except StopIteration:
                continue
            assoc = ProcedureSampleAssociation.query(sample=sample_obj, procedure=self.procedure)
            if assoc and not isinstance(assoc, list):
                output = self._pyd_object(results=list(item.values())[0], parent=assoc, date_analyzed=self.date_analyzed)
                output.result_type = "PCR"
                try:
                    del output.result['result_type']
                except KeyError:
                    pass
                yield output
            else:
                continue
