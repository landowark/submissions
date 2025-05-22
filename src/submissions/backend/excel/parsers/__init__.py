"""

"""
from pathlib import Path
from openpyxl import load_workbook
from backend.validators import pydant

class DefaultParser(object):


    default_range_dict = dict(
        start_row=2,
        end_row=18,
        key_column=1,
        value_column=2,
        sheet="Sample List"
    )

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.filepath.stem}>"

    def __init__(self, filepath: Path | str, range_dict: dict | None = None):
        self._pyd_object = getattr(pydant, f"Pyd{self.__class__.__name__.replace('Parser', '')}")
        if isinstance(filepath, str):
            self.filepath = Path(filepath)
        else:
            self.filepath = filepath
        self.workbook = load_workbook(self.filepath, data_only=True)
        if not range_dict:
            self.range_dict = self.__class__.default_range_dict
        else:
            self.range_dict = range_dict

from .submission_parser import *