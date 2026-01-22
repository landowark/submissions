"""
Module for manager defaults.
"""
import logging
from pprint import pformat
from pathlib import Path
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent
from backend.validators.pydant import PydBaseClass
from backend.db.models import BaseClass

logger = logging.getLogger(f"submissions.{__name__}")

class DefaultManager(object):

    def __init__(self, parent, input_object: Path | str | None = None):
        self.parent = parent
        # NOTE: If input_object is a str or path, use parser to construct object
        match input_object:
            case str():
                self.input_object = Path(input_object)
                self.pyd = self.to_pydantic()
            case Path():
                self.input_object = input_object
                self.pyd = self.to_pydantic()
            case x if issubclass(input_object.__class__, PydBaseClass):
                self.pyd = input_object
            case x if issubclass(input_object.__class__, BaseClass):
                self.pyd = input_object.to_pydantic()
            case _:
                logger.warning(f"Unmatched input object: {type(input_object)}. Looking for file.")
                self.input_object = select_open_file(file_extension="xlsx", obj=get_application_from_parent(parent))
                self.pyd = self.to_pydantic()
        

from .clientsubmissions import DefaultClientSubmissionManager
from .procedures import DefaultProcedureManager
from .results import DefaultResultsManager
from .runs import DefaultRunManager
