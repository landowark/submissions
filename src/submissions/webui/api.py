"""
Python functions exposed to the web UI as window.pywebview.api.<name>.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from functools import wraps
import webview
from math import ceil
from datetime import date, datetime
from getpass import getuser
from tools import is_power_user

# NOTE: Right-click actions the web UI can run so far. The rest still need their Qt dialogs ported.
WEB_ACTIONS = {
        "submission": {"Delete", "Add Comment", "Show Details", "Add Run"},
        "run": {"Delete", "Add Comment", "Show Details", "Export", "Edit", "Add Procedure"},
        "procedure": {"Delete", "Add Comment", "Show Details", "Add Results", "Edit"},
    }

def _iso(value) -> str:
    """
    Returns time in iso format string.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return "" if value is None else str(value)

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

    def __init__(self, ctx):
        # NOTE: Underscore names are not exposed to JS by pywebview.
        self._ctx = ctx
        self._window = None

    def app_info(self) -> dict:
        return dict(
            version=self._ctx.package.__version__,
            database=f"{self._ctx.database.path}/{self._ctx.database.name}",
        )

    @db_call
    def submission_count(self) -> int:
        from sqlalchemy import func
        from backend.db.models import ClientSubmission
        return self._ctx.database.session().query(func.count(ClientSubmission.id)).scalar()

    def choose_save_file(self, default_name: str, extension: str) -> str | None:
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=f"{default_name}.{extension}",
            file_types=(f"{extension.upper()} files (*.{extension})",))
        return result if isinstance(result, str) else (result[0] if result else None)

    @staticmethod
    def _model(kind: str):
        from backend.db.models import ClientSubmission, Run, Procedure
        return {"submission": ClientSubmission, "run": Run, "procedure": Procedure}[kind]

    def _get(self, kind: str, id: int):
        obj = self._ctx.database.session().get(self._model(kind), int(id))
        if obj is None:
            raise LookupError(f"No {kind} with id {id}.")
        return obj

    @db_call
    def list_submissions(self, page: int = 1, page_size: int = 250) -> dict:
        """
        One page of the submissions tree, newest first.

        :return: {total, page, pages, rows}
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
            row['submitted_date'] = _iso(row['submitted_date'])
            rows.append(row)
        return dict(total=total, page=page, pages=max(1, ceil(total / page_size)), rows=rows)

    @db_call
    def context_menu(self, kind: str, id: int) -> list:
        """
        Right-click menu for a tree row. Mirrors SubmissionsTree.contextMenuEvent.

        :return: [{label, enabled, options}], options being sub-menu names or None.
        """
        obj = self._get(kind, id)
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
            menu.append(dict(label=key, enabled=key in WEB_ACTIONS[kind], options=options))
        return menu      

    @db_call
    def run_action(self, kind: str, id: int, action: str, option: str | None = None, text: str | None = None) -> dict:
        """
        Runs a right-click action.

        :return: {ok, message, refresh}
        """
        if action not in WEB_ACTIONS[kind]:
            return dict(ok=False, message=f"'{action}' isn't available in the web UI yet.", refresh=False)
        try:
            obj = self._get(kind, id)
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
                    report = obj.save(original=False) if kind == "run" else obj.save()
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
                case "Edit" if kind == "procedure":
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
        except Exception as e:
            logger.exception(f"{action} on {kind} {id} failed: {e}")
            return dict(ok=False, message=f"{action} failed: {e}", refresh=False)

    @staticmethod
    def _managables() -> list:
        from backend.validators.pydant import PydAbstract, PydConcrete
        return list(PydAbstract.get_managables()) + list(PydConcrete.get_managables())

    @db_call
    def list_managables(self) -> list:
        return [cls.__name__.replace("Pyd", "") for cls in self._managables()]

    @db_call
    def open_manager(self, name: str) -> None:
        from .manager import open_manager
        object_type = next(cls for cls in self._managables() if cls.__name__ == f"Pyd{name}")
        open_manager(self._ctx, object_type)

    