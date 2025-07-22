
from __future__ import annotations
import logging
from .. import DefaultManager
from backend.db.models import Procedure
from pathlib import Path
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from backend.validators.pydant import PydResults


logger = logging.getLogger(f"submission.{__name__}")

class DefaultResultsManager(DefaultManager):

    def __init__(self, procedure: Procedure, parent, fname: Path | str | None = None):
        logger.debug(f"FName before correction: {fname}")
        self.procedure = procedure
        if not fname:
            self.fname = select_open_file(file_extension="xlsx", obj=get_application_from_parent(parent))
        elif isinstance(fname, str):
            self.fname = Path(fname)
        logger.debug(f"FName after correction: {fname}")

    def procedure_to_pydantic(self) -> PydResults:
        info = self.info_parser.to_pydantic()
        info.parent = self.procedure
        return info

    def samples_to_pydantic(self) -> List[PydResults]:
        sample = [item for item in self.sample_parser.to_pydantic()]
        return sample

from .pcr_results_manager import PCRManager
