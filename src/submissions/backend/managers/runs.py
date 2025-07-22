from __future__ import annotations
import logging
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.workbook.workbook import Workbook
from tools import copy_xl_sheet


from backend.managers import DefaultManager

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultRunManager(DefaultManager):

    def write(self) -> Workbook:
        from backend.managers import DefaultClientSubmissionManager, DefaultProcedureManager
        logger.debug(f"Initializing write")
        clientsubmission = DefaultClientSubmissionManager(parent=self.parent, input_object=self.pyd.clientsubmission, submissiontype=self.pyd.clientsubmission.submissiontype)
        workbook = clientsubmission.write()
        for procedure in self.pyd.procedure:
            logger.debug(f"Running procedure: {procedure}")
            procedure = DefaultProcedureManager(proceduretype=procedure.proceduretype.name, parent=self.parent, input_object=procedure)
            wb: Workbook = procedure.write()
            for sheetname in wb.sheetnames:
                source_sheet = wb[sheetname]
                ws = workbook.create_sheet(sheetname)
                copy_xl_sheet(source_sheet, ws)
        return workbook
