"""
Behavioural tests for ``SubmissionFormContainer.import_submission_function``
(``frontend/widgets/submission_widget.py:147``).

Why this method is awkward to test
----------------------------------
It is written to be driven by a human and reaches for three collaborators that
all want a real environment:

* ``select_open_file`` (functions.py:15) opens a native ``QFileDialog``.
* ``DefaultClientSubmissionManager`` (managers/clientsubmissions.py:19) opens the
  chosen workbook and queries the database for a ``SubmissionType``.
* ``SampleChecker`` (sample_checker.py:18) is a modal ``QDialog`` wrapping a
  ``QWebEngineView``, and the method branches on ``dlg.exec()``.

So the tests here substitute fakes for all three and drive the *real* method
against a real widget tree, exactly as ``test_run_actions.py`` does for the Run
context-menu actions. What lives inside the web view is out of scope, matching
the note in ``test_widgets.py``.

One extra wrinkle: the method is wrapped in ``@report_result``
(tools/__init__.py:815), which pops an ``AlertPop`` message box for every Alert
in the returned Report and then *swallows the Report itself* -- for a bare
``Report`` return value the decorator hands the caller ``None``
(tools/__init__.py:859). Tests that care about the report therefore call
``import_submission_function.__wrapped__``; tests that care about what the user
actually sees call the decorated method with ``AlertPop`` patched.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets", reason="PyQt6 is required for these tests")
pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="PyQt6-WebEngine is required")


# --------------------------------------------------------------------------- #
# Qt application (mirrors test_widgets.py: exactly one, session scoped).       #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["", "--no-sandbox"])
    yield app
    app.processEvents()


# --------------------------------------------------------------------------- #
# The widget under test.                                                       #
#                                                                              #
# ``SubmissionFormContainer.__init__`` (submission_widget.py:92) reaches two    #
# levels up with ``self.parent().parent()`` to find the application, and the    #
# import method calls ``self.layout().addWidget(...)`` even though the class    #
# never gives itself a layout -- app.py:266 installs one from the outside. The  #
# fixture reproduces both facts so the tests exercise the real wiring.          #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def container(qapp):
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from frontend.widgets.submission_widget import SubmissionFormContainer

    app_stand_in = QWidget()          # what self.app resolves to
    middle = QWidget(app_stand_in)    # the tab widget in the real app
    widget = SubmissionFormContainer(middle)
    widget.setLayout(QVBoxLayout())   # app.py:266 does this for the real one
    try:
        yield widget
    finally:
        widget.setParent(None)
        app_stand_in.deleteLater()
        qapp.processEvents()


# --------------------------------------------------------------------------- #
# Fakes                                                                        #
# --------------------------------------------------------------------------- #
def _fake_pyd(form_widget=None):
    """
    A stand-in for the parsed submission. ``spec=`` keeps the ``isinstance``
    assertion at submission_widget.py:183 satisfied, which is what the real
    manager's ``to_pydantic()`` would return.
    """
    from unittest.mock import MagicMock

    from backend.validators import PydClientSubmission

    pyd = MagicMock(spec=PydClientSubmission)
    pyd.sample = []
    pyd.to_form.return_value = form_widget
    return pyd


def _patch_manager(monkeypatch, *, pyd=None, raises=None):
    """
    Replace ``DefaultClientSubmissionManager``. The method imports it from
    ``backend.managers`` at call time (submission_widget.py:157), so patching the
    attribute on that module is enough. Returns a recorder dict.
    """
    import backend.managers as managers

    recorder = {}

    class _FakeManager:
        def __init__(self, parent=None, input_object=None, **kwargs):
            recorder["parent"] = parent
            recorder["input_object"] = input_object
            recorder["manager"] = self
            if raises is not None:
                raise raises

        def to_pydantic(self):
            recorder["to_pydantic_called"] = True
            return pyd

    monkeypatch.setattr(managers, "DefaultClientSubmissionManager", _FakeManager)
    return recorder


def _patch_checker(monkeypatch, *, accept: bool):
    """
    Replace the modal ``SampleChecker``. It is bound into the module namespace at
    import time (submission_widget.py:20), so the patch goes on
    ``frontend.widgets.submission_widget``.
    """
    import frontend.widgets.submission_widget as sw

    recorder = {}

    class _FakeChecker:
        def __init__(self, parent, title, samples, run=None):
            recorder["parent"] = parent
            recorder["title"] = title
            recorder["samples"] = samples
            recorder["checker"] = self

        def exec(self):
            recorder["exec_called"] = True
            return 1 if accept else 0

    monkeypatch.setattr(sw, "SampleChecker", _FakeChecker)
    return recorder


def _patch_file_dialog(monkeypatch, *, returns=None, raises=None):
    """Replace ``select_open_file``; also bound at import time."""
    import frontend.widgets.submission_widget as sw

    recorder = {"calls": []}

    def _fake(obj, file_extension=None):
        recorder["calls"].append((obj, file_extension))
        if raises is not None:
            raise raises
        return returns

    monkeypatch.setattr(sw, "select_open_file", _fake)
    return recorder

@pytest.fixture()
def alerts(monkeypatch):
    """
    Capture what ``@report_result`` would show the user. ``Alert.report()``
    imports ``AlertPop`` at call time (tools/__init__.py:703), so patching the
    module attribute intercepts every popup -- and keeps ``exec()`` from blocking
    the suite on a modal dialog.
    """
    import frontend.widgets.pop_ups as pop_ups

    captured = []

    class _FakeAlertPop:
        def __init__(self, message, status, owner=None):
            self.message = message
            self.status = status
            self.owner = owner
            captured.append(self)

        def exec(self):
            return 0

    monkeypatch.setattr(pop_ups, "AlertPop", _FakeAlertPop)
    return captured


def _raw(container):
    """The undecorated function, so a test can see the Report it builds."""
    return type(container).import_submission_function.__wrapped__


# --------------------------------------------------------------------------- #
# 1. Choosing the file.                                                        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("passed", [None, False, True])
def test_missing_path_opens_the_file_dialog(container, monkeypatch, alerts, passed):
    """
    ``None`` means "no path yet"; ``False`` is what ``QAction.triggered`` sends
    through the lambda at app.py:145 (the signal carries a checked-state bool).
    Both must fall through to the picker rather than being treated as a path.
    """
    dialog = _patch_file_dialog(monkeypatch, returns=None)
    _patch_manager(monkeypatch, pyd=_fake_pyd())

    container.import_submission_function(fname=passed)

    assert len(dialog["calls"]) == 1
    obj, extension = dialog["calls"][0]
    assert obj is container
    assert extension == "xlsx"


def test_supplied_path_skips_the_file_dialog(container, monkeypatch, alerts, tmp_path):
    """A path handed in by the drag-and-drop route must be used as-is."""
    from PyQt6.QtWidgets import QWidget

    book = tmp_path / "submission.xlsx"
    book.write_bytes(b"not really a workbook")

    dialog = _patch_file_dialog(monkeypatch, returns=None)
    manager = _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    _patch_checker(monkeypatch, accept=True)

    container.import_submission_function(fname=book)

    assert dialog["calls"] == []
    assert manager["input_object"] == book
    assert manager["parent"] is container


# --------------------------------------------------------------------------- #
# 2. The cancel paths.                                                         #
# --------------------------------------------------------------------------- #
def test_cancelled_file_dialog_produces_a_report(container, monkeypatch, alerts):
    """
    ``select_open_file`` returns ``None`` when the user cancels
    (functions.py:45-47). The method must stop, and must not build a manager.
    """
    _patch_file_dialog(monkeypatch, returns=None)
    manager = _patch_manager(monkeypatch, pyd=_fake_pyd())

    report = _raw(container)(container)

    assert len(report.results) == 1
    assert "manager" not in manager


@pytest.mark.xfail(
    strict=True,
    reason="Cancelling the file dialog is reported as a CRITICAL error reading "
           "'File None not found.'. submission_widget.py:173-174 formats the "
           "message from `fname` after `select_open_file` has already returned "
           "None for the cancel case (functions.py:45-47), so the user gets an "
           "error popup with the literal word 'None' in it for what is simply a "
           "cancelled dialog. A cancel is not an error: it should be a WARNING "
           "worded like the 'Submission cancelled.' branch at "
           "submission_widget.py:190, or no alert at all. Delete this xfail when "
           "fixed.",
)
def test_cancelled_file_dialog_is_not_reported_as_a_critical_error(container, monkeypatch, alerts):
    from tools import AlertStatus

    _patch_file_dialog(monkeypatch, returns=None)
    _patch_manager(monkeypatch, pyd=_fake_pyd())

    report = _raw(container)(container)

    alert = report.results[0]
    assert alert.status != AlertStatus.CRITICAL.value
    assert "None" not in alert.msg


def test_cancelled_sample_checker_reports_a_warning_and_adds_no_form(container, monkeypatch, alerts):
    """Rejecting the SampleChecker must abandon the import, not half-apply it."""
    from PyQt6.QtWidgets import QWidget

    from tools import AlertStatus

    _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    checker = _patch_checker(monkeypatch, accept=False)

    report = _raw(container)(container, fname=Path("/some/book.xlsx"))

    assert checker["exec_called"]
    assert container.layout().count() == 0
    assert len(report.results) == 1
    assert report.results[0].msg == "Submission cancelled."
    assert report.results[0].status == AlertStatus.WARNING.value


# --------------------------------------------------------------------------- #
# 3. The happy path.                                                           #
# --------------------------------------------------------------------------- #
def test_accepted_checker_builds_the_form_and_adds_it_to_the_layout(container, monkeypatch, alerts):
    from PyQt6.QtWidgets import QWidget

    form = QWidget()
    pyd = _fake_pyd(form)
    _patch_manager(monkeypatch, pyd=pyd)
    _patch_checker(monkeypatch, accept=True)

    report = _raw(container)(container, fname=Path("/some/book.xlsx"))

    assert container.form is form
    assert container.layout().indexOf(form) != -1
    pyd.to_form.assert_called_once_with(parent=container)
    assert report.results == []


def test_state_is_reset_before_each_import(container, monkeypatch, alerts):
    """
    ``samples`` and ``missing_info`` are scratch state for the form being built;
    a new import must not inherit the previous one's (submission_widget.py:168).
    """
    from PyQt6.QtWidgets import QWidget

    container.samples = ["stale"]
    container.missing_info = ["stale"]

    _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    _patch_checker(monkeypatch, accept=True)

    container.import_submission_function(fname=Path("/some/book.xlsx"))

    assert container.samples == []
    assert container.missing_info == []

def test_a_second_import_replaces_the_first_form(container, monkeypatch, alerts):
    from PyQt6.QtWidgets import QWidget

    first, second = QWidget(), QWidget()

    _patch_manager(monkeypatch, pyd=_fake_pyd(first))
    _patch_checker(monkeypatch, accept=True)
    container.import_submission_function(fname=Path("/a.xlsx"))

    _patch_manager(monkeypatch, pyd=_fake_pyd(second))
    _patch_checker(monkeypatch, accept=True)
    container.import_submission_function(fname=Path("/b.xlsx"))

    assert container.form is second
    assert container.layout().indexOf(first) == -1
    assert container.layout().indexOf(second) != -1


def test_the_checker_is_shown_the_parsed_samples(container, monkeypatch, alerts):
    from PyQt6.QtWidgets import QWidget

    pyd = _fake_pyd(QWidget())
    pyd.sample = ["sample-a", "sample-b"]
    _patch_manager(monkeypatch, pyd=pyd)
    checker = _patch_checker(monkeypatch, accept=True)

    container.import_submission_function(fname=Path("/some/book.xlsx"))

    assert checker["samples"] == ["sample-a", "sample-b"]
    assert checker["parent"] is container


# --------------------------------------------------------------------------- #
# 4. Bad input. This is the drag-and-drop route: dragEnterEvent               #
#    (submission_widget.py:100) accepts *any* url, and dropEvent emits the     #
#    path straight into this method.                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.xfail(
    strict=True,
    reason="A path that does not exist is never rejected. The guard at "
           "submission_widget.py:173 is `if not fname:`, and a pathlib.Path is "
           "always truthy -- even Path('') normalises to PosixPath('.'). So the "
           "'File ... not found.' alert the author wrote on the next line can "
           "only ever fire for None/False from the dialog, never for an actual "
           "missing file. The bad path is handed to "
           "DefaultClientSubmissionManager (submission_widget.py:177), which "
           "raises FileNotFoundError from DefaultNamer.__init__ "
           "(validators/__init__.py:26-29). Nothing in the method or in "
           "@report_result catches it, so it escapes into the Qt slot that "
           "dropEvent fired. Guard with `fname.exists()`. Delete this xfail when "
           "fixed.",
)
def test_a_nonexistent_path_is_reported_not_raised(container, monkeypatch, alerts, tmp_path):
    missing = tmp_path / "no-such-file.xlsx"
    _patch_manager(monkeypatch, raises=FileNotFoundError(f"File {missing} does not exist."))
    _patch_checker(monkeypatch, accept=True)

    report = _raw(container)(container, fname=missing)

    assert len(report.results) == 1
    assert "not found" in report.results[0].msg.lower()


@pytest.mark.xfail(
    strict=True,
    reason="Same guard, different trigger: dragEnterEvent "
           "(submission_widget.py:100) accepts any drop that hasUrls(), so a "
           "folder or a .txt reaches import_submission_function as a real, "
           "existing Path. It sails past `if not fname:` "
           "(submission_widget.py:173) into the workbook loader, where "
           "openpyxl's load_workbook (validators/__init__.py:31) raises rather "
           "than producing an Alert. Either filter the drop by suffix or wrap "
           "the manager construction in a try/except that adds to the report. "
           "Delete this xfail when fixed.",
)
def test_a_non_workbook_path_is_reported_not_raised(container, monkeypatch, alerts, tmp_path):
    not_a_book = tmp_path / "notes.txt"
    not_a_book.write_text("this is not a workbook")
    _patch_manager(monkeypatch, raises=ValueError("openpyxl does not support this format"))
    _patch_checker(monkeypatch, accept=True)

    report = _raw(container)(container, fname=not_a_book)

    assert len(report.results) == 1


@pytest.mark.xfail(
    strict=True,
    reason="select_open_file raises FileNotFoundError when the chosen path does "
           "not exist (functions.py:43-44) and import_submission_function calls "
           "it bare at submission_widget.py:172. The exception crosses the whole "
           "method uncaught, so a race (file deleted or unmounted between the "
           "dialog listing it and the user clicking Open) escapes into the Qt "
           "event loop instead of becoming the CRITICAL alert already written "
           "one line below. Delete this xfail when fixed.",
)
def test_a_raising_file_dialog_is_reported_not_raised(container, monkeypatch, alerts):
    _patch_file_dialog(monkeypatch, raises=FileNotFoundError("File /gone.xlsx could not be found."))
    _patch_manager(monkeypatch, pyd=_fake_pyd())

    report = _raw(container)(container)

    assert len(report.results) == 1

# --------------------------------------------------------------------------- #
# 5. Contract details worth pinning.                                          #
# --------------------------------------------------------------------------- #
def test_the_decorated_method_returns_none(container, monkeypatch, alerts):
    """
    Documented as '-> Report' (submission_widget.py:147) but @report_result maps
    a bare Report return to None (tools/__init__.py:859). Pinned so a caller
    written against the annotation is caught here rather than in production.
    """
    from PyQt6.QtWidgets import QWidget

    _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    _patch_checker(monkeypatch, accept=True)

    assert container.import_submission_function(fname=Path("/a.xlsx")) is None


def test_the_cancel_alert_reaches_the_user(container, monkeypatch, alerts):
    """The decorator must actually surface the cancel warning as a popup."""
    from PyQt6.QtWidgets import QWidget

    _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    _patch_checker(monkeypatch, accept=False)

    container.import_submission_function(fname=Path("/a.xlsx"))

    assert len(alerts) == 1
    assert alerts[0].message == "Submission cancelled."


@pytest.mark.xfail(
    strict=True,
    reason="The `owner=self.__class__.__name__` argument at "
           "submission_widget.py:191 is dead. Alert.__init__ "
           "(tools/__init__.py:698-700) unconditionally overwrites owner with "
           "`stack()[1].function`, so every Alert is owned by the function that "
           "constructed it and the popup title reads "
           "'import_submission_function - Warning' instead of naming the widget. "
           "Either honour an explicitly passed owner or drop the parameter from "
           "the call sites. Delete this xfail when fixed.",
)
def test_an_explicit_alert_owner_is_honoured(container, monkeypatch, alerts):
    from PyQt6.QtWidgets import QWidget

    _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    _patch_checker(monkeypatch, accept=False)

    report = _raw(container)(container, fname=Path("/a.xlsx"))

    assert report.results[0].owner == "SubmissionFormContainer"


@pytest.mark.xfail(
    strict=True,
    reason="Cancelling an import destroys the form that was already on screen. "
           "submission_widget.py:163-166 does `self.form.setParent(None)` before "
           "the file dialog even opens, so backing out of either dialog leaves "
           "the user with an empty panel and a 'Submission cancelled.' popup -- "
           "their previous work is gone from the layout with no way back. Clear "
           "the old form only once the new one is ready to take its place. "
           "Delete this xfail when fixed.",
)
def test_cancelling_leaves_the_existing_form_alone(container, monkeypatch, alerts):
    from PyQt6.QtWidgets import QWidget

    # First, a successful import puts a form on screen.
    first = QWidget()
    _patch_manager(monkeypatch, pyd=_fake_pyd(first))
    _patch_checker(monkeypatch, accept=True)
    container.import_submission_function(fname=Path("/a.xlsx"))
    assert container.layout().indexOf(first) != -1

    # Now the user starts a second import and backs out of it.
    _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
    _patch_checker(monkeypatch, accept=False)
    container.import_submission_function(fname=Path("/b.xlsx"))

    assert container.layout().indexOf(first) != -1


@pytest.mark.xfail(
    strict=True,
    reason="The isinstance guard at submission_widget.py:182-186 is unreachable "
           "as protection: it runs *after* SampleChecker has already been handed "
           "`self.pydclientsubmission.sample` at submission_widget.py:180. If "
           "to_pydantic() ever returns the wrong type, the AttributeError from "
           "the line above fires first and the assertion never gets to report "
           "the real problem. Move the check to immediately after the "
           "to_pydantic() call on line 178. Delete this xfail when fixed.",
)
def test_a_wrong_pydantic_type_is_caught_by_the_assertion(container, monkeypatch, alerts):
    _patch_manager(monkeypatch, pyd=object())   # no .sample attribute
    _patch_checker(monkeypatch, accept=True)

    with pytest.raises(AssertionError):
        _raw(container)(container, fname=Path("/a.xlsx"))


def test_the_container_never_gives_itself_a_layout(qapp, monkeypatch, alerts):
    """
    Pins a structural fragility: ``import_submission_function`` calls
    ``self.layout().addWidget(...)`` (submission_widget.py:188) but
    ``SubmissionFormContainer.__init__`` never sets a layout -- app.py:266 does
    it from the outside. Construct the widget on its own and the happy path dies
    on ``NoneType.addWidget``. Not a bug in the running app, but the class does
    not stand up alone, and any second construction site has to know that.
    """
    from PyQt6.QtWidgets import QWidget

    from frontend.widgets.submission_widget import SubmissionFormContainer
    grandparent = QWidget()
    widget = SubmissionFormContainer(QWidget(grandparent))
    try:
        assert widget.layout() is None
        _patch_manager(monkeypatch, pyd=_fake_pyd(QWidget()))
        _patch_checker(monkeypatch, accept=True)
        with pytest.raises(AttributeError):
            widget.import_submission_function(fname=Path("/a.xlsx"))
    finally:
        widget.setParent(None)
        grandparent.deleteLater()
        qapp.processEvents()