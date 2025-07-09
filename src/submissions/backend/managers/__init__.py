import logging
from pathlib import Path
from typing import Literal

from backend.db.models import ProcedureType
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent
from backend.validators.pydant import PydBaseClass
from backend.db.models import BaseClass

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultManager(object):

    def __init__(self, parent, input_object: Path | str | None = None):
        logger.debug(f"FName before correction: {input_object}")
        # if input_object != "no_file":
        match input_object:
            case str():
                self.input_object = Path(input_object)
                self.pyd = self.parse()
            case Path():
                self.input_object = input_object
                self.pyd = self.parse()
            case x if issubclass(input_object.__class__, PydBaseClass):
                self.pyd = input_object
            case x if issubclass(input_object.__class__, BaseClass):
                self.pyd = input_object.to_pydantic()
            case _:
                self.input_object = select_open_file(file_extension="xlsx", obj=get_application_from_parent(parent))
                self.pyd = self.parse()
        logger.debug(f"FName after correction: {input_object}")


from .clientsubmissions import DefaultClientSubmission
from .procedures import DefaultProcedure
from.results import DefaultResults
