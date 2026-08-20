"""
Pin the behaviour of the procedure-creation form.

The Equipment and Reagent sections of ``procedure_creation.html`` were converted
from Jinja-baked ``<option>`` constants to live backend fetches: the dropdowns are
now filled at runtime by ``ProcedureCreation`` pyqtSlots that the page reaches over
the QWebChannel bridge (``backend.<slot>(...)``).  That bridge is exactly the kind
of seam nothing else in the suite watches -- a slot that raises is swallowed into
an empty dropdown, and a JavaScript name the page references but never declares
fails silently in a console nobody is reading.  Every regression this form hit
during troubleshooting was one of those two shapes.

These tests therefore work at the two seams that broke:

* the model query the reagent dropdown is built from
  (``ReagentRole.get_reagents``), driven against the seeded graph; and
* the static contract between ``procedure_form.js`` and the slots on
  ``ProcedureCreation`` -- which names the page calls, and which names it uses.

The static half needs neither Qt nor a database, so it runs anywhere; the model
half uses the shared ``graph`` fixture.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Locate the two source files the form is built from.                          #
# --------------------------------------------------------------------------- #
_SRC = Path(__file__).resolve().parents[1] / "src" / "submissions"
_JS = _SRC / "templates" / "js" / "procedure_form.js"
_TEMPLATE = _SRC / "templates" / "procedure_creation.html"
_SLOTS = _SRC / "frontend" / "widgets" / "procedure_creation.py"


# --------------------------------------------------------------------------- #
# 1. The reagent dropdown's data source: ReagentRole.get_reagents.            #
#                                                                              #
#    The reagent section narrows its choices to reagents this ProcedureType    #
#    has actually used before, which the slots compute via                     #
#    ``role.get_reagents(proceduretype)``.  With no proceduretype it must fall  #
#    back to every reagent on the role.                                        #
# --------------------------------------------------------------------------- #
def _roles(graph):
    rr = graph["reagent_roles"]
    return list(rr.values()) if isinstance(rr, dict) else list(rr)


def _used_reagents_by_role_and_type(graph):
    """
    Ground truth, computed straight off the seeded procedures rather than through
    the method under test: ``(reagentrole_name, proceduretype_name) -> {Reagent}``.
    """
    used: dict[tuple[str, str], set] = defaultdict(set)
    for run in graph["runs"]:
        for proc in run.procedure:
            ptname = proc.proceduretype.name
            for assoc in proc.procedurereagentlotassociation:
                role_name = getattr(assoc.reagentrole, "name", assoc.reagentrole)
                used[(role_name, ptname)].add(assoc.reagentlot.reagent)
    return used


def test_get_reagents_without_a_type_returns_every_reagent(graph):
    """No proceduretype -> the role's full reagent list, one entry per reagent."""
    for role in _roles(graph):
        result = role.get_reagents(None)
        assert [getattr(r, "name", r) for r in result] == [r.name for r in role.reagent], (
            f"{role.name}: unscoped get_reagents diverged from role.reagent"
        )


def test_get_reagents_scoped_never_raises_and_stays_a_subset(graph):
    """
    Scoping by proceduretype must return a subset of the unscoped list and must
    not raise.

    Regression: the history query builds its ``used`` set from
    ``assoc.reagentrole.reagent``, an ``_AssociationList`` (a collection, not a
    single reagent), which is unhashable -- so the set comprehension throws
    ``TypeError`` for every role that actually has history in the type.  The fix
    is to gather ``assoc.reagentlot.reagent`` (one hashable Reagent per lot).
    See ``reagents.py`` ``ReagentRole.get_reagents``.
    """
    from backend.db.models import ProcedureType

    proceduretypes = ProcedureType.query()
    failures = []
    for role in _roles(graph):
        allowed = {getattr(r, "name", r) for r in role.get_reagents(None)}
        for pt in proceduretypes:
            try:
                scoped = role.get_reagents(pt)
            except Exception as exc:  # noqa: BLE001 - report, don't mask
                failures.append(f"{role.name} / {pt.name}: "
                                f"{type(exc).__name__}: {exc}")
                continue
            names = {getattr(r, "name", r) for r in scoped}
            if not names <= allowed:
                failures.append(f"{role.name} / {pt.name}: {names - allowed} "
                                f"not in unscoped list")
    assert not failures, "get_reagents(proceduretype) misbehaved:\n  " + "\n  ".join(failures)


