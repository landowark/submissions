"""
Read every computed attribute on every seeded row.

Most of this application's derived values are ``hybrid_property`` getters that
walk a relationship and reduce it -- ``Run.completed_date`` maxes over its
procedures, ``ClientSubmission.completed_date`` maxes over its runs, ``Procedure``
sums costs. They are invoked constantly by the Jinja templates and the report
builders, but nothing calls them directly in a test, so a getter can be broken
for every row in the database while the rest of the suite stays green.

The sweep below simply reads each one against the populated ``graph`` fixture and
fails on any exception. It is deliberately assertion-light: the point is not to
pin return values (which vary with the seed) but to guarantee that no getter
raises on ordinary data. That is exactly the failure mode this project keeps
hitting -- ``max()`` over a list containing ``None``, a relationship referenced by
the wrong name, a guard that can never fire.

``test_getters_survive_partial_data`` covers the other half: rows that are only
half filled in. Unfinished procedures, unsigned runs and submissions with no runs
at all are normal states in the lab's workflow, and they are the states in which
these getters have historically blown up.
"""
from __future__ import annotations

from inspect import getattr_static

import pytest
from sqlalchemy.ext.hybrid import hybrid_property


def _computed_attrs(cls) -> list[str]:
    """Every hybrid_property / property / classproperty name declared on ``cls``."""
    names = []
    for name in dir(cls):
        if name.startswith("__"):
            continue
        try:
            attr = getattr_static(cls, name)
        except AttributeError:
            continue
        if isinstance(attr, (hybrid_property, property)):
            names.append(name)
    return sorted(names)


