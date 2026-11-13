"""
Details windows for the web UI. Replaces frontend.widgets.submission_details.SubmissionDetails.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from datetime import datetime
from getpass import getuser
import webview
from .api import db_call

# NOTE: Back/Export PDF bar injected into every details page; hidden when printing.
TOOLBAR = """
<div id="details-toolbar" style="padding: 6px 0 10px; display: flex; gap: 8px;">
<button type="button" onclick="backend.back()"{disabled}>Back</button>
<button type="button" onclick="window.print()">Export PDF</button>
</div>
<style>@media print {{ #details-toolbar {{ display: none; }} }}</style>
"""


class DetailsApi(object):
    """
    js_api for one details window. Method names match the Qt slots the templates call through `backend`.
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self._window = None
        # NOTE: (model class, id) pairs; ORM objects can't be kept because every call runs on a new thread.
        self._current = None
        self._history = []

    def _page(self, obj) -> tuple[str, str]:
        """
        Renders an object's details page.

        :return: Window title and html.
        """
        pyd = obj.to_pydantic()
        html = pyd.to_html(creation=False)
        html = html.replace("<body>", "<body>" + TOOLBAR.format(disabled="" if self._history else " disabled"), 1)
        return f"{pyd.__class__.__name__} Details - {pyd.name}", html

    def _show(self, obj, push: bool = True) -> None:
        if push and self._current is not None:
            self._history.append(self._current)
        self._current = (type(obj), obj.id)
        title, html = self._page(obj)
        self._window.set_title(title)
        self._window.load_html(html)

    def _reload(self, push: bool = False) -> None:
        model, id = self._current
        self._show(self._ctx.database.session().get(model, id), push=push)

    @db_call
    def show_sub_details(self, sub_name: str, sub_type: str) -> None:
        """
        Shows another object's details in this window (a.data-link clicks).
        """
        from backend.db import models
        clss = models.BaseClass.find_subclasses(class_name=sub_type)
        if isinstance(clss, list):
            clss = clss[0] if clss else None
        if not clss:
            logger.error(f"No class found for {sub_type}.")
            return
        obj = clss.query(name=sub_name, limit=1)
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        if obj is None:
            logger.error(f"{sub_type} with name {sub_name} not found.")
            return
        self._show(obj)

    @db_call
    def sign_off(self, run_name: str) -> None:
        """
        Marks a run as complete. The template only shows the button to users with permission.
        """
        from backend.db import models
        logger.info(f"Signing off on {run_name} - ({getuser()})")
        run = models.Run.query(name=run_name)
        run.signed_by = getuser()
        run.completed_date = datetime.now()
        run.save()
        self._reload()

    @db_call
    def back(self) -> None:
        if not self._history:
            return
        self._current = self._history.pop()
        self._reload()

def open_details_window(ctx, obj) -> None:
    """
    Opens a new details window for a database object.
    """
    api = DetailsApi(ctx)
    api._current = (type(obj), obj.id)
    title, html = api._page(obj)
    api._window = webview.create_window(title, html=html, js_api=api, width=1000, height=750)