# --------------------------------------------------------------------------- #
# 1b. The slots the reagent dropdown is actually filled by.                    #
#                                                                              #
#     ``get_reagent_names`` / ``get_reagentlot_names`` are what the page calls  #
#     over the bridge.  They wrap ``get_reagents`` but add the failure mode     #
#     that bit us twice: the pydantic reagents returned by the fallback branch  #
#     carry their lots as bare strings, so ``lot.active`` / ``lot.name`` blow   #
#     up.  Drive the real slots, not just the model, so both live here.        #
#                                                                              #
#     Constructing a full ``ProcedureCreation`` runs a pydantic reorder pass    #
#     that is unrelated to these slots (and currently broken for tip-bearing    #
#     equipment), so the slots are exercised on a bare instance with only the   #
#     one attribute they read -- ``self.procedure.proceduretype`` -- wired up.  #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the session; the slots need a live QObject host."""
    pytest.importorskip("PyQt6.QtWidgets", reason="PyQt6 is required for slot tests")
    pytest.importorskip("PyQt6.QtWebEngineWidgets", reason="PyQt6-WebEngine is required")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(["", "--no-sandbox"])
    yield app
    app.processEvents()


def _bare_slots(proceduretype):
    """
    A ``ProcedureCreation`` with only ``self.procedure.proceduretype`` populated.

    Built through ``__new__`` so the fragile ``__init__`` (WebEngine, channel,
    the reorder pass) is skipped -- the reagent slots read nothing else.
    """
    from types import SimpleNamespace
    from frontend.widgets.procedure_creation import ProcedureCreation

    pc = ProcedureCreation.__new__(ProcedureCreation)
    pc.procedure = SimpleNamespace(proceduretype=proceduretype)
    return pc


def test_reagent_slots_never_raise_and_return_strings(qapp, graph):
    """
    Whatever the (role, type) combination, the two dropdown slots must return a
    list of strings and never raise.

    A raising slot is invisible from the page -- the QWebChannel swallows it into
    an empty dropdown -- so the failure only ever shows up as a mysteriously empty
    control.  Two regressions live under this one assertion: the unhashable
    ``_AssociationList`` in ``get_reagents`` (a ``TypeError``), and the pydantic
    fallback whose lots are strings, so ``get_reagentlot_names`` hits
    ``'str' object has no attribute 'active'``.
    """
    from backend.db.models import ProcedureType

    roles = _roles(graph)
    failures = []
    for pt in ProcedureType.query():
        pc = _bare_slots(pt)
        for role in roles:
            for slot in ("get_reagent_names", "get_reagentlot_names"):
                try:
                    out = getattr(pc, slot)(role.name)
                except Exception as exc:  # noqa: BLE001 - the point is to report it
                    failures.append(f"{pt.name}/{role.name}.{slot}: "
                                    f"{type(exc).__name__}: {exc}")
                    continue
                if not (isinstance(out, list) and all(isinstance(x, str) for x in out)):
                    failures.append(f"{pt.name}/{role.name}.{slot}: "
                                    f"returned {out!r}, expected list[str]")
    assert not failures, "reagent dropdown slots misbehaved:\n  " + "\n  ".join(failures)


def test_reagent_name_slot_scopes_to_history(qapp, graph):
    """
    Through the real slot: the reagent names offered for a role under a
    proceduretype are exactly the reagents that type's procedures have used.

    Ground truth is derived independently from the seeded procedure
    associations, so this pins the scoping behaviour end to end at the seam the
    page talks to.
    """
    from backend.db.models import ProcedureType

    used = _used_reagents_by_role_and_type(graph)
    checked = 0
    for (role_name, pt_name), reagents in used.items():
        pt = ProcedureType.query(name=pt_name, limit=1)
        offered = set(_bare_slots(pt).get_reagent_names(role_name))
        expected = {r.name for r in reagents}
        assert offered == expected, (
            f"{role_name} under {pt_name}: slot offered {offered}, "
            f"but the type has used {expected}"
        )
        checked += 1
    assert checked, "fixture seeded no reagent history to scope against"