def _all_model_classes():
    import backend.db.models as M

    seen = {}
    stack = list(M.BaseClass.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls.__name__ in seen:
            continue
        seen[cls.__name__] = cls
        stack.extend(cls.__subclasses__())
    return seen


# Attributes that reach outside the process and cannot be read in a test.
# Keep this list short and justified -- every entry is a hole in the sweep.
SKIP = {
    # Opens a file dialog / touches the filesystem for a real submission form.
    ("ClientSubmission", "filepath"),
    ("Run", "filepath"),
}

# Getters that are known to be broken today. They are excluded from the sweep so
# it can act as a regression gate, but ``test_known_broken_getters_still_raise``
# asserts each one still fails -- so fixing the bug turns that test red and tells
# you to delete the entry here. Nothing rots silently in either direction.
KNOWN_BROKEN = {
    ("ConfigItem", "details_dict"):
        "BaseClass.details_dict (backend/db/models/__init__.py:1164) does "
        "output['name'] = self.name unconditionally, but ConfigItem's column is "
        "'key' and it has no 'name' attribute, so this always raises AttributeError.",
}


@pytest.fixture()
def model_classes(graph):
    return _all_model_classes()


def test_every_getter_is_readable(graph, model_classes):
    """No computed attribute may raise when read off a fully populated row."""
    failures = []
    for name, cls in sorted(model_classes.items()):
        try:
            rows = graph["session"].query(cls).all()
        except Exception as exc:                      # pragma: no cover - diagnostic
            failures.append(f"{name}: could not query rows: {type(exc).__name__}: {exc}")
            continue
        if not rows:
            continue
        row = rows[0]
        for attr in _computed_attrs(cls):
            if (name, attr) in SKIP or (name, attr) in KNOWN_BROKEN:
                continue
            try:
                getattr(row, attr)
            except Exception as exc:
                failures.append(f"{name}.{attr}: {type(exc).__name__}: {exc}")

    assert not failures, "computed attributes raised:\n  " + "\n  ".join(failures)


def test_every_getter_is_readable_on_every_row(graph, model_classes):
    """
    The same sweep across *all* rows, not just the first.

    Bugs in these getters are usually data-dependent -- a run with two unfinished
    procedures raises where a run with one does not -- so checking a single row
    per class is not enough.
    """
    failures = []
    for name, cls in sorted(model_classes.items()):
        attrs = [a for a in _computed_attrs(cls)
                 if (name, a) not in SKIP and (name, a) not in KNOWN_BROKEN]
        for row in graph["session"].query(cls).all():
            for attr in attrs:
                try:
                    getattr(row, attr)
                except Exception as exc:
                    failures.append(f"{name}(id={getattr(row, 'id', '?')}).{attr}: "
                                    f"{type(exc).__name__}: {exc}")
    assert not failures, "computed attributes raised:\n  " + "\n  ".join(failures[:40])


# --------------------------------------------------------------------------- #
# Partial data: the shapes these getters have actually broken on.              #
# --------------------------------------------------------------------------- #
def test_run_completed_date_with_unfinished_procedures(graph):
    """
    A run whose procedures are not all finished must not raise.

    ``Run.completed_date`` reduces its procedures with ``max()``. If the list is
    not filtered first, a procedure with no completion date puts ``None`` into the
    comparison and raises ``TypeError``. Both the all-unfinished and the
    partially-finished shapes are checked, because ``max()`` on a single-element
    list succeeds by accident and hides the bug.
    """
    from backend.db.models.submissions import Run

    run = graph["runs"][0]
    procedures = list(run.procedure)
    assert len(procedures) >= 2, "fixture must supply a multi-procedure run"

    for label, completions in [
        ("all unfinished", [None] * len(procedures)),
        ("first finished", [graph["submissions"][0].submitted_date] + [None] * (len(procedures) - 1)),
    ]:
        for procedure, value in zip(procedures, completions):
            procedure._completed_date = value
        run._completed_date = None

        run._signed_by = None
        assert run.completed_date is None, f"unsigned run ({label}) should report no completion"

        run._signed_by = "tester"
        try:
            run.completed_date
        except Exception as exc:
            pytest.fail(f"signed run with {label} procedures raised "
                        f"{type(exc).__name__}: {exc}")


def test_clientsubmission_completed_date_with_unfinished_runs(graph):
    """A submission whose runs are incomplete must not raise."""
    submission = graph["submissions"][0]
    for run in submission.run:
        run._completed_date = None
        run._signed_by = None
    try:
        assert submission.completed_date is None
    except Exception as exc:
        pytest.fail(f"ClientSubmission.completed_date raised {type(exc).__name__}: {exc}")


def test_clientsubmission_completed_date_with_no_runs(graph, db):
    """A submission with no runs at all reports ``None`` rather than raising."""
    from backend.db.models import ClientSubmission

    submission = ClientSubmission(
        submitter_plate_id="EMPTY-001",
        clientlab=graph["labs"][0],
        submissiontype=next(iter(graph["submissiontypes"].values())),
        submitted_date=graph["submissions"][0].submitted_date,
    )
    db.add(submission)
    db.commit()
    assert submission.completed_date is None


def test_turnaround_time_tolerates_incomplete_runs(graph):
    """
    ``turnaround_time`` is what the Turnaround Times tab calls on every row, and
    it reaches ``completed_date`` on the way. It has taken the whole application
    down at startup twice, so it gets its own check.
    """
    failures = []
    for submission in graph["submissions"]:
        for run in submission.run:
            run._completed_date = None
            run._signed_by = "tester"
            for procedure in run.procedure:
                procedure._completed_date = None
        try:
            submission.turnaround_time
        except Exception as exc:
            failures.append(f"{submission.submitter_plate_id}: {type(exc).__name__}: {exc}")
    assert not failures, "turnaround_time raised:\n  " + "\n  ".join(failures)


def test_signed_by_distinguishes_unset_from_set(graph):
    """
    ``signed_by`` must report something falsy when nothing has been signed.

    It previously returned the string ``"NA"``, which is truthy, silently
    disabling every ``if not run.signed_by`` guard in the codebase and inverting
    the Sign Off button in ``run_details.html``.
    """
    run = graph["runs"][0]
    run._signed_by = None
    assert not run.signed_by, "unset signature must be falsy"
    run._signed_by = "tester"
    assert run.signed_by == "tester"


def test_known_broken_getters_still_raise(graph, model_classes):
    """
    Guard the ``KNOWN_BROKEN`` list above.

    Each entry claims a getter is currently broken. If one starts working, this
    test fails -- that is the signal to delete the entry so the main sweep starts
    covering it. Without this, a fixed bug would leave a permanent blind spot.
    """
    fixed = []
    for (class_name, attr), reason in sorted(KNOWN_BROKEN.items()):
        cls = model_classes.get(class_name)
        if cls is None:
            continue
        rows = graph["session"].query(cls).all()
        if not rows:
            continue
        try:
            getattr(rows[0], attr)
        except Exception:
            continue
        fixed.append(f"{class_name}.{attr} no longer raises -- remove it from "
                     f"KNOWN_BROKEN. Recorded reason: {reason}")
    assert not fixed, "\n  ".join(fixed)
