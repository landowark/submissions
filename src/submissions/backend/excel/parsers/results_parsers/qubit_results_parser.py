"""
Results parser for Qubit csv file.
"""
from __future__ import annotations
import logging
from typing import Generator, TYPE_CHECKING
from frontend.widgets.results_sample_matcher import ResultsSampleMatcher
from backend.excel.parsers.results_parsers import DefaultResultsInfoParser, DefaultResultsSampleParser
from pathlib import Path
if TYPE_CHECKING:
    from backend.db.models import Procedure

logger = logging.getLogger(f"submissions.{__name__}")

class QubitInfoParser(DefaultResultsInfoParser):

    sheets = [ dict(
                sheet = 1,
                start_row = 18) 
            ]

    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        self.results_type = "Qubit"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type="Qubit", *args, **kwargs)

    def to_pydantic(self):
        """
        Since there is no overview generated, return blank PydResults object.

        Returns:
            None
        """
        from backend.validators.pydant import PydResults
        return None


class QubitSampleParser(DefaultResultsSampleParser):
    """Object to pull data from Design and Analysis PCR export file."""

    def __init__(self, worksheet: Worksheet, procedure: Procedure | None = None, *args, **kwargs):
        self.results_type = "Qubit"
        self.procedure = procedure
        super().__init__(worksheet=worksheet, results_type="Qubit", *args, **kwargs)
        self.sample_matcher()

    def sample_matcher(self):
        dlg = ResultsSampleMatcher(
            parent=None,
            results_var_name="original_sample_conc.",
            results=self.parsed_info,
            samples=self.procedure.proceduresampleassociation,
            procedure=self.procedure,
            results_type="Qubit"
        )
        if dlg.exec():
            for result in dlg.output:
                result.save()

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        for item in super().parsed_info:
            item['date_analyzed'] = item['test_date']
            yield item
