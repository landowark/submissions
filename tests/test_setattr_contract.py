"""
``BaseClass.__setattr__`` is load-bearing, so it gets its own tests.

Every attribute assignment on every model goes through this one method. It does
four different things depending on the key:

1. lets SQLAlchemy's own internal attributes through untouched,
2. routes unknown attributes into the ``_misc_info`` JSON catch-all,
3. calls ``fset`` directly for hybrid properties, because assigning through
   ``super().__setattr__`` would not always trigger the descriptor,
4. swallows failures from either of the last two and logs them.

Point 4 is why this file matters. A broken setter does not raise here; it logs
and moves on, so the object stays alive holding the wrong value. That has already
turned one bug (a tuple appended to a relationship) into silent data loss, and a
later attempt to improve the logging on this path introduced an
``UnboundLocalError`` that broke the ``_misc_info`` catch-all outright -- because
Python unbinds an ``except ... as e`` name at the end of the block, and the new
log statement referenced ``e`` from outside it.
"""
from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# Live bug, 2026-08-19.                                                        #
#                                                                              #
# backend/db/models/__init__.py:872 reads ``{e}`` in its log message, but ``e`` #
# was bound by the ``except AttributeError as e:`` on line 864 and Python       #
# unbinds that name at the end of the except block. Every trip through the      #
# _misc_info catch-all therefore raises UnboundLocalError, which takes the      #
# whole feature out.                                                           #
#                                                                              #
# Fix: drop ``{e}`` from the f-string on line 872 (the attribute name is        #
# already in the message), then delete this marker and the decorators below.    #
# strict=True means these turn red the moment the fix lands.                    #
# --------------------------------------------------------------------------- #
MISC_INFO_BROKEN = pytest.mark.xfail(
    strict=True,
    reason="backend/db/models/__init__.py:872 references 'e' outside the except "
           "block that bound it; the _misc_info catch-all raises UnboundLocalError.",
)


# @MISC_INFO_BROKEN
def test_unknown_attribute_lands_in_misc_info(graph, db):
    """
    Assigning an attribute the model does not declare stores it in ``_misc_info``.

    This is the documented behavior of the branch at
    ``backend/db/models/__init__.py:869``, and it is a normal path -- the Excel
    parsers rely on it to carry columns the schema has no home for.
    """
    submission = graph["submissions"][0]
    submission.some_unmapped_field = "carried through"
    assert submission._misc_info.get("some_unmapped_field") == "carried through"


# @MISC_INFO_BROKEN
def test_unknown_attribute_readable_after_commit(graph, db):
    """What went into ``_misc_info`` has to survive a round trip."""
    submission = graph["submissions"][0]
    submission.another_unmapped_field = {"nested": [1, 2, 3]}
    db.commit()
    db.expire(submission)
    assert submission._misc_info.get("another_unmapped_field") == {"nested": [1, 2, 3]}


# @MISC_INFO_BROKEN
def test_unknown_attribute_on_a_fresh_instance(db):
    """
    The catch-all also has to work before the row has ever been flushed, when
    ``_misc_info`` is still unset.
    """
    from backend.db.models import ClientLab

    lab = ClientLab(name="Misc Lab")
    lab.unmapped_on_new_object = "value"
    db.add(lab)
    db.commit()
    assert lab._misc_info.get("unmapped_on_new_object") == "value"


# @MISC_INFO_BROKEN
def test_unknown_attribute_is_coerced_to_something_serializable(graph, db):
    """
    ``_misc_info`` is a JSON column, so values are sanitized on the way in. A
    value that cannot be coerced is dropped rather than corrupting the row.
    """
    from json import dumps

    submission = graph["submissions"][0]
    submission.a_date_field = graph["submissions"][0].submitted_date
    db.commit()
    dumps(submission._misc_info)          # must not raise


def test_hybrid_property_setter_is_invoked(graph):
    """
    Assigning to a hybrid property must run its ``fset``, not just bind an
    instance attribute that shadows the descriptor.
    """
    run = graph["runs"][0]
    run.signed_by = "someone"
    assert run._signed_by == "someone", "the setter did not write the backing column"
    assert "signed_by" not in run.__dict__, "the descriptor was shadowed"


def test_internal_sqlalchemy_attributes_pass_through(graph):
    """
    SQLAlchemy stores per-instance bookkeeping under generated names such as
    ``_AssociationProxy_<rel>_<id>``. Those must reach ``object.__setattr__``
    untouched -- routing them into ``_misc_info`` would both corrupt the JSON
    column and break the ORM.
    """
    submission = graph["submissions"][0]
    before = dict(submission._misc_info or {})
    key = "_AssociationProxy_test_1234567890"
    setattr(submission, key, object())
    assert key not in (submission._misc_info or {}), (
        "an internal SQLAlchemy attribute was captured into _misc_info"
    )
    assert dict(submission._misc_info or {}) == before


# @MISC_INFO_BROKEN
def test_setting_many_unknown_attributes_accumulates(graph, db):
    """Each unknown key is added, not overwriting the ones before it."""
    submission = graph["submissions"][0]
    for i in range(5):
        setattr(submission, f"extra_field_{i}", i)
    db.commit()
    for i in range(5):
        assert submission._misc_info.get(f"extra_field_{i}") == i


# @MISC_INFO_BROKEN
def test_assignment_never_raises_for_ordinary_values(graph):
    """
    The catch-all path has to be exception-free for plain data.

    A regression here is invisible in normal use until a parser hits an unmapped
    column, at which point the whole import fails.
    """
    submission = graph["submissions"][0]
    failures = []
    for name, value in [
        ("str_field", "text"),
        ("int_field", 7),
        ("float_field", 1.5),
        ("bool_field", True),
        ("none_field", None),
        ("list_field", [1, 2]),
        ("dict_field", {"k": "v"}),
    ]:
        try:
            setattr(submission, name, value)
        except Exception as exc:
            failures.append(f"{name}={value!r}: {type(exc).__name__}: {exc}")
    assert not failures, "assignment raised on ordinary values:\n  " + "\n  ".join(failures)
