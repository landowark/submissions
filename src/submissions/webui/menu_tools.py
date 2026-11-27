"""
Menu tools for the web UI: Submissions to Excel, About, Docs and GitHub (from frontend.widgets.app.App).
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import html as html_lib, sys, webbrowser, webview, htpy as h
from datetime import date, timedelta
from pathlib import Path
from .charts import _names
from .modal import ModalApi, exec_window
from markupsafe import Markup
from .components import *
from . import css


# DATE_TYPE_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Submissions to Excel</title>
#         <style>
#         body { font: 14px "Segoe UI", sans-serif; margin: 16px; }
#         fieldset { border: 1px solid #ccc; margin-bottom: 12px; }
#         fieldset label { display: block; }
#         #types { max-height: 220px; overflow: auto; }
#         </style></head><body>
#         <fieldset><legend>Dates</legend>
#         <label>From <input type="date" id="start" value="__START__"></label>
#         <label>To <input type="date" id="end" value="__END__"></label>
#         </fieldset>
#         <fieldset id="types"><legend>Submission Type</legend>__TYPES__</fieldset>
#         <div style="display: flex; gap: 8px; justify-content: flex-end;">
#         <button type="button" onclick="pywebview.api.cancel()">Cancel</button>
#         <button type="button" onclick="this.disabled = true; pywebview.api.finish(values())">OK</button>
#         </div>
#         <script>
#         function values() {
#             return {
#             start_date: document.getElementById('start').value,
#             end_date: document.getElementById('end').value,
#             submissiontype: [...document.querySelectorAll('#types input:checked')].map((box) => box.value),
#             };
#         }
#         </script></body></html>"""

DATE_TYPE_PAGE = h.html[
    h.head[h.meta(charset="utf-8"), h.style[Markup(css)], h.title["Submissions to Excel"]],
    h.body[
        _date_range_picker(),
        h.fieldset(id="types")[
            h.legend["Submission Type"], 
            "__TYPES__"
        ],
        h.div(style="display: flex; gap: 8px; justify-content: flex-end;")[
            h.button(type="button", onclick="pywebview.api.cancel()")["Cancel"],
            h.button(type="button", onclick="this.disabled = true; pywebview.api.finish(values()")["OK"]
        ],
        h.script["""
            function values() {
                return {
                    start_date: document.getElementById('start').value,
                    end_date: document.getElementById('end').value,
                    submissiontype: [...document.querySelectorAll('#types input:checked')].map((box) => box.value),
                };
            }
        """]
    ]
]


class DateTypeApi(ModalApi):
    """
    js_api for the date/type picker (port of DateTypePicker).
    """

    def __init__(self):
        super().__init__()
        self._values = None

    def finish(self, values: dict) -> None:
        # NOTE: Stores the choices and closes in one call, so nothing can arrive after OK.
        self._values = values
        self.accept()


def export_submissions(window) -> dict:
    """
    Port of App.submissions_to_excel. Call from a pywebview API call (it blocks on the picker).
    """
    from pandas import ExcelWriter
    from backend.db.models import Run, SubmissionType
    types = "".join(f'<label><input type="checkbox" value="{html_lib.escape(name)}" checked> {html_lib.escape(name)}</label>'
                    for name in _names(SubmissionType.query()))
    page = (_plain(DATE_TYPE_PAGE).replace("__TYPES__", types))
    api = DateTypeApi()
    if not exec_window("Submissions to Excel", page, api, width=520, height=520):
        return dict(ok=False, message="Export cancelled.")
    start = date.fromisoformat(api._values["start_date"])
    end = date.fromisoformat(api._values["end_date"])
    df = Run.archive_submissions(start_date=start, end_date=end, submissiontype=api._values["submissiontype"])
    if df.empty:
        return dict(ok=False, message="No runs found for those dates and submission types.")
    result = window.create_file_dialog(webview.FileDialog.SAVE, save_filename=f"Submissions {start}-{end}.xlsx",
                                        file_types=("Excel files (*.xlsx)",))
    if not result:
        return dict(ok=False, message="Export cancelled.")
    path = result if isinstance(result, str) else result[0]
    with ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer)
    return dict(ok=True, message=f"Saved {path}")

def open_about(ctx) -> None:
    """
    Port of App.showAbout.
    """
    from tools import jinja_env
    html = jinja_env.get_template("project.html").render(info=ctx.package.__dict__)
    # NOTE: target=_blank links go to the system browser / mail client instead of navigating this window.
    html = html.replace("<head>", '<head><base target="_blank">', 1)
    webview.create_window("About", html=html, width=560, height=260)


def docs_path() -> Path:
    from tools import check_if_app, project_path
    if check_if_app():
        return Path(sys._MEIPASS).joinpath("files", "docs", "index.html")
    return project_path.joinpath("docs", "build", "index.html")


def open_docs() -> dict:
    """
    Port of App.openDocs: opens the built Sphinx docs in the default browser.
    """
    path = docs_path()
    if not path.exists():
        return dict(ok=False, message=f"Docs not found at {path}. Build them with Sphinx first.")
    webbrowser.open(path.as_uri())
    return dict(ok=True, message="")


def open_github(ctx) -> None:
    webbrowser.open(ctx.package.__github__)