"""
Results dialogs for the web UI. Implements the interface of backend.managers.results.QtResultsUI.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import html as html_lib
import json
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
import webview
from tools import convert_well_to_row_column, render_details_template
from .modal import ModalApi, add_buttons, exec_window

# NOTE: Results types the web UI can add. Gel Box still needs its image dialog ported.
WEB_RESULTS_TYPES = {"Diomni PCR", "Qubit"}


class SheetChooserApi(ModalApi):

    def __init__(self):
        super().__init__()
        self._selected = set()

    def toggle(self, name: str, checked: bool) -> None:
        if checked:
            self._selected.add(name)
        else:
            self._selected.discard(name)


class MatcherApi(ModalApi):
    """
    js_api for the results sample matcher. Method names match ResultsSampleMatcher's Qt slots.
    Only records choices; WebResultsUI.match_samples builds the Results on the calling thread.
    """

    def __init__(self):
        super().__init__()
        # NOTE: result_text -> {enabled, sample, result}, keyed like the Qt version.
        self._matches = {}

    def set_match(self, enabled: bool, sample: str, result_text: str, result: str) -> None:
        self._matches[result_text] = dict(enabled=enabled, sample=sample, result=result)

    def update_match(self, sample: str, result_text: str) -> None:
        if result_text in self._matches:
            self._matches[result_text]["sample"] = sample


def _association(procedure, sample: str):
    """
    Finds the procedure's sample association for a 'sample_id' or 'sample_id:well' choice.
    """
    if ":" in sample:
        sample_id, well = sample.split(":", 1)
        row, column = convert_well_to_row_column(well)
    else:
        sample_id, row, column = sample, None, None
    return next((assoc for assoc in procedure.proceduresampleassociation
                if assoc.sample.sample_id == sample_id and assoc.row == row and assoc.column == column), None)


def _sheet_page(sheetnames: list) -> str:
    boxes = "".join(
        f'<label><input type="checkbox" onchange="pywebview.api.toggle('
        f'{html_lib.escape(json.dumps(name))}, this.checked)"> {html_lib.escape(name)}</label><br>'
        for name in sheetnames)
    return f'<html><body style="font: 14px \'Segoe UI\', sans-serif;"><p>Select the sheet to import:</p>{boxes}</body></html>'


class WebResultsUI(object):
    """
    The dialogs the results managers need, shown with pywebview. Use only from a pywebview API call.
    """

    def __init__(self, window):
        # NOTE: Main window, used as the owner of the file picker.
        self._window = window

    def choose_file(self, filetypes: str, parent=None) -> Path | None:
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=(filetypes,))
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])

    def choose_sheets(self, workbook) -> list:
        api = SheetChooserApi()
        if not exec_window("Select Excel Sheet", add_buttons(_sheet_page(workbook.sheetnames)), api, width=380, height=360):
            return []
        return [workbook[name] for name in workbook.sheetnames if name in api._selected]

    def match_samples(self, procedure, results: list, results_var_name: str, results_type: str) -> list:
        from backend.db.models import Results
        api = MatcherApi()
        page = render_details_template("results_sample_match", results=results, results_var_name=results_var_name,
                                        samples=procedure.proceduresampleassociation)
        if not exec_window("Matching results", add_buttons(page), api):
            return []
        output = []
        for result_text, match in api._matches.items():
            if not match["enabled"]:
                continue
            try:     
                result = json.loads(match["result"].replace("'", '"'))
            except JSONDecodeError as e:
                logger.exception(f"Could not decode string: {match['result']} due to\n{e}")
                continue
            date_analyzed = result.pop("date_analyzed", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            output.append(Results(sampleprocedureassociation=_association(procedure, match["sample"]), result=result,
                                resultstype=results_type, date_analyzed=date_analyzed))
        return output                  