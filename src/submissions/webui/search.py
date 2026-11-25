"""
Search windows for the web UI. Replaces frontend.widgets.omni_search.SearchBox.
The page is built with htpy (HTML as Python objects) and its browser code is written in Python and
compiled to JavaScript with PScript, so there's no template or hand-written JS for this window.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import json
import htpy as h
from markupsafe import Markup
from pscript import py2js
import webview
from .api import db_call
from . import css


def search_page_script():
    """
    Runs in the browser. PScript compiles this function to JavaScript (see BROWSER_JS), so it uses the
    browser's `window` and `document`, and JavaScript rules apply to numbers and objects.
    """
    state = {"timer": None, "columns": [], "data": [], "sort_col": None, "sort_asc": True}

    def message(text):
        document.getElementById("message").textContent = text
    
    def subclass():
        # NOTE: `is not None` rather than truthiness: PScript treats a <select> with no options as falsy.
        select = document.getElementById("subclass")
        return select.value if select is not None else None
    
    async def build_fields():
        try:
            names = await window.pywebview.api.fields(subclass())
        except Exception as err:
            message("Couldn't load search fields: " + err.message)
            return
        holder = document.getElementById("fields")
        holder.replaceChildren()
        for name in names:
            holder.append(field_input(name))
        await run()
    
    def field_input(name):
        label = document.createElement("label")
        box = document.createElement("input")
        box.dataset.field = name
        box.oninput = schedule
        box.onkeydown = lambda event: run() if event.key == "Enter" else None
        label.append(name, box)
        return label
    
    def schedule():
        window.clearTimeout(state["timer"])
        state["timer"] = window.setTimeout(run, 300)
    
    async def run():
        fields = {}
        for box in window.Array.prototype.slice.call(document.querySelectorAll("#fields input")):
            if box.value:
                fields[box.dataset.field] = box.value
        try:
            result = await window.pywebview.api.search(fields, subclass())
        except Exception as err:
            message("Search failed: " + err.message)
            return
        state["columns"] = result.columns
        state["data"] = result.data
        state["sort_col"] = None
        render()
    
    def sort_by(index):
        state["sort_asc"] = (not state["sort_asc"]) if state["sort_col"] == index else True
        state["sort_col"] = index
        render()
    
    def header_cell(column, index):
        th = document.createElement("th")
        arrow = ""
        if state["sort_col"] == index:
            arrow = " ▲" if state["sort_asc"] else " ▼"
        th.textContent = column + arrow
        th.onclick = lambda: sort_by(index)
        return th
    
    async def open_row(index):
        opened = await window.pywebview.api.open(index)
        if not opened.ok:
            message(opened.message)
    
    def result_row(row, index):
        # NOTE: A function per row, so each row's double-click keeps its own index (JS loop variables don't).
        tr = document.createElement("tr")
        for value in row:
            td = document.createElement("td")
            td.textContent = "" if value is None else str(value)
            tr.append(td)
        tr.ondblclick = lambda: open_row(index)
        return tr
    
    def render():
        # NOTE: Each row keeps its original index, so double-click still opens the right object after sorting.
        rows = [{"row": row, "index": index} for index, row in enumerate(state["data"])]
        column = state["sort_col"]
        if column is not None:
            direction = 1 if state["sort_asc"] else -1
            def compare(a, b):
                left = "" if a["row"][column] is None else str(a["row"][column])
                right = "" if b["row"][column] is None else str(b["row"][column])
                return left.localeCompare(right, undefined, {"numeric": True}) * direction
            # NOTE: The browser's own sort with a comparator, to keep number-aware ordering (RSL-9 before RSL-10).
            window.Array.prototype.sort.call(rows, compare)
        head = document.createElement("tr")
        for index, name in enumerate(state["columns"]):
            head.append(header_cell(name, index))
        document.querySelector("thead").replaceChildren(head)
        body = document.querySelector("tbody")
        body.replaceChildren()
        for item in rows:
            body.append(result_row(item["row"], item["index"]))
        count = len(state["data"])
        if count:
            limit = " (first 50)" if count >= 50 else ""
            message(f"{count} result(s){limit}. Double-click a row to open it.")
        else:
            message("No matches.")
    
    select = document.getElementById("subclass")
    if select is not None:
        select.addEventListener("change", build_fields)
    if window.pywebview and window.pywebview.api and window.pywebview.api.fields:
        build_fields()
    else:
        window.addEventListener("pywebviewready", build_fields)

# NOTE: Compiled once, when this module is imported.
BROWSER_JS = py2js(search_page_script) + "\nsearch_page_script();\n"

def search_page(title: str, subclasses: list[str]) -> str:
    """
    The whole search page as an HTML string, CSS and JS included.
    """
    subclass_select = None
    if subclasses:
        subclass_select = h.label["Type ", h.select(id="subclass")[(h.option[name] for name in ["Any"] + subclasses)]]
    page = h.html[
        # h.head[h.meta(charset="utf-8"), h.title[title], h.style[Markup(_css(STYLE))]],
        h.head[h.meta(charset="utf-8"), h.title[title], h.style[Markup(css)]],
        h.body[
            h.h2[title],
            subclass_select,
            h.div(id="fields"),
            h.p(id="message"),
            h.div(id="results")[h.table[h.thead, h.tbody]],
            h.script[Markup(BROWSER_JS)],
        ],
    ]
    # NOTE: htpy renders to markupsafe.Markup, a str subclass. pythonnet (used by pywebview's WebView2 backend)
    # won't pass a str subclass to .NET, so NavigateToString rejects it; hand over a plain str.
    return str.__str__(str(page))


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
    subclasses = [cls.__name__ for cls in object_type.__subclasses__()]
    api._window = webview.create_window(title, html=search_page(title, subclasses), js_api=api, width=1000, height=750)
