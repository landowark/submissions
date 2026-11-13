"""
Sample checker window for the web UI. Replaces frontend.widgets.sample_checker.SampleChecker.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import json
from typing import Callable
import webview
from tools import render_details_template
from .api import db_call

BUTTONS = """
    <div id="checker-buttons" style="padding: 10px 0; display: flex; gap: 8px; justify-content: flex-end;">
    <button type="button" onclick="backend.cancel()">Cancel</button>
    <button type="button" id="checker-ok" onclick="this.disabled = true; backend.accept()">OK</button>
    </div>
"""


def format_sample_list(samples: list) -> list[dict]:
    """
    Marks repeated sample ids red, as SampleChecker.format_sample_list does.
    """
    seen = set()
    output = []
    for sample in samples:
        s = sample.improved_dict
        s['color'] = "red" if s['sample_id'] in seen else "black"
        seen.add(s['sample_id'])
        output.append(s)
    return output


class SampleCheckerApi(object):
    """
    js_api for one sample checker window. Method names match SampleChecker's Qt slots.

    Edits are only recorded here; accept() reloads the submission on its own thread and applies them,
    because ORM objects loaded during earlier calls are detached by then.
    """

    def __init__(self, ctx, submission_id: int | None, rsl_plate_number: str | None,
                on_done: Callable[[], None] | None = None):
        self._ctx = ctx
        self._window = None
        # NOTE: None for Edit (run), which saves nothing on OK, same as Run.edit in the Qt app.
        self._submission_id = submission_id
        self._rsl_plate_number = rsl_plate_number
        self._on_done = on_done
        self._edits = {}

    def text_changed(self, submission_rank: str, key: str, new_value: str) -> None:
          self._edits.setdefault(int(submission_rank), {})[key] = new_value

    def enable_sample(self, submission_rank: int, enabled: bool) -> None:
        self._edits.setdefault(int(submission_rank), {})["enabled"] = enabled

    def set_rsl_plate_number(self, rsl_plate_number: str) -> None:
        self._rsl_plate_number = rsl_plate_number

    def cancel(self) -> None:
        logger.warning("Run cancelled.")
        self._window.destroy()

    @db_call
    def accept(self) -> None:
        if self._submission_id is not None:
            try:
                self._create_run()
            except Exception as e:
                logger.exception(f"Couldn't create run: {e}")
                message = json.dumps(f"Couldn't create run: {e}")
                self._window.evaluate_js(f"alert({message}); document.getElementById('checker-ok').disabled = false;")
                return
        self._window.destroy()
        if self._on_done:
              self._on_done()

    def _create_run(self) -> None:
        from backend.db.models import ClientSubmission
        submission = self._ctx.database.session().get(ClientSubmission, self._submission_id)
        samples = [assoc.to_pydantic() for assoc in submission.clientsubmissionsampleassociation]
        for sample in samples:
            for key, value in self._edits.get(int(sample.submission_rank), {}).items():
                setattr(sample, key, value)
        submission.create_run(samples=samples, rsl_plate_number=self._rsl_plate_number)


def open_sample_checker(ctx, title: str, samples: list, rsl_plate_number: str | None,
                          submission_id: int | None = None, on_done: Callable[[], None] | None = None) -> None:
    """
    Opens a sample checker window.

    :param submission_id: Submission to create a run from on OK. None just closes on OK (Edit run).
    :param on_done: Called after OK succeeds, e.g. to refresh the submissions list.
    """
    api = SampleCheckerApi(ctx, submission_id=submission_id, rsl_plate_number=rsl_plate_number, on_done=on_done)
    html = render_details_template(template="sample_checker", samples=format_sample_list(samples),
                                    rsl_plate_number=rsl_plate_number)
    html = html.replace("</form>", "</form>" + BUTTONS, 1)
    api._window = webview.create_window(title, html=html, js_api=api, width=950, height=650)