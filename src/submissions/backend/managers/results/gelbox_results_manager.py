"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from pathlib import Path
from PIL import Image
from backend.validators.pydant import PydProcedure, PydResults
from backend.managers.results import DefaultImageManager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.db.models import ResultsType

class GelManager(DefaultImageManager):

    resultstype = "Gel Box"

    def __init__(self, procedure: PydProcedure, parent, input_object: Path | str | Image, resultstype: str | ResultsType):
        super().__init__(procedure, parent, input_object)
        if resultstype:
            self.resultstype = resultstype if isinstance(resultstype, str) else resultstype.name
        else:
            self.resultstype = None

    def parse(self):
        from backend.excel.parsers.results_parsers import GelBoxParser
        parser = GelBoxParser(procedure=self.procedure, img=self.input_object, resultstype=self.resultstype)
        if parser.exec():
            print(parser.controls_form.parse_form())
            return PydResults(
                resultstype=self.resultstype, 
                result=parser.controls_form.parse_form(),
                image=self.input_object.tobytes()
            )
        

    
__all__ = ["GelManager"]