"""
Module for default excel writers
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from numpy import nan as npnan
from typing import List
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from pandas import DataFrame
from openpyxl.utils.dataframe import dataframe_to_rows
from tools import flatten_list, sort_dict_by_list, handle_keys, handle_results


class DefaultWriter(object):
    """
    Default object to handle writing of pydantic objects to Excel files.

    :cvar start_row: Default row to start writing at.
    :ivar pydantic_object: Object to be written to file.
    """

    start_row = 1

    def __repr__(self):
        try:
            return f"{self.__class__.__name__}<{self.filepath.stem}>"
        except AttributeError:
            return f"{self.__class__.__name__}<Unknown Filepath>"

    def __init__(self, pydant_obj, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydBaseClass
        """
        self.pydant_obj = pydant_obj
        if isinstance(self.pydant_obj, list):
            self.write_sheet = pydant_obj[0].class_config.write_sheet
        else:
            self.write_sheet = pydant_obj.class_config.write_sheet
        
    
    
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int | None = None, *args, **kwargs):
        """
        Write to a named sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param sheet: The name of the sheet to which to write. Defaults to None. If None will attempt to get from cvar Writer.sheet
        :type type: str | None
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        
        if not sheet:
            sheet = self.write_sheet
        self.sheet = sheet
        sheetnames = workbook.sheetnames
        if isinstance(sheetnames, property):
            try:
                sheetnames = sheetnames.fget(workbook)
            except Exception as e:
                logger.exception(f"Couldn't resolve workbook sheetnames property due to {e}")
                sheetnames = []
        if self.sheet not in sheetnames:
            try:
                logger.debug(f"Attempting to name first sheet '{self.sheet}'")
                self.worksheet = workbook["Sheet"]
                self.worksheet.title = self.sheet
            except KeyError:
                logger.error(f"First sheet already taken, making new sheet.")
                self.worksheet = workbook.create_sheet(title=self.sheet)
        else:
            self.worksheet = workbook[self.sheet]
        try:
            assert hasattr(self, "worksheet")
        except AssertionError:
            raise AssertionError(f"This object {self} has no worksheet")
        start_row = self.delineate_start_row(start_row=start_row)
        self.worksheet = self.prewrite(self.worksheet, start_row=start_row)
        self.start_row = self.delineate_start_row(start_row=start_row)
        # NOTE: Declared in child classes
        self.end_row = self.delineate_end_row(start_row=start_row)
        return workbook

    def delineate_start_row(self, start_row: int | None = None) -> int:
        """
        Gets the first black row.

        :param start_row: row to start looking at. Defaults to 1.
        :type start_row: int
        :returns: First row including/after start_row with all negative values
        :rtype: int
        """
        if not start_row:
            try:
                start_row = self.__class__.start_row
            except AttributeError as e:
                logger.exception(f"Couldn't get start row due to {e}")
                start_row = 1
        for iii, row in enumerate(self.worksheet.iter_rows(min_row=start_row), start=start_row):
            if all([item.value is None for item in row]):
                return iii
        if self.worksheet.max_row == 1:
            return self.worksheet.max_row + 1
        else:
            return self.worksheet.max_row + 2

    def prewrite(self, worksheet: Worksheet, **kwargs) -> Worksheet:
        """
        Steps taken to make a worksheet ready to receive values.

        To be defined in child classes.

        :param worksheet: The worksheet which to prepare.
        :type worksheet: Worksheet
        :returns: In this case, the same worksheet.
        """
        return worksheet

    @classmethod
    def columns_best_fit(cls, worksheet: Worksheet) -> Worksheet:
        """
        Make all columns' widths best fit.

        :param worksheet: The worksheet on which to change column widths.
        :type worksheet: 
        """
        for col in worksheet.columns:
            setlen = 0
            try:
                column = col[0].column_letter  # Get the column name
            except AttributeError:
                continue
            for cell in col:
                if len(str(cell.value)) > setlen:
                    setlen = len(str(cell.value))
            set_col_width = setlen + 5
            # Note: Setting the column width
            worksheet.column_dimensions[column].width = set_col_width
        return worksheet


class DefaultKEYVALUEWriter(DefaultWriter):
    """
    Default object to handle writing of pydantic objects as Key | Value pairs to Excel files.

    :ivar pydantic_object: Object to be written to file.
    """
    
    def __init__(self, pydant_obj, exclude: list | None = None, order: list | None = None, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydBaseClass
        """
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.excluded = exclude or []
        self.key_value_order = order or []
        logger.debug(f"Creating fill dictionary for {self.pydant_obj}")
        fill_dictionary = {k: v for k, v in self.pydant_obj.improved_dict.items() if k not in self.excluded}
        self.fill_dictionary = sort_dict_by_list(fill_dictionary, self.key_value_order)

    def delineate_end_row(self, start_row: int = 1) -> int:
        """
        Calculates the ending row of a contiguous series of rows.

        :param start_row: The row to start looking at. Defaults to 1
        :type start_row: int
        :returns: len(self.fill_dictionary) + start_row
        :rtype: int 
        """
        return len(self.fill_dictionary) + start_row

    # @classmethod
    # def check_location(cls, locations: list, sheet: str):
    #     return any([item['sheet'] == sheet for item in locations])

    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, 
                          *args, **kwargs) -> Workbook:
        """
        Write to a named sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param sheet: The name of the sheet to which to write. Defaults to None. If None will attempt to get from cvar Writer.sheet
        :type type: str | None
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row)
        for ii, (k, v) in enumerate(self.fill_dictionary.items(), start=self.start_row):
            self.worksheet.cell(column=1, row=ii, value=handle_keys(k))
            value = handle_results(v, html=False)
            if value is None:
                continue
            self.worksheet.cell(column=2, row=ii, value=value)
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        """
        Steps taken to properly format a worksheet after it contains values..

        :param worksheet: The worksheet which to format.
        :type worksheet: Worksheet
        """
        worksheet = self.columns_best_fit(worksheet=worksheet)
        return worksheet


class DefaultTABLEWriter(DefaultWriter):
    """
    Default object to handle writing of pydantic objects as to rows of Excel files. One object per row.

    :ivar pydantic_object: Object to be written to file.
    """

    linked: tuple[str, str] | None = None

    def __init__(self, pydant_obj, actual_objs_type: str | None = None, exclude: list | None = None, order: list | None = None, *args, **kwargs):
        """
        :param pydant_obj: Object to be written to file.
        :type pydant_obj: PydBaseClass
        :param actual_objs_type: Gets what actual obj this is supposed to be from the original object. (Ex. Get PydSample from PydClientSubmissionSampleAssociation)
        :type actual_objs_type: str
        """
        super().__init__(pydant_obj=pydant_obj, *args, **kwargs)
        self.pydant_obj = getattr(self.pydant_obj, actual_objs_type) if actual_objs_type else self.pydant_obj
        # try:
        #     self.excluded = self.pydant_obj[0].class_config.excluded if isinstance(self.pydant_obj, list) else self.pydant_obj.class_config.excluded
        # except (IndexError, AttributeError, TypeError) as e:
        #     logger.exception(f"Error occurred while initializing TABLE writer: {e}")
        #     self.excluded = []
        self.excluded = exclude or []
        # try:
        #     self.key_value_order = self.pydant_obj[0].class_config.key_value_order if isinstance(self.pydant_obj, list) else self.pydant_obj.class_config.key_value_order
        # except (IndexError, AttributeError, TypeError) as e:
        #     logger.exception(f"Error occurred while initializing TABLE writer: {e}")
        #     self.key_value_order = []
        self.key_value_order = order or []

    # def get_row_count(self, start_row: int = 1):
    #     list_df = DataFrame([item for item in self.worksheet.values][start_row - 1:])
    #     row_count = list_df.shape[0]
    #     return row_count

    def delineate_end_row(self, start_row: int = 1) -> int:
        """
        Calculates the ending row of a contiguous series of rows.

        :param start_row: The row to start looking at. Defaults to 1
        :type start_row: int
        :returns: start_row + len(self.pydant_obj) + 2
        :rtype: int 
        """
        return start_row + len(self.pydant_obj) + 2
        
    def write_to_workbook(self, workbook: Workbook, sheet: str | None = None,
                          start_row: int = 1, 
                          records: List[dict] | None = None, *args, **kwargs) -> Workbook:
        """
        Write to a named sheet of a provided workbook. Will create new sheet if named one doesn't exist.

        :param workbook: The workbook object to be written to.
        :type workbook: Workbook
        :param sheet: The name of the sheet to which to write. Defaults to None. If None will attempt to get from cvar Writer.sheet
        :type type: str | None
        :param start_row: Row in which to start writing. Defaults to None. 
        :type start row: int | None
        :param records: List of objects to write to rows. One record per row.
        :type records: List[dict]
        :returns: Workbook with values written.
        :rtype: Workbook
        """
        workbook = super().write_to_workbook(workbook=workbook, sheet=sheet, start_row=start_row, *args, **kwargs)
        # start_row = self.start_row
        if records is None:
            records = self.build_records()
        self._records = records
        df = DataFrame(records)[self.sorted_header_row]
        df.replace("", npnan, inplace=True)

        # Serialize list-valued columns so relationship fields like tipslot are preserved
        for column in df.columns:
            if df[column].apply(lambda value: isinstance(value, list)).any():
                df[column] = df[column].apply(
                    lambda value: "\n".join(str(item) for item in value) if isinstance(value, list) else value
                )

        # Identify columns where ALL values are zero
        is_all_zero = (df == 0).all()

        # Drop columns where the data is empty
        df = df.loc[:, ~is_all_zero]
        df.dropna(axis=1, how='all', inplace=True)
        df.fillna("", inplace=True)
        df.drop(columns=[col for col in df.columns if col in self.excluded], inplace=True, errors='ignore')
        # Rename column Headers.
        df = df.rename(columns=handle_keys)
        rows = dataframe_to_rows(df, index=False, header=True)
        for r_idx, row in enumerate(rows, self.start_row):
            for c_idx, value in enumerate(row, 1):
                value = handle_results(value, html=False)
                if value is None:
                    continue
                self.worksheet.cell(row=r_idx, column=c_idx, value=value)
        self.worksheet = self.postwrite(self.worksheet)
        return workbook

    # @property
    # def sorted_header_row(self) -> List[str]:
    #     """
    #     Sorts table header row based on the key_value_order from the pydant_obj class_config.

    #     :returns: List of key_value_order strings plus an alphabetical list of remaining fields.
    #     :rtype: List[str]
    #     """
    #     output = []
    #     header_list = list(set(flatten_list([item.fields for item in self.pydant_obj])))
    #     class_config = self.pydant_obj[0].class_config
    #     for item in class_config.key_value_order:
    #         if item in [header for header in header_list if header not in self.excluded]:
    #             output.append(header_list.pop(header_list.index(item)))
    #     return output + sorted([item for item in header_list if item not in self.excluded])

    def linked_object(self, item, record: dict):
        """
        The SQL object a row links to (see `linked`): the row's own sql_instance link if it has one, else a lookup
        by the name in the row. None if there's no link or it can't be found.
        """
        if self.linked is None:
            return None
        from backend.db import models
        key, class_name = self.linked
        sql_class = getattr(models, class_name)
        found = getattr(getattr(item, "sql_instance", None), key, None)
        if isinstance(found, sql_class):
            return found
        # NOTE: Some associations' to_pydantic (e.g. ProcedureEquipmentAssociation) don't pass sql_instance.
        name = record.get(key)
        if not name:
            return None
        try:
            found = sql_class.query(name=name, limit=1)
        except TypeError:
            return None
        return found if isinstance(found, sql_class) else None

    def build_records(self) -> List[dict]:
        """
        One dict per row: the row's improved_dict, plus any fields of its linked object (model fields and misc_info)
        that the row doesn't already have, so they can be chosen in the type's *_exclude_order lists.
        """
        records = []
        for item in self.pydant_obj:
            record = dict(getattr(item, "improved_dict", {}) or {})
            linked = self.linked_object(item, record)
            if linked is not None:
                missing = [key for key in linked.pydantic_model().model_fields
                            if key not in record and key not in ("sql_instance", "new")]
                if missing:
                    linked_pyd = linked.to_pydantic()
                    for key in missing:
                        record[key] = linked_pyd.filter_field(key)
                for key, value in (linked.misc_info or {}).items():
                    if key not in record and not key.startswith("_") and "sql_instance" not in key:
                        record[key] = value
            records.append(record)
        return records

    @property
    def sorted_header_row(self) -> List[str]:
        """
        Columns found in the rows: those in the saved order first (the order passed in, else the class_config
        key_value_order), then the rest A-Z. Excluded names are left out.

        :returns: List of key_value_order strings plus an alphabetical list of remaining fields.
        :rtype: List[str]
        """
        records = getattr(self, "_records", None)
        if records is None:
            records = self.build_records()
        headers = []
        for record in records:
            headers += [key for key in record if key not in headers]
        kept = [header for header in headers if header not in self.excluded]
        order = self.key_value_order
        if not order and len(self.pydant_obj):
            order = getattr(getattr(self.pydant_obj[0], "class_config", None), "key_value_order", []) or []
        ordered = [header for header in order if header in kept]
        return ordered + sorted(header for header in kept if header not in ordered)

    def postwrite(self, worksheet: Worksheet) -> Worksheet:
        """
        Steps taken to properly format a worksheet after it contains values.

        :param worksheet: The worksheet which to format.
        :type worksheet: Worksheet
        :returns: Formatted worksheet.
        :rtype: Worksheet
        """
        worksheet = self.columns_best_fit(worksheet=worksheet)
        worksheet = self.format_worksheet_row(worksheet=worksheet, row=self.start_row)
        return worksheet

    @staticmethod
    def format_worksheet_row(worksheet: Worksheet, 
                         row: int,
                         font: dict | None = None,
                         fill: dict | None = None,
                         align: dict | None = None
                         ) -> Worksheet:
        """
        Post-write step to format header row in Excel.

        :param worksheet: The worksheet with the row to be formatted.
        :type worksheet: Worksheet
        :param row: The index of the row to be formatted.
        :type row: int
        :param font: Dictionary of cell font values. Check openpyxl.styles.Font for allowed keys/values. Defaults to None, fallback values in code.
        :type font: dict
        :param fill: Dictionary of cell fill values. Check openpyxl.styles.PatternFill for allowed keys/values. Defaults to None, fallback values in code.
        :type font: dict
        :param align: Dictionary of cell alignment values. Check openpyxl.styles.Alignment for allowed keys/values. Defaults to None, fallback values in code.
        :type align: dict
        :returns: Worksheet with properly formatted row.
        :rtype: Worksheet
        """
        if not font:
            font = dict(color="ffffffff", bold=True)
        if not fill:
            fill = dict(start_color='376589', end_color='376589', fill_type="solid")
        if not align:
            align = dict(horizontal="center")
        font_ = Font(**font)
        fill_ = PatternFill(**fill)
        align_ = Alignment(**align)
        for cell in worksheet[row]:
            cell.font = font_
            cell.fill = fill_
            cell.alignment = align_
        return worksheet


from .procedure_writers import *
from .results_writers import *
from .clientsubmission_writer import *

__all__ = ["DefaultKEYVALUEWriter", "DefaultTABLEWriter", "ProcedureInfoWriter", "ProcedureReagentWriter", "ProcedureEquipmentWriter", 
           "ProcedureSampleWriter", "DefaultResultsInfoWriter", "DefaultResultsSampleWriter", "DiomniPCRInfoWriter", "DiomniPCRSampleWriter", 
           "QubitInfoWriter", "QubitSampleWriter", "ClientSubmissionInfoWriter", "ClientSubmissionSampleWriter"]
