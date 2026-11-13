"""
Submission import/edit window for the web UI. Replaces SubmissionFormContainer and
ClientSubmissionFormWidget in frontend.widgets.submission_widget.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import html as html_lib
from datetime import date
from pathlib import Path
from typing import Callable
import webview
from tools import render_details_template
from .charts import _names
from .modal import ModalApi, add_buttons, exec_window
from .sample_checker import format_sample_list
from .window_thread import WindowThread, on_window_thread

FORM_SCRIPT = """
<script>
function markUpdated(input) {
    const label = document.querySelector(`label[for="${input.id}"]`);
    if (label) label.textContent = 'UPDATED ' + label.dataset.title;
}
async function saveForm(button) {
    button.disabled = true;
    const values = {};
    for (const input of document.querySelectorAll('#submission-form [data-key]')) {
    if (!input.disabled && !input.readOnly) values[input.dataset.key] = input.value;
    }
    const result = await pywebview.api.save(values);
    if (result && !result.ok) { alert(result.message); button.disabled = false; }
}
</script>
"""


def _display_value(value):
    """
    The plain value of a form field, as InfoItem.set_widget unwraps it.
    """
    from backend.db.models import BaseClass
    from backend.validators import SourcedField
    if isinstance(value, dict):
        value = value.get('value', value)
    elif isinstance(value, SourcedField):
        value = value.value
    if issubclass(value.__class__, BaseClass):
        value = value.name
    return value

def _status(value) -> str:
      # NOTE: Same wording as ParsedQLabel.
      check = value.get('missing', True) if isinstance(value, dict) else True
      return "Parsed" if check else "MISSING"


def _lookup_first(class_, value) -> list[str]:
    """
    All names of a model, with the one matching value first, as the Qt combo boxes order them.
    """
    names = _names(class_.query())
    try:
        found = class_.query(name=value, limit=1)
    except AttributeError:
        found = None
    if found:
        names = [str(found.name)] + [name for name in names if name != str(found.name)]
    return names

def form_fields(pyd, disable: list) -> list[dict]:
    """
    One entry per form field, following SubmissionFormWidget.InfoItem.set_widget.
    """
    from backend.db.models import ClientSubmission, ClientLab, SubmissionType
    excluded = list(pyd.class_config.excluded) + ["sample_count"]
    submission_type = SubmissionType.query(name=pyd.submissiontype.get('value'))
    fields = []
    for key in pyd.__class__.model_fields.keys():
        if key in excluded:
            continue
        try:
            raw = getattr(pyd, key)
        except AttributeError:
            raw = (pyd.model_extra or {}).get(key, dict(value=None, missing=True))
        value = _display_value(raw)
        field = dict(key=key, title=key.replace('_', ' ').title().replace("Rsl", "RSL").replace("Pcr", "PCR"),
                    status=_status(raw), disabled=key in disable)
        match key:
            case 'clientlab':
                field.update(kind="select", options=_lookup_first(ClientLab, value))
            case 'submission_category':
                categories = ['Diagnostic', "Surveillance", "Research"] + _names(SubmissionType.query())
                first = value if value in categories else getattr(submission_type, "name", None)
                if first in categories:
                    categories.insert(0, categories.pop(categories.index(first)))
                field.update(kind="select", options=categories)
            case _:
                try:
                    field_type = ClientSubmission.determine_field_type(key)
                except AttributeError:
                    logger.error(f"Could not get fieldtype for {key}")
                    continue
                match field_type:
                    case "TIMESTAMP":
                        field.update(kind="date", value=(value if isinstance(value, date) else date.today()).isoformat()[:10])
                    case "INTEGER":
                        field.update(kind="int", value=value if isinstance(value, int) else 0)
                    case "RELATIONSHIPSCALAR":
                        field.update(kind="select", options=_lookup_first(ClientSubmission.get_relationship_sqlclass(key), value))
                    case "Invalid":
                        continue
                    case _:
                        field.update(kind="text", value=value if isinstance(value, str) else "NA")
        fields.append(field)
    return fields

def _field_html(field: dict) -> str:
    key = html_lib.escape(field["key"])
    attrs = f'id="f-{key}" data-key="{key}" onchange="markUpdated(this)"'
    if field["disabled"]:
        attrs += ' disabled title="Widget disabled to protect database integrity."'
    match field["kind"]:
        case "select":
            options = "".join(f"<option>{html_lib.escape(str(option))}</option>" for option in field["options"])
            control = f"<select {attrs}>{options}</select>"
        case "date":
            control = f'<input type="date" {attrs} value="{field["value"]}">'
        case "int":
            # NOTE: Read-only because the Qt form never saved number fields either (InfoItem.parse_form skips QSpinBox).
            control = f'<input type="number" {attrs} value="{field["value"]}" readonly>'
        case _:
            control = f'<input type="text" {attrs} value="{html_lib.escape(field["value"])}">'
    title = html_lib.escape(field["title"])
    return (f'<div class="field"><label for="f-{key}" data-title="{title}">{html_lib.escape(field["status"])} {title}</label>'
            f'{control}</div>')


def _form_page(title: str, fields: list[dict]) -> str:
    rows = "".join(_field_html(field) for field in fields)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html_lib.escape(title)}</title>
        <style>
        body {{ font: 14px "Segoe UI", sans-serif; margin: 16px; }}
        .field {{ margin-bottom: 10px; }}
        .field label {{ display: block; font-weight: 600; margin-bottom: 2px; }}
        .field input, .field select {{ width: 100%; max-width: 420px; padding: 3px; box-sizing: border-box; }}
        </style></head><body>
        <h2>{html_lib.escape(title)}</h2>
        <form id="submission-form" onsubmit="return false">{rows}</form>
        <div style="display: flex; gap: 8px;">
        <button type="button" onclick="pywebview.api.cancel()">Cancel</button>
        <button type="button" onclick="saveForm(this)">Save</button>
        </div>
        {FORM_SCRIPT}</body></html>"""


