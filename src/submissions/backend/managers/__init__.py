import logging
from pathlib import Path
from backend.db.models import ProcedureType
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultManager(object):

    def __init__(self, proceduretype: ProcedureType, parent, fname: Path | str | None = None):
        logger.debug(f"FName before correction: {fname}")
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        self.proceduretype = proceduretype
        if fname != "no_file":
            if not fname:
                self.fname = select_open_file(file_extension="xlsx", obj=get_application_from_parent(parent))
            elif isinstance(fname, str):
                self.fname = Path(fname)
        logger.debug(f"FName after correction: {fname}")

