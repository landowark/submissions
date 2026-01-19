"""
Module for managing Runs object
"""
from __future__ import annotations
import logging, sys
from pprint import pformat
from openpyxl.workbook.workbook import Workbook
from backend.managers import DefaultManager
from frontend.widgets.functions import select_save_file

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultRunManager(DefaultManager):

    def write(self, workbook: Workbook | None = None) -> Workbook:
        from backend.managers import DefaultClientSubmissionManager, DefaultProcedureManager
        from backend.db.models import Procedure
        logger.info(f"Initializing write")
        
        clientsubmission = self.pyd.sql_instance.clientsubmission
        # Question: what the hell is this even for?
        # Answer: It's to write all the client submission info apparently
        self.clientsubmission = DefaultClientSubmissionManager(parent=self.parent, 
                                                               input_object=clientsubmission, 
                                                               submissiontype=clientsubmission.submissiontype.name)
        if not workbook:
            workbook = Workbook()
        workbook = self.clientsubmission.write(workbook=workbook)
        self.procedures = []
        for procedure in self.pyd.sql_instance.procedure:
            
            logger.debug(f"Procedure: {pformat(procedure)}")

            procedure = DefaultProcedureManager(parent=self.parent, input_object=procedure)
            workbook: Workbook = procedure.write(workbook=workbook)
            self.procedures.append(procedure)
        return workbook
