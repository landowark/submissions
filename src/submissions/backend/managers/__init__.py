"""
Module for manager defaults.
"""
from __future__ import annotations
from logging import getLogger
from typing import List
logger = getLogger(f"submissions.{__name__}")
from copy import deepcopy
from pathlib import Path
from frontend.widgets.functions import select_open_file
from tools import get_application_from_parent
from backend.validators import pydant
from backend.db.models import BaseClass

from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from PIL.ImageFile import ImageFile
from csv import reader as csvreader


class DefaultManager(object):

    """
    The job of the manager class is to convert all inputs into a Pydantic object for portability.
    This object will be stored as self.pyd
    """

    def __new__(cls, *args, **kwargs):
        """
        Is called before __init__. Ensures filepath is present.
        """
        try:
            input_object = kwargs.get('input_object') or args[1]
        except IndexError:
            input_object = None
        if isinstance(input_object, str):
            input_object = Path(input_object)
        if isinstance(input_object, Path):
            try:
                assert input_object.exists()
            except AssertionError:
                raise FileNotFoundError(f"File {input_object} does not exist.")
        instance = super().__new__(cls)
        instance.input_object = input_object
        return instance

    def __init__(self, parent, input_object: Path | str | pydant.PydBaseClass | BaseClass | Workbook | Worksheet | None = None, **kwargs):
        self.parent = parent
        self.input_object = input_object
        self.sheets = self.set_sheets()
        self.set_pyd()

    def set_sheets(self) -> List[dict]:
        try:
            return self.__class__.sheets
        except AttributeError:
            return [dict(sheet="Client Info", start_row=1)]

    def set_pyd(self, _depth: int=0):
        if _depth > 2:
            raise RecursionError("set_pyd called too many times; could not resolve input_object.")
        logger.debug(f"Setting pydantic object for input: {self.input_object}")
        match self.input_object:
            case Workbook() | Worksheet() | ImageFile():
                self.pyd = self.parse()
            case _ if issubclass(self.input_object.__class__, pydant.PydBaseClass):
                self.pyd = self.input_object
            case _ if issubclass(self.input_object.__class__, BaseClass):
                self.pyd = self.input_object.to_pydantic()
            case _:
                logger.warning(f"Unmatched input object: {type(self.input_object)}. Looking for file.")
                if self.parent is not None:
                    # TODO: Allow for multiple filters. For now, just look for xlsx.
                    self.input_object = select_open_file(filetypes="Excel Files (*.xlsx)", obj=get_application_from_parent(self.parent))
                    if self.input_object is not None:
                        self.set_pyd(_depth=_depth + 1)
                else:
                    raise ValueError(f"No parent, cannot get user input.")

    def parse(self):
        raise NotImplementedError("Parse only implemented in subclasses.")

    @property
    def _pyd_object(self):
        try:
            return getattr(pydant, f"Pyd{self.__class__.__name__.replace('Manager', '').replace('Default', '')}")
        except AttributeError as e:
            logger.exception(
                f"Couldn't get pyd object: Pyd{self.__class__.__name__.replace('Manager', '').replace('Default', '')}, using {self.__class__.pyd_name}")
            try:
                return getattr(pydant, self.__class__.pyd_name)
            except AttributeError:
                logger.exception(f"Couldn't get pyd object using pyd_name. Returning None")
                return None
        
    @classmethod
    def csv2xlsx(cls, filepath):
        wb = Workbook()
        ws = wb.active
        with open(filepath, "r") as f:
            reader = csvreader(f, delimiter=",")
            for row in reader:
                ws.append(row)
        return wb, ws

    def to_pydantic(self):
        return self.pyd

    def get_worksheet(self, sheet: Worksheet | str | int = 0):
        match sheet:
            case Worksheet():
                return sheet
            case str():
                return self.input_object[sheet]
            case int():
                return self.input_object.worksheets[sheet - 1]
            case _:
                raise TypeError(f"Invalid type for worksheet retrieval: {type(sheet)}")


from .clientsubmissions import *
from .procedures import *
from .results import *
from .runs import *
