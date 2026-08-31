"""
Module for pcr results from Design and Analysis Studio
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from backend.managers.results import DefaultImageManager


class GelManager(DefaultImageManager):

    resultstype = "Gel Box"
            
    def parse(self):
        from backend.excel.parsers.results_parsers import GelBoxParser
        parser = GelBoxParser(procedure=self.procedure)

    def procedure_to_pydantic(self):
        pass
            
__all__ = ["GelManager"]