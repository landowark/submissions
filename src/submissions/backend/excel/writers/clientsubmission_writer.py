"""
Module for ClientSubmission writing
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from openpyxl.cell import MergedCell
from openpyxl.workbook import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from . import DefaultKEYVALUEWriter, DefaultTABLEWriter
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from backend.validators.pydant import PydClientSubmission, PydClientSubmissionSampleAssociation


class ClientSubmissionInfoWriter(DefaultKEYVALUEWriter):
    """
    Derived from DefaultKEYVALUEWriter to handle writing of PydClientSubmission info as Key | Value pairs to Excel files.

    :ivar pydantic_object: Object to be written to file.
    """

    def __init__(self, pydant_obj: PydClientSubmission, *args, **kwargs):
        """
        :param pydant_obj: PydClientSubmission object to be written.
        :type pydant_obj: PydClientSubmission
        """
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        # Add comment back due to exclusion
        self.fill_dictionary['comment'] = pydant_obj.comment

    def prewrite(self, worksheet: Worksheet, start_row: int = 1, **kwargs) -> Worksheet:
        """
        Delineates start row as 'Submitter Info'.

        :param worksheet: The worksheet which to prepare.
        :type worksheet: Worksheet
        :param start_row: The row to which to write. Defaults to 1
        :type start_row: int
        :returns: Worksheet with 'Submitter Info' starting row marked.
        :rtype: Worksheet.
        """
        worksheet.cell(row=start_row, column=1, value="Submitter Info")
        worksheet.cell(row=start_row, column=1).alignment = Alignment(horizontal="center")
        worksheet.cell(row=start_row, column=1).font = Font(bold=True, color="FFFFFF")
        worksheet.cell(row=start_row, column=1).fill = PatternFill(start_color='376589', end_color='376589', fill_type="solid")
        worksheet.cell(row=start_row, column=2).fill = PatternFill(start_color='376589', end_color='376589', fill_type="solid")
        return worksheet


class ClientSubmissionSampleWriter(DefaultTABLEWriter):
    """
    Derived from DefaultTABLEWriter to handle writing of ClientSubmissionSampleAssociations as to rows of Excel files. One object per row.

    :ivar pydantic_object: Object to be written to file.
    """

    def __init__(self, pydant_obj, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: List[PydClientSubmissionSampleAssociation]
        """
        self.submissiontype = pydant_obj.submissiontype
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.pydant_obj = self.pad_submission_samples_to_length()
        self.excluded = self.pydant_obj[0].class_config.excluded
        self.key_value_order = self.pydant_obj[0].class_config.key_value_order

    # def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
    #                       start_row: int | None = None, *args, **kwargs) -> Workbook:
        
    #     workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row, *args, **kwargs)
    #     return workbook

    def postwrite(self, worksheet: Worksheet, **kwargs) -> Worksheet:
        """
        Formats start row and best fits columns (super). Followed by setting bad cell values to ""

        :param worksheet: The worksheet which to format.
        :type worksheet: Worksheet
        :returns: Formatted worksheet.
        :rtype: Worksheet
        """
        worksheet = super().postwrite(worksheet, **kwargs)
        for row in worksheet.iter_rows(min_row=self.start_row, max_row=self.end_row):
            for cell in row:
                if cell.value in [0, "0", "None"]:
                    if isinstance(cell, MergedCell):
                        continue
                    else:
                        cell.value = ""
                cell.alignment = Alignment(horizontal="center")
        return worksheet
    
    def pad_submission_samples_to_length(self) -> List[PydClientSubmissionSampleAssociation]:
        """
        Creates blank PydClientSubmissionSampleAssociation objects to fill in blank rows.

        Use: Submissions currently can have empty rows to allow for referencing on the plate map.

        :returns: Padded list of objects sorted by submission_rank.
        :rtype: List[PydClientSubmissionSampleAssociation]
        """
        from backend.validators.pydant import PydClientSubmissionSampleAssociation
        output_samples = []
        rng = self.pydant_obj.max_sample_rank + 1
        for iii in range(1, rng):
            iterator = self.pydant_obj.sql_instance.clientsubmissionsampleassociation
            try:
                sample = next(item.to_pydantic() for item in iterator if item.submission_rank == iii)
            except StopIteration:
                sample = PydClientSubmissionSampleAssociation(sample="", clientsubmission=self.pydant_obj.name, submission_rank=iii)
            output_samples.append(sample)
        return sorted(output_samples, key=lambda x: x.submission_rank)


__all__ = ["ClientSubmissionInfoWriter", "ClientSubmissionSampleWriter"]