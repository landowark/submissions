import logging
from .. import DefaultManager
from backend.db.models import Procedure
from pathlib import Path
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent

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

from .pcr_results_manager import PCRManager
