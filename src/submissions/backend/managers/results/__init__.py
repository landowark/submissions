"""
Module for default results manager
"""
from __future__ import annotations
import logging
from .. import DefaultManager
from backend.db.models import Procedure
from pathlib import Path
from frontend.widgets.functions import select_open_file
from openpyxl import Workbook
from tools import get_application_from_parent
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from backend.validators.pydant import PydResults


logger = logging.getLogger(f"submission.{__name__}")

class DefaultResultsManager(DefaultManager):

    def __init__(self, procedure: Procedure, parent, input_object: Path | str | Workbook):
        self.procedure = procedure
        # if not fname:
        #     fname = select_open_file(file_extension=extension, obj=get_application_from_parent(parent))
        # elif isinstance(fname, str):
        #     fname = Path(fname)
        # self.fname = fname
        super().__init__(parent=parent, input_object=input_object)

    def procedure_to_pydantic(self) -> PydResults:
        info = self.info_parser.to_pydantic()
        if info:
            info.parent = self.procedure
        return info

    def samples_to_pydantic(self) -> List[PydResults]:
        sample = [item for item in self.sample_parser.to_pydantic()]
        return sample

from .diomni_pcr_results_manager import DiomniPCRManager
from .qubit_results_manager import QubitManager
