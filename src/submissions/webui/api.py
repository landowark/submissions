"""
Python functions exposed to the web UI as window.pywebview.api.<name>.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from functools import wraps
import webview, json
from math import ceil
from datetime import date, datetime
from getpass import getuser
from tools import is_power_user
from typing import TYPE_CHECKING, List
if TYPE_CHECKING:
    from tools import Settings
    from backend.validators.pydant import PydBaseClass


def db_call(func):
    """
    Releases the thread's database session after an API call.

    pywebview runs every API call on a new thread, and ctx.database.session is thread-local,
    so each call gets its own session. Return only plain data (dicts/str), never ORM objects.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        finally:
            self._ctx.database.session.remove()
    return wrapper


class Api(object):

    # NOTE: Right-click actions the web UI can run so far. The rest still need their Qt dialogs ported.
    WEB_ACTIONS = {
        "submission": {"Delete", "Add Comment", "Show Details", "Add Run"},
        "run": {"Delete", "Add Comment", "Show Details", "Export", "Edit", "Add Procedure"},
        "procedure": {"Preprocessing", "Delete", "Add Comment", "Show Details", "Add Results", "Edit"},
    }

    def __init__(self, ctx: Settings):
        # NOTE: Underscore names are not exposed to JS by pywebview.
        self._ctx = ctx
        # self._window = None
        self._window = webview.create_window(
            f"Submissions App TNG (v{ctx.package.__version__})",
            url=str(ctx.static.joinpath("index.html")), js_api=self, width=1300, height=1000)
        self._window.events.loaded += self._bind_drop
        self._window.events.closed += lambda: self.close_other_windows()
        self._install_alerts()

    def close_other_windows(self) -> None:
        """
        Closing the main window quits the app, as in the Qt app. pywebview otherwise keeps running
        until the last window is closed.
        """
        for window in list(webview.windows):
            if window is not self:
                try:
                    window.destroy()
                except Exception:
                    pass

    def app_info(self) -> dict:
        """
        Dictionary of application info
        NOTE: Cannot be a property due to being called in JS.

        :returns: dict(version=self._ctx.package.__version__, database=f"{self._ctx.database.path}/{self._ctx.database.name}")
        :rtype: dict
        """
        return dict(
            version=self._ctx.package.__version__,
            database=f"{self._ctx.database.path}/{self._ctx.database.name}",
        )

    def _install_alerts(self):
        
        """
        Routes tools.report_result alerts to a JS alert in the focused window. Call before webview.start().
        """
        from tools import set_alert_handler
        def show(alert) -> None:
            window = webview.active_window() or self
            message = json.dumps(f"{alert.status}: {alert.msg}")
            window.evaluate_js(f"alert({message})")
        set_alert_handler(show)

    @staticmethod
    def _iso(value) -> str:
        """
        Returns time in iso format string.

        :returns: iso formatted string or ""
        :rtype: str
        """
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return "" if value is None else str(value)

    @db_call
    def submission_count(self) -> int:
        """
        Gets count of ClientSubmission objects.

        :returns: self._ctx.database.session().query(func.count(ClientSubmission.id)).scalar()
        :rtype: int
        """
        from sqlalchemy import func
        from backend.db.models import ClientSubmission
        return self._ctx.database.session().query(func.count(ClientSubmission.id)).scalar()

    def choose_save_file(self, default_name: str, extension: str) -> str | None:
        """
        Select file save location from a dialog.

        :param default_name: Default name constructed by program.
        :type default_name: str
        :param extension: File type suffix (e.g. 'xlsx', 'csv')
        :type extension: str
        :returns: Choosen filename
        :rtype: str
        """
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=f"{default_name}.{extension}",
            file_types=(f"{extension.upper()} files (*.{extension})",))
        return result if isinstance(result, str) else (result[0] if result else None)

    @staticmethod
    def _model(alias: str):
        """
        Gets a SqlAlchemy model by its alias.

        :param alias: Alias of the model of interest.
        :type alias: str
        :returns: BaseClass subclass with the alias.
        :rtype: BaseClass 
        """
        from backend.db.models import BaseClass
        return BaseClass.find_subclasses(class_alias=alias)
        
    def _get(self, alias: str, id: int):
        """
        Gets an instance of a BaseClass subclass by id.

        :param alias: Alias of the model in question.
        :type alias: str
        :param id: Unique id of the instance of interest.
        :type id: int
        :returns: BaseClass instance with id.
        :rtype: BaseClass
        """
        obj = self._ctx.database.session().get(self._model(alias), int(id))
        if obj is None:
            raise LookupError(f"No {alias} with id {id}.")
        return obj

    @db_call
    def list_submissions(self, page: int = 1, page_size: int = 250) -> dict:
        """
        One page of the submissions tree, newest first.

        :param page: Page number.
        :type page: int
        :param page_size: Number of objects to fit on a page.
        :type page_size: int
        :return: {total, page, pages, rows}
        :rtype: dict
        """
        from sqlalchemy import func
        from sqlalchemy.orm import selectinload
        from backend.db.models import ClientSubmission, Run
        total = self._ctx.database.session().query(func.count(ClientSubmission.id)).scalar()
        options = [selectinload(ClientSubmission._clientlab),
                    selectinload(ClientSubmission._run).selectinload(Run._procedure)]
        rows = []
        for submission in ClientSubmission.query(chronologic=True, page=page, page_size=page_size, options=options):
            row = submission.row_data
            row['submitted_date'] = self._iso(row['submitted_date'])
            rows.append(row)
        import __main__
        if hasattr(__main__, "mark") and not getattr(self, "_first_list_marked", False):
            self._first_list_marked = True
            __main__.mark("first page of submissions loaded")
        return dict(total=total, page=page, pages=max(1, ceil(total / page_size)), rows=rows)

    @db_call
    def context_menu(self, alias: str, id: int) -> List[dict]:
        """
        Right-click menu for a tree row. Mirrors SubmissionsTree.contextMenuEvent.

        :param alias: Alias of the model of interest.
        :type alias: str
        :param id: Unique id of the instance of interest
        :type id: int 
        :return: [{label, enabled, options}], options being sub-menu names or None.
        :rtype: List[dict]
        """
        obj = self._get(alias, id)
        menu = []
        for key in obj.custom_context_events.keys():
            match key.lower():
                case "add procedure":
                    options = [procedure.name for procedure in obj.allowed_procedures]
                case "add results":
                    options = [item['name'] for item in (obj.proceduretype.allowed_result_methods or []) if item.get('name')]
                case "preprocessing":
                    options = [item['name'] for item in (obj.proceduretype.preprocessing_methods or []) if item.get('name')]
                case _:
                    options = None
            if options == []:
                continue
            menu.append(dict(label=key, enabled=key in self.WEB_ACTIONS[alias], options=options))
        return menu      

    @db_call
    def run_action(self, alias: str, id: int, action: str, option: str | None = None, text: str | None = None) -> dict:
        """
        Runs a right-click action.

        :param alias: Alias of the model of interest.
        :type alias: str
        :param id: Unique id of the instance of interest
        :type id: int 
        :param action: Name of the action to run.
        :type action: str
        :param option: Additional param to pass to the action.
        :type option: str
        :param text: Text to include for a comment.
        :type text: str
        :return: {ok, message, refresh}
        :rtype: dict
        """
        if action not in self.WEB_ACTIONS[alias]:
            return dict(ok=False, message=f"'{action}' isn't available in the web UI yet.", refresh=False)
        try:
            obj = self._get(alias, id)
            match action:
                case "Delete":
                    if not is_power_user():
                        return dict(ok=False, message=f"User {getuser()} is not authorized for this function.", refresh=False)
                    obj.remove_from_db()
                    return dict(ok=True, message="Deleted.", refresh=True)
                case "Add Comment":
                    if not text or not text.strip():
                        return dict(ok=False, message="Comment was empty.", refresh=False)
                    obj.comment = dict(user=getuser(), time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text=text.strip())
                    report = obj.save(original=False) if alias == "run" else obj.save()
                    problems = [result.msg for result in getattr(report, "results", [])]
                    return dict(ok=not problems, message="; ".join(problems) or "Comment added.", refresh=False)
                case "Export":
                    workbook, default_name = obj.export_workbook()
                    path = self.choose_save_file(default_name, "xlsx")
                    if not path:
                        return dict(ok=False, message="Export cancelled.", refresh=False)
                    workbook.save(filename=path)
                    return dict(ok=True, message=f"Saved {path}", refresh=False)
                case "Show Details":
                      from .details import open_details_window
                      open_details_window(self._ctx, obj)
                      return dict(ok=True, message="", refresh=False)
                case "Add Run":
                      from backend.db.models import Run
                      from .sample_checker import open_sample_checker
                      dummy = Run.construct_dummy_run(clientsubmission=obj)
                      open_sample_checker(self._ctx, "Create Run",
                                          samples=[assoc.to_pydantic() for assoc in obj.clientsubmissionsampleassociation],
                                          rsl_plate_number=dummy.rsl_plate_number.value, submission_id=obj.id,
                                          on_done=lambda: self._window.evaluate_js("load(state.page)"))
                      return dict(ok=True, message="", refresh=False)
                case "Edit" if alias == "procedure":
                    from .procedure import open_procedure_window
                    open_procedure_window(self._ctx, procedure_id=obj.id,
                                          on_done=lambda: self._window.evaluate_js("load(state.page)"))
                    return dict(ok=True, message="", refresh=False)
                case "Add Procedure":
                    from .procedure import open_procedure_window
                    open_procedure_window(self._ctx, run_id=obj.id, proceduretype_name=option,
                                          on_done=lambda: self._window.evaluate_js("load(state.page)"))
                    return dict(ok=True, message="", refresh=False)
                case "Edit":
                    from .sample_checker import open_sample_checker
                    open_sample_checker(self._ctx, "Edit Run",
                                        samples=[sample.to_pydantic() for sample in obj.sample],
                                        rsl_plate_number=obj.to_pydantic().rsl_plate_number.value)
                    return dict(ok=True, message="", refresh=False)
                case "Add Results":
                    from .results import WebResultsUI, WEB_RESULTS_TYPES
                    if option not in WEB_RESULTS_TYPES:
                        return dict(ok=False, message=f"{option} results can't be added from the web UI yet.", refresh=False)
                    obj.add_results(obj=None, resultstype_name=option, ui=WebResultsUI(self._window))
                    return dict(ok=True, message=f"{option} results added.", refresh=False)
                case "Preprocessing":
                    from .preprocessing import WebSettingsUI
                    method = next((m for m in obj.proceduretype.preprocessing_methods if m.get("name") == option), None)
                    if method is None:
                        return dict(ok=False, message=f"Unknown preprocessing step: {option}", refresh=False)
                    settings = method["function"](obj=None, procedure=obj.to_pydantic(),
                                                  resultstype=method["results_type"], ui=WebSettingsUI(self._window))
                    if settings.output_path:
                        return dict(ok=True, message=f"Saved {settings.output_path}", refresh=False)
                    return dict(ok=False, message=f"{option} cancelled.", refresh=False)
        except Exception as e:
            logger.exception(f"{action} on {alias} {id} failed: {e}")
            return dict(ok=False, message=f"{action} failed: {e}", refresh=False)

    @staticmethod
    def _managables() -> List[PydBaseClass]:
        """
        Gets list of Pydantic objects that can be managed from the webui.

        :return: list(PydAbstract.get_managables()) + list(PydConcrete.get_managables())
        :rtype: List[PydBaseClass]
        """
        from backend.validators.pydant import PydAbstract, PydConcrete
        return list(PydAbstract.get_managables()) + list(PydConcrete.get_managables())

    @db_call
    def list_managables(self) -> List[str]:
        """
        Gets list of names of Pyd objects that can be managed from the webui.

        :returns: [cls.__name__.replace("Pyd", "") for cls in self._managables()]
        :rtype: List[str] 
        """
        return [cls.__name__.replace("Pyd", "") for cls in self._managables()]

    @db_call
    def open_manager(self, name: str) -> None:
        """
        Creates a webui for managing objects of a named class.

        :param name: Name of the pydantic class to manage.
        :type name: str
        """
        # from .manager import open_manager
        from .manager_page import ManagerForm
        object_type = next(cls for cls in self._managables() if cls.__name__ == f"Pyd{name}")
        api = ManagerForm(self._ctx, object_type)
        html = api._thread.run(api._page)
        api._window = webview.create_window(f"Manage {api._sql_type.__name__}", html=html, js_api=api, width=1100, height=800)
        api._window.events.closed += api._thread.close
        # self.open_manager(self._ctx, object_type)

    @db_call
    def chart_options(self, name: str) -> dict:
        from .charts import filter_options
        return filter_options(name)

    @db_call
    def chart(self, name: str, filters: dict) -> dict:
        from .charts import chart
        return chart(name, filters)

    @db_call
    def save_chart_data(self, name: str, filters: dict) -> dict:
        from .charts import save_data
        return save_data(name, filters, self.choose_save_file)

    def save_chart_png(self, name: str, filters: dict, data_url: str) -> dict:
        from .charts import save_png
        return save_png(name, filters, data_url, self.choose_save_file)

    @db_call
    def print_report(self, filters: dict) -> None:
        from .charts import open_report_window
        open_report_window(filters)

    def import_submission(self) -> dict:
        """
        Begins import of a new ClientSubmission by setting a file path.

        :returns: File path.
        :rtype: dict
        """
        from pathlib import Path
        result = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=("Excel Files (*.xlsx)",))
        if not result:
            return dict(ok=False, message="Import cancelled.")
        return self._import_path(Path(result if isinstance(result, str) else result[0]))

    def _import_path(self, path) -> dict:
        from .submission_form import open_import_window
        try:
            open_import_window(self._ctx, path, on_done=lambda: self._window.evaluate_js("load(state.page)"))
        except Exception as e:
            logger.exception(f"Couldn't import {path}: {e}")
            return dict(ok=False, message=f"Couldn't import {path.name}: {e}")
        return dict(ok=True, message="")

    def _bind_drop(self, window) -> None:
          """
          Lets an .xlsx be dropped onto the main window to import it, as the Qt submission form allowed.
          pywebview only gives the dropped file's real path to drop handlers registered from Python.
          """
          from webview.dom import DOMEventHandler
          window.dom.document.events.drop += DOMEventHandler(self._on_drop, prevent_default=True, stop_propagation=True)

    def _on_drop(self, event: dict) -> None:
        from pathlib import Path
        from threading import Thread
        files = event.get('dataTransfer', {}).get('files', [])
        paths = [Path(f['pywebviewFullPath']) for f in files if f.get('pywebviewFullPath')]
        path = next((p for p in paths if p.suffix.lower() == ".xlsx"), None)
        if path is None:
            self._window.evaluate_js("status('Drop an .xlsx submission form to import it.')")
            return

        def run():
            result = self._import_path(path)
            if result["message"]:
                self._window.evaluate_js(f"status({json.dumps(result['message'])})")

        # NOTE: Off the event thread, because opening the import window parses the whole file first.
        Thread(target=run, daemon=True).start()

    @db_call
    def open_search(self, name: str) -> None:
        from backend.db.models import Sample, ReagentLot
        from .search import open_search_window
        open_search_window(self._ctx, {"Sample": Sample, "Reagent Lot": ReagentLot}[name])

    @db_call
    def export_submissions(self) -> dict:
        from .menu_tools import export_submissions
        try:
            return export_submissions(self._window)
        except Exception as e:
            logger.exception(f"Submissions to Excel failed: {e}")
            return dict(ok=False, message=f"Submissions to Excel failed: {e}")

    def help(self, item: str) -> dict:
        from .menu_tools import open_about, open_docs, open_github
        match item:
            case "About":
                open_about(self._ctx)
            case "Docs":
                return open_docs()
            case "GitHub":
                open_github(self._ctx)
        return dict(ok=True, message="")

    # def open_manager(self, object_type: type) -> None:
    #     """
    #     Opens a manager window for a Pydantic class, as PydBaseClass.manage does.
    #     """
    #     from .manager import ManagerApi
    #     api = ManagerApi(self._ctx, object_type)
    #     html = api._thread.run(api._page)
    #     api._window = webview.create_window(f"Manage {api._sql_type.__name__}", html=html, js_api=api, width=1100, height=800)
    #     api._window.events.closed += api._thread.close