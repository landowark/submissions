"""
Python functions exposed to the web UI as window.pywebview.api.<name>.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from functools import wraps
import webview


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