class ChoiceApi(ModalApi):

    def __init__(self, first: str | None):
        super().__init__()
        self._choice = first

    def choose(self, value: str) -> None:
        self._choice = value

def choose_submissiontype(message: str):
    """
    Web stand-in for the Qt ObjectSelector (see backend.validators.set_submissiontype_chooser).
    """
    from backend.db.models import SubmissionType
    names = _names(SubmissionType.query())
    options = "".join(f"<option>{html_lib.escape(name)}</option>" for name in names)
    page = (f'<html><body style="font: 14px \'Segoe UI\', sans-serif;"><p>{html_lib.escape(message)}</p>'
            f'<select onchange="pywebview.api.choose(this.value)">{options}</select></body></html>')
    api = ChoiceApi(names[0] if names else None)
    if not exec_window("Couldn't parse submission type.", add_buttons(page), api, width=420, height=260):
        return None
    return SubmissionType.query(name=api._choice) if api._choice else None


class SubmissionFormApi(object):
    """
    js_api for one import/edit window: a Sample Checker page (import only), then the submission form.
    Every @on_window_thread method runs on this window's thread; they must not call each other.
    """

    def __init__(self, ctx, edit: bool, on_done: Callable[[], None] | None = None):
        self._ctx = ctx
        self._window = None
        self._thread = WindowThread(ctx)
        self._edit = edit
        self._on_done = on_done
        self._pyd = None
        self._disable = []
        self._fields = []

    def _load_import(self, path: Path) -> tuple[str, str]:
        from backend.managers import DefaultClientSubmissionManager
        from backend.validators import set_submissiontype_chooser
        from backend.validators.pydant import PydClientSubmission
        set_submissiontype_chooser(choose_submissiontype)
        self._pyd = DefaultClientSubmissionManager(parent=None, input_object=path).to_pydantic()
        if not isinstance(self._pyd, PydClientSubmission):
            raise TypeError(f"Got wrong type for {self._pyd}: {type(self._pyd)}")
        html = render_details_template(template="sample_checker", samples=format_sample_list(self._pyd.sample),
                                        rsl_plate_number=None)
        return "Sample Checker", add_buttons(html)

    def _load_edit(self, submission_id: int) -> tuple[str, str]:
        from backend.db.models import ClientSubmission
        from backend.managers import DefaultClientSubmissionManager
        submission = self._ctx.database.session().get(ClientSubmission, submission_id)
        self._pyd = DefaultClientSubmissionManager(parent=None, input_object=submission).to_pydantic()
        self._disable = ['submitter_plate_id']
        return self._form()

    def _form(self) -> tuple[str, str]:
        self._fields = form_fields(self._pyd, self._disable)
        title = "Edit Submission" if self._edit else "New Submission"
        return title, _form_page(title, self._fields)

    # NOTE: Sample Checker page (template calls these through bridge.js).
    @on_window_thread
    def text_changed(self, submission_rank: str, key: str, new_value: str) -> None:
        sample = next((s for s in self._pyd.sample if int(submission_rank) == s.submission_rank), None)
        if sample is None:
            logger.error(f"Unable to find sample {submission_rank}")
            return
        setattr(sample, key, new_value)

    def enable_sample(self, submission_rank: int, enabled: bool) -> None:
        # NOTE: The checkboxes only appear when a run exists, never during an import.
        pass

    def set_rsl_plate_number(self, rsl_plate_number: str) -> None:
        pass

    @on_window_thread
    def accept(self) -> None:
        """
        Sample Checker OK: go on to the form.
        """
        title, html = self._form()
        self._window.set_title(title)
        self._window.load_html(html)

    def cancel(self) -> None:
        logger.warning("Submission cancelled.")
        self._window.destroy()

    @on_window_thread
    def save(self, values: dict) -> dict:
        """
        Port of ClientSubmissionFormWidget.create_new_submission.
        """
        from backend.validators.pydant import PydSample
        try:
            kinds = {field["key"]: field["kind"] for field in self._fields}
            for key, value in values.items():
                if key == "sample" or key not in kinds:
                    continue
                if kinds[key] == "date":
                    value = date.fromisoformat(value)
                setattr(self._pyd, key, value)
            self._pyd.sample = [item for item in self._pyd.sample if PydSample.is_sample_id_valid(item)]
            sql = self._pyd.to_sql()
            if isinstance(sql, tuple):
                sql = sql[0]
            # NOTE: Remove any sample info accidentally left in misc_info by pyd.to_sql
            try:
                del sql._misc_info['sample']
            except (KeyError, TypeError):
                pass
            sql.save()
        except Exception as e:
            logger.exception(f"Couldn't save submission: {e}")
            return dict(ok=False, message=f"Couldn't save submission: {e}")
        self._window.destroy()
        if self._on_done:
            self._on_done()
        return dict(ok=True)


def _open(api: SubmissionFormApi, loader, *args) -> None:
    try:
        title, html = api._thread.run(loader, *args)
    except Exception:
        api._thread.close()
        raise
    api._window = webview.create_window(title, html=html, js_api=api, width=950, height=800)
    api._window.events.closed += api._thread.close


def open_import_window(ctx, path: Path, on_done: Callable[[], None] | None = None) -> None:
    api = SubmissionFormApi(ctx, edit=False, on_done=on_done)
    _open(api, api._load_import, path)

def open_import_window(ctx, path: Path, on_done: Callable[[], None] | None = None) -> None:
    api = SubmissionFormApi(ctx, edit=False, on_done=on_done)
    _open(api, api._load_import, path)


def open_edit_window(ctx, submission_id: int, on_done: Callable[[], None] | None = None) -> None:
    api = SubmissionFormApi(ctx, edit=True, on_done=on_done)
    _open(api, api._load_edit, submission_id)