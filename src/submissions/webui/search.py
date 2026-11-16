"""
Search windows for the web UI. Replaces frontend.widgets.omni_search.SearchBox.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import html as html_lib
import json
import webview
from .api import db_call

SEARCH_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>__TITLE__</title>
        <style>
        body { font: 14px "Segoe UI", sans-serif; margin: 12px; }
        #fields { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
        #fields label { display: flex; flex-direction: column; font-weight: 600; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 3px 6px; text-align: left; white-space: nowrap; }
        th { background: #eee; cursor: pointer; position: sticky; top: 0; }
        tbody tr:hover { background: #cfe2f3; cursor: default; }
        #results { max-height: 75vh; overflow: auto; }
        #message { color: #666; }
        </style></head><body>
        <h2>__TITLE__</h2>
        __SUBCLASS__
        <div id="fields"></div>
        <p id="message"></p>
        <div id="results"><table><thead></thead><tbody></tbody></table></div>
        <script>
        let timer = null, result = { columns: [], data: [] }, sortCol = null, sortAsc = true;
        const subclass = () => document.getElementById('subclass')?.value || null;
        const message = (text) => { document.getElementById('message').textContent = text; };

        async function buildFields() {
            const names = await pywebview.api.fields(subclass());
            document.getElementById('fields').replaceChildren(...names.map((name) => {
            const label = document.createElement('label');
            const input = document.createElement('input');
            input.dataset.field = name;
            input.oninput = () => { clearTimeout(timer); timer = setTimeout(run, 300); };
            input.onkeydown = (e) => { if (e.key === 'Enter') run(); };
            label.append(name, input);
            return label;
            }));
            await run();
        }
        async function run() {
            const fields = {};
            for (const input of document.querySelectorAll('#fields input')) if (input.value) fields[input.dataset.field] = input.value;
            try {
                result = await pywebview.api.search(fields, subclass());
                sortCol = null;
                render();
            } catch (err) {
                message(`Search failed: ${err.message ?? err}`);
            }
            }

            function render() {
            // NOTE: Each row keeps its original index, so double-click still opens the right object after sorting.
            const rows = result.data.map((row, index) => ({ row, index }));
            if (sortCol !== null) {
                rows.sort((a, b) => String(a.row[sortCol] ?? '').localeCompare(String(b.row[sortCol] ?? ''), undefined, { numeric: true }) * (sortAsc ? 1 : -1));
            }
            const head = document.createElement('tr');
            result.columns.forEach((column, i) => {
                const th = document.createElement('th');
                th.textContent = column + (sortCol === i ? (sortAsc ? ' \\u25B2' : ' \\u25BC') : '');
                th.onclick = () => { sortAsc = sortCol === i ? !sortAsc : true; sortCol = i; render(); };
                head.append(th);
            });
            document.querySelector('thead').replaceChildren(head);
            document.querySelector('tbody').replaceChildren(...rows.map(({ row, index }) => {
                const tr = document.createElement('tr');
                for (const value of row) {
                const td = document.createElement('td');
                td.textContent = value ?? '';
                tr.append(td);
                }
                tr.ondblclick = async () => {
                const opened = await pywebview.api.open(index);
                if (!opened.ok) message(opened.message);
                };
                return tr;
            }));
            message(result.data.length ? `${result.data.length} result(s)${result.data.length >= 50 ? ' (first 50)' : ''}. Double-click a row to open it.` : 'No matches.');
            }

            document.getElementById('subclass')?.addEventListener('change', buildFields);
            if (window.pywebview?.api?.fields) buildFields();
            else window.addEventListener('pywebviewready', buildFields);
        </script></body></html>"""

class SearchApi(object):
    """
    js_api for one search window. Port of SearchBox / FieldSearch / SearchResults.
    """

    def __init__(self, ctx, object_type: type):
        self._ctx = ctx
        self._window = None
        self._object_type = object_type
        self._last_model = object_type
        # NOTE: ids of the last results, by row, so double-click doesn't need to re-query by column values.
        self._ids = []

    def _model(self, subclass: str | None):
        if not subclass or subclass == "Any":
            return self._object_type
        found = self._object_type.find_subclasses(class_name=subclass)
        return found[0] if isinstance(found, list) else (found or self._object_type)

    @db_call
    def fields(self, subclass: str | None = None) -> list:
        return self._model(subclass).get_searchables()

    @db_call
    def search(self, fields: dict, subclass: str | None = None) -> dict:
        model = self._model(subclass)
        objects = model.fuzzy_search(**{key: value for key, value in fields.items() if value})
        self._last_model = model
        self._ids = [obj.id for obj in objects]
        if not objects:
            return dict(columns=[], data=[])
        df = model.results_to_df(objects=objects)
        if df is None or df.empty:
            return dict(columns=[], data=[])
        if "id" in df.columns:
            # NOTE: Same id formatting as SearchResults.setData.
            df["id"] = df["id"].astype(str).str.zfill(3)
        return json.loads(df.to_json(orient="split", index=False, date_format="iso", default_handler=str))

    @db_call
    def open(self, row: int) -> dict:
        obj = self._ctx.database.session().get(self._last_model, self._ids[int(row)])
        # NOTE: Same rule as SearchResults.parse_row: only types with edit_from_search open anything,
        # and Sample.edit_from_search just shows details.
        if obj is None or not hasattr(obj, "edit_from_search"):
            return dict(ok=False, message=f"Nothing to open for a {self._last_model.__name__}.")
        from .details import open_details_window
        open_details_window(self._ctx, obj)
        return dict(ok=True, message="")

def open_search_window(ctx, object_type: type) -> None:
    api = SearchApi(ctx, object_type)
    title = f"Search {object_type.__name__}"
    options = ["Any"] + [cls.__name__ for cls in object_type.__subclasses__()]
    subclass = ""
    if len(options) > 1:
        subclass = ('<label>Type <select id="subclass">'
                    + "".join(f"<option>{html_lib.escape(option)}</option>" for option in options)
                    + "</select></label>")
    html = SEARCH_PAGE.replace("__TITLE__", html_lib.escape(title)).replace("__SUBCLASS__", subclass)
    api._window = webview.create_window(title, html=html, js_api=api, width=1000, height=750)

