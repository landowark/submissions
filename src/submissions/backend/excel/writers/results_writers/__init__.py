"""
Default results writers.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from openpyxl import Workbook
from backend.excel.writers import DefaultKEYVALUEWriter, DefaultTABLEWriter
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from backend.validators.pydant import PydResults


class DefaultResultsInfoWriter(DefaultKEYVALUEWriter):
    """
    Derived from DefaultKEYVALUEWriter to write results info as Key | Value pairs into Excel.

    :cvar exclude: Keys to exclude from writing. 
    :type exclude: List[str]
    :ivar pydantic_object: Object to be written to file.
    """
    exclude = ["excluded", "sampleprocedureassocation", "img", "sample"]

    def __init__(self, pydant_obj: PydResults, *args, **kwargs):
        """
        :param pydant_obj: The object to be written to the Excel book.
        :type pydant_obj: PydResults
        """
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.fill_dictionary = pydant_obj.result
        self.write_sheet = pydant_obj.write_sheet_name
        
    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, start_row: int = 1, *args, **kwargs) -> Workbook:
        """
        Write to a self.sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.write_sheet, start_row=start_row)
        return workbook


class DefaultResultsSampleWriter(DefaultTABLEWriter):
    """
    Derived from DefaultTableWriter to write sample results info as rows into Excel.
    
    :cvar exclude: Keys to exclude from writing.
    :cvar header_order: List of the columns to move to the front.
    """

    exclude = ["excluded", "name", "procedure", "sample", "sampleprocedureassociation", "result", 
               "image", 'img', "plate_barcode", "resultstype", "reagent_lot#", "is_sample"]
    header_order = ["sample_id"]

    def __init__(self, pydant_obj: List[PydResults], *args, **kwargs):
        """
        :param pydant_obj: List of results objects to write.
        :type pydant_obj: List[PydResults]
        """
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        if isinstance(self.pydant_obj, list):
            self.write_sheet = self.pydant_obj[0].write_sheet_name
        else:
            self.write_sheet = self.pydant_obj.write_sheet_name

    # NOTE: Required to pass self.sheet to function.
    def write_to_workbook(self, workbook: Workbook, start_row: int = 1, *args, **kwargs) -> Workbook:
        """
        Write to a named sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        records = [getattr(item, 'improved_dict', {}) for item in self.pydant_obj]
        workbook = super().write_to_workbook(workbook=workbook, sheet=self.write_sheet, start_row=start_row, records=records)
        return workbook


from .qubit_results_writer import *
from .diomni_pcr_results_writer import *

__all__ = ["DefaultResultsInfoWriter", "DefaultResultsSampleWriter", "DiomniPCRInfoWriter", "DiomniPCRSampleWriter", "QubitInfoWriter", "QubitSampleWriter"]