# --------------------------------------------------------------------------- #
# 2. The JS <-> slot contract.                                                #
#                                                                              #
#    procedure_form.js drives the form by calling ``backend.<name>(...)``,     #
#    which crosses the QWebChannel to a pyqtSlot on ProcedureCreation. A name   #
#    the page calls but the widget does not define is a dead control: the call  #
#    rejects in a console nobody watches and the field silently does nothing.   #
# --------------------------------------------------------------------------- #
def _backend_calls(js_text):
    return set(re.findall(r"backend\.(\w+)\s*\(", js_text))


def _slot_names(py_text):
    return set(re.findall(r"def (\w+)\s*\(", py_text))


def test_every_backend_call_has_a_matching_slot():
    """
    Every ``backend.<name>(`` in procedure_form.js resolves to a method on
    ``ProcedureCreation``.

    This is the check that would have caught the ``get_equipment_list`` /
    ``get_process_list`` typos (the slots are ``get_equipment_names`` /
    ``get_processversion_names``).  It currently also flags ``update_date``,
    which the date fields call (procedure_form.js) but no slot implements.
    """
    called = _backend_calls(_JS.read_text())
    defined = _slot_names(_SLOTS.read_text())
    missing = sorted(called - defined)
    assert not missing, (
        "procedure_form.js calls backend slots that ProcedureCreation does not "
        f"define: {missing}"
    )


def test_new_reagent_subform_references_only_declared_variables():
    """
    Selecting ``--New--`` builds an add-reagentlot subform in JS.  That handler
    must not reference a variable it never declares, or it throws ``ReferenceError``
    and aborts before the subform is appended -- so ``--New--`` does nothing.

    Regression: the barcode inputs ``rr_lims`` / ``rr_lims_label`` were commented
    out where they were declared, but the ``appendChild`` calls that use them were
    left live.  A read of an undeclared name should not survive in the handler.
    """
    js = _JS.read_text()
    # Strip line and block comments so we only see code that actually runs.
    code = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    code = re.sub(r"(?m)//.*$", "", code)
    orphaned = sorted(set(re.findall(r"\b(rr_lims\w*)\b", code)))
    assert not orphaned, (
        "procedure_form.js references undeclared barcode variables "
        f"{orphaned} in live code (their declarations are commented out); "
        "the --New-- handler will throw ReferenceError before the subform renders"
    )


def test_reagent_dropdown_is_filled_from_the_backend_not_baked_html():
    """
    The reagent section was converted from Jinja-baked ``<option>`` constants to a
    live fetch.  Pin both halves of that conversion so it cannot silently revert:

    * the JS populates the dropdown from ``backend.get_reagentlot_names`` and
      appends the ``--New--`` sentinel itself, and
    * the template's reagent ``<select>`` no longer ships baked reagent options.
    """
    js = _JS.read_text()
    assert "backend.get_reagentlot_names" in js, (
        "the reagent dropdown is no longer populated from the backend"
    )
    assert 'new Option("--New--"' in js or "'--New--'" in js, (
        "the JS no longer appends the --New-- sentinel to the reagent dropdown"
    )

    template = _TEMPLATE.read_text()
    # The active reagentrole <select> (id="{{rname}}") must not carry a live,
    # uncommented reagentlot <option> loop -- that data now comes from the slot.
    without_comments = re.sub(r"<!--.*?-->", "", template, flags=re.S)
    reagent_block = re.search(
        r'<select[^>]*class="reagentrole[^"]*"[^>]*>(.*?)</select>',
        without_comments, flags=re.S,
    )
    assert reagent_block is not None, "could not find the reagentrole <select> in the template"
    assert "<option" not in reagent_block.group(1), (
        "the reagentrole <select> still bakes <option> constants; the reagent "
        "list is supposed to be fetched live via get_reagentlot_names"
    )
