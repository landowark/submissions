"""
Module for managing Runs object
"""
from __future__ import annotations
import logging, sys
from pprint import pformat
from openpyxl.workbook.workbook import Workbook
from backend.managers import DefaultManager

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultRunManager(DefaultManager):

    def write(self) -> Workbook:
        from backend.managers import DefaultClientSubmissionManager, DefaultProcedureManager
        logger.info(f"Initializing write")
        clientsubmission = DefaultClientSubmissionManager(parent=self.parent, input_object=self.pyd.clientsubmission, submissiontype=self.pyd.clientsubmission.submissiontype)
        workbook = Workbook()
        workbook = clientsubmission.write(workbook=workbook)
        for procedure in self.pyd.procedure:
            procedure = DefaultProcedureManager(proceduretype=procedure.proceduretype, parent=self.parent, input_object=procedure)
            workbook: Workbook = procedure.write(workbook=workbook)
        return workbook
