"""

"""
from __future__ import annotations
import logging
from pathlib import Path
from string import ascii_lowercase
from typing import Generator, TYPE_CHECKING, Literal
from openpyxl.reader.excel import load_workbook
from tools import row_keys
from . import DefaultKEYVALUEParser, DefaultTABLEParser
if TYPE_CHECKING:
    from backend.db.models import SubmissionType

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionTyperMixin(object):

    @classmethod
    def retrieve_submissiontype(cls, filepath: Path) -> "SubmissionType":
        """
        Gets the submission type from a file.

        Args:
            filepath (Path): The import file

        Returns:
            SubmissionType: The determined submissiontype
        """
        # NOTE: Attempt 1, get from form properties:
        sub_type = cls.get_subtype_from_properties(filepath=filepath)
        if not sub_type:
            # NOTE: Attempt 2, get by opening file and using default parser
            logger.warning(
                f"Getting submissiontype from file properties failed, falling back on preparse.\nDepending on excel structure this might yield an incorrect submissiontype")
            sub_type = cls.get_subtype_from_preparse(filepath=filepath)
        if not sub_type:
            logger.warning(
                f"Getting submissiontype from preparse failed, falling back on filename regex.\nDepending on excel structure this might yield an incorrect submissiontype")
            sub_type = cls.get_subtype_from_regex(filepath=filepath)
        return sub_type

    @classmethod
    def get_subtype_from_regex(cls, filepath: Path) -> "SubmissionType":
        """
        Uses regex of the file name to determine submissiontype

        Args:
            filepath (Path): The import file

        Returns:
            SubmissionType: The determined submissiontype
        """
        from backend.db.models import SubmissionType
        regex = SubmissionType.regex
        m = regex.search(filepath.__str__())
        try:
            sub_type = m.lastgroup
        except AttributeError as e:
            sub_type = None
            logger.critical(f"No submission type or procedure type found!: {e}")
        sub_type = SubmissionType.query(name=sub_type, limit=1)
        if not sub_type:
            return
        return sub_type

    @classmethod
    def get_subtype_from_preparse(cls, filepath: Path) -> "SubmissionType":
        """
        Performs a default parse of the file in an attempt to find the submission type.

        Args:
            filepath (Path): The import file

        Returns:
            SubmissionType: The determined submissiontype
        """
        from backend.db.models import SubmissionType
        parser = ClientSubmissionInfoParser(filepath=filepath, submissiontype=SubmissionType.query(name="Test"))
        sub_type = next((value for k, value in parser.parsed_info.items() if k == "submissiontype" or k == "submission_type"), None)
        sub_type = SubmissionType.query(name=sub_type.title())
        if isinstance(sub_type, list):
            return
        return sub_type

    @classmethod
    def get_subtype_from_properties(cls, filepath: Path) -> "SubmissionType":
        """
        Attempts to get submission type from the xl metadata.

        Args:
            filepath (Path): The import file

        Returns:
            SubmissionType: The determined submissiontype
        """
        from backend.db.models import SubmissionType
        wb = load_workbook(filepath)
        # NOTE: Gets first category in the metadata.
        categories = wb.properties.category.split(";")
        sub_type = next((item.strip().title() for item in categories), None)
        sub_type = SubmissionType.query(name=sub_type)
        if isinstance(sub_type, list):
            return
        return sub_type


class ClientSubmissionInfoParser(DefaultKEYVALUEParser, SubmissionTyperMixin):
    """
    Object for retrieving submitter info from "Client Info" sheet
    """

    pyd_name = "PydClientSubmission"

    def __init__(self, filepath: Path | str, submissiontype: "SubmissionType" | None = None, *args, **kwargs):
        logger.debug(f"Set submission type: {submissiontype}")
        if not submissiontype:
            self.submissiontype = self.retrieve_submissiontype(filepath=filepath)
        else:
            self.submissiontype = submissiontype
        super().__init__(filepath=filepath, sheet="Client Info", start_row=1, **kwargs)
        # NOTE: move to the manager class.
        # allowed_procedure_types = [item.name for item in self.submissiontype.proceduretype]
        # for name in allowed_procedure_types:
        #     if name in self.workbook.sheetnames:
        #         # TODO: check if run with name already exists
        #         add_run = QuestionAsker(title="Add Run?", message="We've detected a sheet corresponding to an associated procedure type.\nWould you like to add a new run?")
        #         if add_run.accepted:
        #         # NOTE: recruit parser.
        #             try:
        #                 manager = getattr(procedure_managers, name)
        #             except AttributeError:
        #                 manager = procedure_managers.DefaultManager
        #             self.manager = manager(proceduretype=name)
        #         pass

    @property
    def parsed_info(self):
        output = {k: v for k, v in super().parsed_info}
        try:
            output['clientlab'] = output['client_lab']
        except KeyError:
            pass
        # output['submissiontype'] = dict(value=self.submissiontype.name.title())
        try:
            output['submissiontype'] = output['submission_type']
            output['submissiontype']['value'] = self.submissiontype.name.title()
        except KeyError:
            pass
        logger.debug(f"Data: {output}")
        return output


class ClientSubmissionSampleParser(DefaultTABLEParser, SubmissionTyperMixin):
    """
    Object for retrieving submitter samples from "sample list" sheet
    """

    pyd_name = "PydSample"

    def __init__(self, filepath: Path | str, submissiontype: "SubmissionType" | None = None, start_row: int = 1, *args,
                 **kwargs):
        if not submissiontype:
            self.submissiontype = self.retrieve_submissiontype(filepath=filepath)
        else:
            self.submissiontype = submissiontype
        super().__init__(filepath=filepath, sheet="Client Info", start_row=start_row, **kwargs)

    @property
    def parsed_info(self) -> Generator[dict, None, None]:
        output = super().parsed_info
        for ii, sample in enumerate(output, start=1):
            # logger.debug(f"Parsed info sample: {sample}")

            if isinstance(sample["row"], str) and sample["row"].lower() in ascii_lowercase[0:8]:
                try:
                    sample["row"] = row_keys[sample["row"]]
                except KeyError:
                    pass
            sample['submission_rank'] = ii
            yield sample

    def to_pydantic(self):
        logger.debug(f"Attempting to pydantify: {self._pyd_object}")
        return [self._pyd_object(**sample) for sample in self.parsed_info if sample['sample_id']]
