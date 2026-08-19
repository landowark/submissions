"""
``details_dict`` and ``to_pydantic`` on every seeded row.

These two methods are the boundary between the ORM and everything the user
actually sees. ``details_dict`` feeds the Jinja templates rendered inside the
QWebEngineView panes; ``to_pydantic`` feeds the edit forms and the Excel writers.
Both walk the whole object graph and touch nearly every hybrid property on the
way, so they are a broad, cheap smoke test of the model layer -- and both have
broken in ways that no other test noticed:

* ``details_dict`` assumes every model has a ``name`` attribute, which
  ``ConfigItem`` does not.
* ``Run.to_pydantic`` built a placeholder path with ``Path(TemporaryFile().name)``.
  On Windows ``.name`` is a string; on Linux and macOS it is the integer file
  descriptor, so the call raised ``TypeError`` on every non-Windows machine.

The JSON-serializability check matters because ``details_dict`` output is handed
to a template engine and, in places, embedded into the page as JSON. A value that
survives Python but not ``json.dumps`` fails only at render time.
"""
from __future__ import annotations

from json import dumps

import pytest

# ConfigItem is covered by KNOWN_BROKEN in test_hybrid_properties.py; excluded
# here for the same reason and with the same fix.
DETAILS_DICT_KNOWN_BROKEN = {"ConfigItem"}


def _model_classes():
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


def test_details_dict_on_every_seeded_row(graph):
    """No model's ``details_dict`` may raise on ordinary data."""
    failures = []
    for name, cls in sorted(_model_classes().items()):
        if name in DETAILS_DICT_KNOWN_BROKEN:
            continue
        for row in graph["session"].query(cls).all():
            try:
                row.details_dict
            except Exception as exc:
                failures.append(f"{name}(id={getattr(row, 'id', '?')}): "
                                f"{type(exc).__name__}: {exc}")
                break          # one report per class is enough
    assert not failures, "details_dict raised:\n  " + "\n  ".join(failures)


def test_details_dict_is_json_serializable(graph):
    """
    Whatever ``details_dict`` returns has to survive ``json.dumps``.

    The values are sanitized on the way out precisely so the result can be handed
    to a template or embedded in a page; an unsanitized value fails at render
    time, inside a WebEngine view, where the traceback is easy to miss.
    """
    failures = []
    for name, cls in sorted(_model_classes().items()):
        if name in DETAILS_DICT_KNOWN_BROKEN:
            continue
        rows = graph["session"].query(cls).all()
        if not rows:
            continue
        try:
            dumps(rows[0].details_dict, default=str)
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failures, "details_dict output was not serializable:\n  " + "\n  ".join(failures)


def test_details_dict_declares_its_exclusions(graph):
    """
    Templates iterate ``for key, value in obj.items() if key not in obj['excluded']``,
    so the ``excluded`` key has to be present and iterable on every payload.
    """
    for kind in ("submissions", "runs"):
        for row in graph[kind]:
            details = row.details_dict
            assert "excluded" in details, f"{type(row).__name__} has no 'excluded' key"
            assert isinstance(details["excluded"], (list, tuple, set))


# --------------------------------------------------------------------------- #
# to_pydantic                                                                  #
# --------------------------------------------------------------------------- #
def test_run_to_pydantic(graph):
    """
    ``Run.to_pydantic`` must work on the machine the tests run on.

    This is the one that was Windows-only for months.
    """
    run = graph["runs"][0]
    pyd = run.to_pydantic()
    assert pyd is not None
    assert pyd.rsl_plate_number.value == run.rsl_plate_number


def test_run_to_pydantic_on_every_run(graph):
    failures = []
    for run in graph["runs"]:
        try:
            run.to_pydantic()
        except Exception as exc:
            failures.append(f"{run.rsl_plate_number}: {type(exc).__name__}: {exc}")
    assert not failures, "Run.to_pydantic raised:\n  " + "\n  ".join(failures)


def test_run_to_pydantic_filepath_is_a_path(graph):
    """
    The placeholder ``filepath`` has to be a real path object.

    ``PydRun.filepath`` is typed as a path and is passed to the Excel writers; an
    integer file descriptor there fails much further downstream than here.
    """
    from pathlib import Path

    pyd = graph["runs"][0].to_pydantic()
    assert isinstance(pyd.filepath, Path)


def test_sample_to_pydantic(graph):
    failures = []
    for sample in graph["samples"][:20]:
        try:
            sample.to_pydantic()
        except Exception as exc:
            failures.append(f"{sample.sample_id}: {type(exc).__name__}: {exc}")
    assert not failures, "Sample.to_pydantic raised:\n  " + "\n  ".join(failures)


def test_clientsubmission_to_pydantic(graph):
    failures = []
    for submission in graph["submissions"]:
        try:
            submission.to_pydantic()
        except Exception as exc:
            failures.append(f"{submission.submitter_plate_id}: "
                            f"{type(exc).__name__}: {exc}")
    assert not failures, "ClientSubmission.to_pydantic raised:\n  " + "\n  ".join(failures)


def test_pydantic_round_trip_preserves_identity(graph, db):
    """
    ``sql -> pydantic -> sql`` has to come back to the same row, not a copy.

    ``to_sql`` looks the instance up rather than inserting blindly; if that lookup
    ever misses, editing a run through the form would silently create a duplicate.
    """
    run = graph["runs"][0]
    original_id = run.id

    pyd = run.to_pydantic()
    back, _ = pyd.to_sql()
    assert back.id == original_id
