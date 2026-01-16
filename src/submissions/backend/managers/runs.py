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

    def write(self) -> Workbook:
        from backend.managers import DefaultClientSubmissionManager, DefaultProcedureManager
        logger.info(f"Initializing write")
        default_name = self.pyd.construct_filename()
        output_filepath = select_save_file(obj=self.parent, default_name=default_name, extension="xlsx")
        clientsubmission = self.pyd.sql_instance.clientsubmission
        # Question: what the hell is this even for?
        # Answer: It's to write all the client submission info apparently
        self.clientsubmission = DefaultClientSubmissionManager(parent=self.parent, 
                                                               input_object=clientsubmission, 
                                                               submissiontype=clientsubmission.submissiontype.name)
        workbook = Workbook()
        workbook = self.clientsubmission.write(workbook=workbook)
        self.procedures = []
        for procedure in self.pyd.procedure:
            procedure = DefaultProcedureManager(proceduretype=procedure.proceduretype, parent=self.parent, input_object=procedure)
            workbook: Workbook = procedure.write(workbook=workbook)
            self.procedures.append(procedure)
        return workbook
