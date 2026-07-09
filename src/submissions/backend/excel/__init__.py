"""
Contains pandas and openpyxl convenience functions for interacting with excel workbooks
"""

from openpyxl import worksheet
from copy import copy


def copy_xl_sheet(source_sheet, target_sheet):
    """
    Copy a sheet's values with style, format, layout, etc. from one Excel sheet to another

    Args:
        source_sheet (Worksheet): Input sheet
        target_sheet (Worksheet): Output sheet
    """
    copy_cells(source_sheet, target_sheet)  # copy all the cell values and styles
    copy_sheet_attributes(source_sheet, target_sheet)

def copy_sheet_attributes(source_sheet, target_sheet):
    """
    Copy a sheet's style, format, layout, etc. from one Excel sheet to another

    Args:
        source_sheet (Worksheet): Input sheet
        target_sheet (Worksheet): Output sheet
    """
    if isinstance(source_sheet, worksheet._read_only.ReadOnlyWorksheet):
        return
    target_sheet.sheet_format = copy(source_sheet.sheet_format)
    target_sheet.sheet_properties = copy(source_sheet.sheet_properties)
    target_sheet.merged_cells = copy(source_sheet.merged_cells)
    target_sheet.page_margins = copy(source_sheet.page_margins)
    target_sheet.freeze_panes = copy(source_sheet.freeze_panes)

    # NOTE: set row dimensions
    # NOTE: So you cannot copy the row_dimensions attribute. Does not work (because of meta data in the attribute I think). So we copy every row's row_dimensions. That seems to work.
    for rn in range(len(source_sheet.row_dimensions)):
        target_sheet.row_dimensions[rn] = copy(source_sheet.row_dimensions[rn])

    if source_sheet.sheet_format.defaultColWidth is None:
        logger.error('Unable to copy default column wide')
    else:
        target_sheet.sheet_format.defaultColWidth = copy(source_sheet.sheet_format.defaultColWidth)

    # NOTE: set specific column width and hidden property
    # NOTE: we cannot copy the entire column_dimensions attribute so we copy selected attributes
    for key, _ in source_sheet.column_dimensions.items():
        target_sheet.column_dimensions[key].min = copy(source_sheet.column_dimensions[
                                                           key].min)  # Excel actually groups multiple columns under 1 key. Use the min max attribute to also group the columns in the targetSheet
        target_sheet.column_dimensions[key].max = copy(source_sheet.column_dimensions[
                                                           key].max)  # https://stackoverflow.com/questions/36417278/openpyxl-can-not-read-consecutive-hidden-columns discussed the issue. Note that this is also the case for the width, not onl;y the hidden property
        target_sheet.column_dimensions[key].width = copy(
            source_sheet.column_dimensions[key].width)  # set width for every column
        target_sheet.column_dimensions[key].hidden = copy(source_sheet.column_dimensions[key].hidden)


def copy_cells(source_sheet, target_sheet):
    """
    Copy a sheet's values from one Excel sheet to another

    Args:
        source_sheet (Worksheet): Input sheet
        target_sheet (Worksheet): Output sheet
    """
    for r, row in enumerate(source_sheet.iter_rows()):
        for c, cell in enumerate(row):
            source_cell = cell
            if isinstance(source_cell, cell.read_only.EmptyCell):
                continue
            target_cell = target_sheet.cell(column=c + 1, row=r + 1)
            target_cell._value = source_cell._value
            target_cell.data_type = source_cell.data_type
            if source_cell.has_style:
                target_cell.font = copy(source_cell.font)
                target_cell.border = copy(source_cell.border)
                target_cell.fill = copy(source_cell.fill)
                target_cell.number_format = copy(source_cell.number_format)
                target_cell.protection = copy(source_cell.protection)
                target_cell.alignment = copy(source_cell.alignment)
            if not isinstance(source_cell, cell.ReadOnlyCell) and source_cell.hyperlink:
                target_cell._hyperlink = copy(source_cell.hyperlink)
            if not isinstance(source_cell, cell.ReadOnlyCell) and source_cell.comment:
                target_cell.comment = copy(source_cell.comment)



from .parsers import *
from .writers import *
from .reports import *
