"""
Manager windows for the web UI. Replaces frontend.widgets.omni_manager_pydant.OmniManager.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import json
from operator import itemgetter
import webview
from tools import render_details_template
from .window_thread import WindowThread, on_window_thread


class ManagerApi(object):
    """
    js_api for one manager window. Method names match OmniManager's Qt slots.
    """

    def __init__(self, ctx, object_type: type):
        from backend.db.models import BaseClass
        self._ctx = ctx
        self._window = None
        self._thread = WindowThread(ctx)
        self._object_type = object_type
        self._sql_type = BaseClass.find_subclasses(class_name=object_type.__name__.replace('Pyd', ''))
        self._pydant = None

    def _page(self) -> str:
        """
        Renders the object picker, as OmniManager.reset_form does.
        """
        q = self._sql_type.query()
        if q is not None:
            objects = sorted(
                [dict(name=item.name, active=item.is_active) for item in q if item.name != "Default SubmissionType"],
                key=itemgetter("active"), reverse=True)
        else:
            objects = []
        object_list = [dict(name="", active=True), dict(name="--New--", active=True)] + objects
        return render_details_template("managers/default_manager", js_in=['manager'],
                                        object_name=self._sql_type.__name__, object_list=object_list)

    @on_window_thread
    def update_selection(self, selection: str) -> str:
        if selection == "--New--":
            self._pydant = self._object_type()
            self._pydant.new = True
        else:
            sql_instance = self._object_type._sql_class.query(name=selection, limit=1)
            if not sql_instance:
                logger.error(f"Could not find instance with name: {selection}")
                self._pydant = None
                return ""
            self._pydant = sql_instance.to_pydantic()
            self._pydant.new = False
        return self._pydant.html_form

    @on_window_thread
    def update_instrumentedattribute(self, field: str, value: str) -> None:
        self._pydant.update_instrumentedattribute(field, value)

    @on_window_thread
    def get_association_form(self, field: str, value: str | None = None) -> str:
        # NOTE: manager.js passes the selected value too; the Qt slot ignored it.
        if self._pydant is None:
            raise AttributeError("No object selected. Unable to get association form.")
        return self._pydant.get_association_class(field)().html_form

    @on_window_thread
    def add_relationship(self, field: str, value: str, data: dict | None = None) -> None:
        self._pydant.add_relationship(field, value, data)

    @on_window_thread
    def remove_relationship(self, field: str, value: str) -> None:
        self._pydant.remove_relationship(field, value)

    @on_window_thread
    def submit(self) -> None:
        try:
            sql_instance = self._pydant.to_sql()
            if isinstance(sql_instance, tuple):
                sql_instance = sql_instance[0]
            sql_instance.save()
        except Exception as e:
            logger.exception(f"Couldn't save {self._sql_type.__name__}: {e}")
            message = json.dumps(f"Couldn't save: {e}")
            self._window.evaluate_js(f"alert({message})")
            return
        self._pydant = None
        self._window.load_html(self._page())

    def save_html(self) -> None:
        # NOTE: OmniManager.write_html is an empty stub, so this does nothing in the Qt app either.
        pass


def open_manager(ctx, object_type: type) -> None:
    """
    Opens a manager window for a Pydantic class, as PydBaseClass.manage does.
    """
    api = ManagerApi(ctx, object_type)
    html = api._thread.run(api._page)
    api._window = webview.create_window(f"Manage {api._sql_type.__name__}", html=html, js_api=api, width=1100, height=800)
    api._window.events.closed += api._thread.close