"""
Results dialogs for the web UI. Implements the interface of backend.managers.results.QtResultsUI.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import html as html_lib
import json
import base64,  re 
from io import BytesIO
from itertools import zip_longest
import numpy as np
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
import webview
from tools import convert_well_to_row_column, render_details_template
from .modal import ModalApi, add_buttons, exec_window

# NOTE: Results types the web UI can add. Gel Box still needs its image dialog ported.
WEB_RESULTS_TYPES = {"Diomni PCR", "Qubit", "Gel Box"}


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

class GelApi(ModalApi):

    def __init__(self):
        super().__init__()
        self._result = None

    def finish(self, result: dict) -> None:
        # NOTE: One call that both stores the form and closes, so no separate update can arrive late.
        self._result = result
        self.accept()


def _gel_controls(procedure, resultstype: str) -> dict:
    """
    Controls table layout, with the same defaults as ControlsForm.
    """
    settings = procedure.load_resultstype_settings(resultstype) or {}
    try:
        tip = "\n".join(f"{item.sample_id} - CELL {item.well}" for item in procedure.sample if item.is_control < 0)
    except TypeError:
        tip = ""
    return dict(
        tip=tip,
        headers=settings.get('column headers', ["Negative Control Key", "Description", "Results - 65 C", "Results - 63 C", "Results - Spike"]),
        ntcs=settings.get('ntcs', ["RSL-NTC", "ENC-NTC", "NTC"]),
        ntc_types=settings.get('ntc types', ["Processing Negative (PBS)", "Extraction Negative (Extraction buffers ONLY)",
                                            "Artic no-template control (mastermix ONLY)"]),
    )


def _png_base64(image) -> str:
    """
    The image as base64 PNG for display, scaled to 8 bits if it's e.g. a 16-bit TIFF.
    """
    from PIL import Image
    if image.mode not in ("L", "RGB", "RGBA"):
        pixels = np.array(image).astype(float)
        span = pixels.max() - pixels.min() or 1
        image = Image.fromarray((255 * (pixels - pixels.min()) / span).astype(np.uint8))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

def _gel_page(title: str, image_b64: str, controls: dict) -> str:
    esc = html_lib.escape
    headers, columns = controls["headers"], controls["headers"][2:]
    head = (f'<th title="{esc(controls["tip"])}" class="{"tip" if controls["tip"] else ""}">{esc(headers[0])}</th>'
            f'<th>{esc(headers[1])}</th>' + "".join(f"<th>{esc(c)}</th>" for c in columns))
    rows = "".join(
        f'<tr><td>{esc(ntc)}</td><td>{esc(ntc_type or "")}</td>'
        + "".join(f'<td><input list="negpos" value="Neg" data-row="{esc(ntc)}" data-col="{esc(c)}"></td>' for c in columns)
        + "</tr>"
        for ntc, ntc_type in zip_longest(controls["ntcs"], controls["ntc_types"]) if ntc)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(title)}</title>
        <style>
        body {{ font: 14px "Segoe UI", sans-serif; margin: 12px; }}
        .viewer {{ height: 55vh; overflow: auto; border: 1px solid #ccc; background: #111; }}
        .viewer img {{ display: block; }}
        .sliders {{ display: flex; gap: 16px; margin: 6px 0 10px; }}
        table {{ border-collapse: collapse; }}
        th, td {{ border: 1px solid #ccc; padding: 3px 6px; text-align: left; }}
        th.tip {{ color: blue; text-decoration: underline; cursor: help; }}
        td input {{ width: 5em; }}
        .bottom {{ display: flex; gap: 16px; align-items: flex-start; }}
        textarea {{ width: 320px; height: 70px; }}
        </style></head><body>
        <div class="viewer"><img id="gel" src="data:image/png;base64,{image_b64}"></div>
        <div class="sliders">
        <label>Zoom <input type="range" id="zoom" min="25" max="400" value="100"></label>
        <label>Brightness <input type="range" id="brightness" min="50" max="300" value="100"></label>
        <label>Contrast <input type="range" id="contrast" min="50" max="300" value="100"></label>
        </div>
        <div class="bottom">
        <table><tr>{head}</tr>{rows}</table>
        <label>Comments:<br><textarea id="comment"></textarea></label>
        </div>
        <datalist id="negpos"><option>Neg</option><option>Pos</option></datalist>
        <div style="padding: 10px 0; display: flex; gap: 8px; justify-content: flex-end;">
        <button type="button" onclick="pywebview.api.cancel()">Cancel</button>
        <button type="button" onclick="this.disabled = true; pywebview.api.finish(gelResult())">OK</button>
        </div>
        <script>
        const gel = document.getElementById('gel');
        function view() {{
            gel.style.width = (gel.naturalWidth * document.getElementById('zoom').value / 100) + 'px';
            gel.style.filter = `brightness(${{document.getElementById('brightness').value}}%) contrast(${{document.getElementById('contrast').value}}%)`;
        }}
        for (const id of ['zoom', 'brightness', 'contrast']) document.getElementById(id).oninput = view;
        gel.onload = view;
        function gelResult() {{
            const output = {{}};
            for (const input of document.querySelectorAll('input[data-row]')) {{
            (output[input.dataset.row] ??= {{}})[input.dataset.col] = input.value;
            }}
            output.comment = document.getElementById('comment').value;
            return output;
             }}
  </script></body></html>"""

class WebResultsUI(object):
    """
    The dialogs the results managers need, shown with pywebview. Use only from a pywebview API call.
    """

    def __init__(self, window):
        # NOTE: Main window, used as the owner of the file picker.
        self._window = window

    def choose_file(self, filetypes: str, parent=None) -> Path | None:
        filetypes = re.sub(r"\s+(?=\*)", ";", filetypes)
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

    def gel_results(self, procedure, image, resultstype: str) -> dict | None:
        api = GelApi()
        title = Path(getattr(image, "filename", "") or "Gel image").name
        page = _gel_page(title, _png_base64(image), _gel_controls(procedure, resultstype))
        if not exec_window(title, page, api, width=1300, height=950):
            return None
        return api._result

    