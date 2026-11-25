"""
htpy versions of the manager pages: templates/managers/default_manager.html (the object picker) and
templates/managers/manager_form.html (an object's form, PydBaseClass.html_form).

Element ids and classes match the templates exactly, so templates/js/manager.js works unchanged.
The templates stay as they are for the Qt OmniManager.
"""
from __future__ import annotations
from datetime import date, datetime
from operator import itemgetter
import htpy as h
from markupsafe import Markup
from .window_thread import WindowThread, on_window_thread
from .components import *
from . import css


class ManagerForm(object):

    def __init__(self, ctx, object_type: type):
        from backend.db.models import BaseClass
        self._ctx = ctx
        self._window = None
        self._thread = WindowThread(ctx)
        self._object_type = object_type
        self._sql_type = BaseClass.find_subclasses(class_name=object_type.__name__.replace('Pyd', ''))
        self._pydant = None
        q = self._sql_type.query()
        if q is not None:
            objects = sorted(
                [dict(name=item.name, active=item.is_active) for item in q if item.name != "Default SubmissionType"],
                key=itemgetter("active"), reverse=True)
        else:
            objects = []
        self.object_list = [dict(name="", active=True), dict(name="--New--", active=True)] + objects

    def _page(self):
        """
        The object picker page (default_manager.html). The chosen object's form is loaded into #object_form.
        """
        object_name = self._sql_type.__name__
        page = h.html[
            h.head[h.meta(charset="utf-8"), h.style[Markup(css)]],
            h.body[
                h.h2(id="ObjectName")[f"Manage {object_name}"],
                h.select(id="initial_object", onchange="update_selection(this.value)")[
                    (h.option(value=item["name"],
                                style=None if item["active"] else "color:gray",
                                title=None if item["active"] else "Inactive")[item["name"]]
                        for item in self.object_list)
                ],
                h.div(id="object_form"),
                (h.script[_asset("js", name)] for name in ("bridge", "details", "manager")),
            ],
        ]
        return _plain(page)

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
        # return self._pydant.html_form
        return self._pydant.create_manager_form()

    @on_window_thread
    def update_instrumentedattribute(self, field: str, value: str) -> None:
        self._pydant.update_instrumentedattribute(field, value)

    @on_window_thread
    def get_association_form(self, field: str, value: str | None = None) -> str:
        # NOTE: manager.js passes the selected value too; the Qt slot ignored it.
        if self._pydant is None:
            raise AttributeError("No object selected. Unable to get association form.")
        # return self._pydant.get_association_class(field)().html_form
        return manager_form(self._pydant.get_association_class(field)())

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

