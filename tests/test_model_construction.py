"""
Construct every model through its real ``__init__``.

The ``seed`` fixture writes columns with Core inserts precisely so that fixture
setup never depends on constructor behavior. That makes the query tests robust,
but it also means nothing else in the suite exercises the constructors -- and this
codebase puts a lot of behavior in them: kwargs are popped and re-dispatched
through hybrid-property setters, strings are resolved into related rows, and some
setters reach back into the database for rows that may not exist yet.

Two failures this file is designed to catch, both of which happened:

* ``ResultsType.__init__`` defaulted ``saved_settings`` to ``[]`` while its setter
  accepted only ``dict``, so a bare ``ResultsType(name=...)`` always raised.
* ``ProcedureType``'s ``submissiontype`` setter unconditionally appends a row
  named ``"Default SubmissionType"``. When that row was missing it appended
  ``None``; when the lookup was switched to ``query_or_create`` it appended the
  ``(instance, is_new)`` tuple. Both broke the assignment, and the second did so
  silently.
"""
from __future__ import annotations

import pytest

DEFAULT_SUBMISSIONTYPE = "Default SubmissionType"


# --------------------------------------------------------------------------- #
# Catalog models: constructible with nothing but a name, in an empty database.  #
# --------------------------------------------------------------------------- #
CATALOG_MODELS = [
    ("ClientLab", dict(name="Test Lab")),
    ("Contact", dict(name="Test Contact", email="test@example.com", tel="555")),
    ("ReagentRole", dict(name="Test Role")),
    ("Reagent", dict(name="Test Reagent", manufacturer="TestCo")),
    ("EquipmentRole", dict(name="Test Equipment Role")),
    ("Equipment", dict(name="Test Equipment", asset_number="A-1")),
    ("Process", dict(name="Test Process")),
    ("SubmissionType", dict(name="Test Submission Type")),
    ("Tips", dict(name="Test Tips", ref="T-9", manufacturer="TipCo", capacity=200)),
]


@pytest.mark.parametrize("model_name,kwargs", CATALOG_MODELS, ids=[m for m, _ in CATALOG_MODELS])
def test_catalog_model_constructs_in_empty_database(db, model_name, kwargs):
    """
    Each catalog model must be creatable in a database with nothing in it.

    Bootstrapping a fresh install goes through exactly this path, so a constructor
    that depends on a row already existing makes the application impossible to set
    up from scratch.
    """
    import backend.db.models as M

    cls = getattr(M, model_name)
    instance = cls(**kwargs)
    db.add(instance)
    db.commit()
    assert instance.id is not None


def test_resultstype_constructs_without_saved_settings(db):
    """
    ``ResultsType(name=...)`` with no ``saved_settings`` must work.

    The constructor's default and the setter's accepted type have to agree; when
    they did not, every bare construction raised ``ValueError``.
    """
    from backend.db.models import ResultsType

    rt = ResultsType(name="Test Results Type")
    db.add(rt)
    db.commit()
    assert rt.id is not None


def test_resultstype_saved_settings_round_trips_a_dict(db):
    from backend.db.models import ResultsType

    rt = ResultsType(name="Kraken-ish", saved_settings={"projects": {"a": 1}})
    db.add(rt)
    db.commit()
    assert rt.saved_settings == {"projects": {"a": 1}}


def test_resultstype_saved_settings_getter_returns_a_mapping(db):
    """
    The empty case must not change type on the caller.

    The getter previously returned ``[]`` when unset and a ``dict`` otherwise, so
    ``results_type.saved_settings['projects']`` raised ``TypeError`` on a fresh
    row instead of ``KeyError`` -- and ``KrakenViewer`` reads exactly that key.
    """
    from backend.db.models import ResultsType

    rt = ResultsType(name="Empty Settings")
    db.add(rt)
    db.commit()
    assert isinstance(rt.saved_settings, dict)


def test_resultstype_saved_settings_rejects_non_mapping(db):
    """
    A non-mapping is refused, but quietly.

    The setter raises ``ValueError``; ``BaseClass.__setattr__`` catches it
    (backend/db/models/__init__.py:901-905), logs, and restores the previous
    value. So the bad value never lands, the object stays usable, and the caller
    is not told. This test pins that behavior rather than endorsing it -- if the
    swallow is ever removed, this fails and points at the decision.
    """
    from backend.db.models import ResultsType

    rt = ResultsType(name="Bad Settings", saved_settings=["not", "a", "dict"])
    assert isinstance(rt.saved_settings, dict), "a list must not be stored"
    assert rt.saved_settings == {}

    rt.saved_settings = ["still", "bad"]
    assert rt.saved_settings == {}, "a rejected assignment must leave the old value"


# --------------------------------------------------------------------------- #
# ProcedureType: the model with the most constructor machinery.                 #
# --------------------------------------------------------------------------- #
def test_proceduretype_constructs_in_empty_database(db):
    """
    With no ``Default SubmissionType`` row present, construction must still work.

    The setter creates the row on demand; if it ever goes back to a plain lookup,
    this fails at flush with "Can't flush None value found in collection".
    """
    from backend.db.models import ProcedureType

    pt = ProcedureType(name="Bootstrap Procedure")
    db.add(pt)
    db.commit()
    assert pt.id is not None


def test_proceduretype_attaches_only_model_instances(db):
    """
    Every member of the relationship must be a mapped object.

    This is the check that catches the ``query_or_create`` tuple: a ``(instance,
    is_new)`` pair in the list makes SQLAlchemy raise ``AttributeError`` deep in
    ``__setattr__``, where it was being swallowed and logged.
    """
    from backend.db.models import ProcedureType, SubmissionType

    pt = ProcedureType(name="Typed Procedure")
    db.add(pt)
    db.commit()

    for attached in pt.submissiontype:
        assert isinstance(attached, SubmissionType), (
            f"expected SubmissionType instances, found {type(attached).__name__}: "
            f"{attached!r}"
        )


def test_proceduretype_gets_the_default_submissiontype(db):
    """The default must actually be attached, not merely attempted."""
    from backend.db.models import ProcedureType

    pt = ProcedureType(name="Defaulted Procedure")
    db.add(pt)
    db.commit()
    names = [st.name for st in pt.submissiontype]
    assert DEFAULT_SUBMISSIONTYPE in names, (
        f"the default submission type was not attached; got {names}"
    )


def test_proceduretype_keeps_explicit_submissiontypes(db):
    """Passing a submission type must not cost you the default, or vice versa."""
    from backend.db.models import ProcedureType, SubmissionType

    db.add(SubmissionType(name="Wastewater"))
    db.commit()

    pt = ProcedureType(name="Explicit Procedure", submissiontype=["Wastewater"])
    db.add(pt)
    db.commit()

    names = sorted(st.name for st in pt.submissiontype)
    assert names == sorted(["Wastewater", DEFAULT_SUBMISSIONTYPE])


def test_default_submissiontype_links_back_to_its_procedures(db):
    """
    The reverse side of the relationship has to be populated too.

    ``PydSubmissionType.validate_proceduretype`` treats the default as the bucket
    holding every procedure type, so an empty reverse collection quietly changes
    what the submission-type form offers.
    """
    from backend.db.models import ProcedureType, SubmissionType

    for name in ("Alpha Procedure", "Beta Procedure"):
        db.add(ProcedureType(name=name))
        db.commit()          # see test_two_proceduretypes_in_one_transaction

    default = SubmissionType.query(name=DEFAULT_SUBMISSIONTYPE, limit=1)
    assert default is not None, "the default submission type row was never created"
    linked = sorted(pt.name for pt in default.proceduretype)
    assert linked == ["Alpha Procedure", "Beta Procedure"]


# --------------------------------------------------------------------------- #
# query_or_create's contract, which several constructors depend on.            #
# --------------------------------------------------------------------------- #
def test_query_or_create_returns_instance_and_flag(db):
    """
    ``query_or_create`` returns a ``(instance, is_new)`` tuple.

    Roughly thirty call sites unwrap it; one that forgot silently emptied a
    relationship. Pinning the contract here makes the shape explicit rather than
    something each caller has to remember.
    """
    from backend.db.models import ClientLab

    first, created = ClientLab.query_or_create(name="Tuple Lab")
    assert isinstance(first, ClientLab)
    assert created is True

    db.add(first)
    db.commit()

    again, created_again = ClientLab.query_or_create(name="Tuple Lab")
    assert again.id == first.id
    assert created_again is False


@pytest.mark.xfail(
    strict=True,
    reason="Creating two ProcedureTypes in one transaction inserts two "
           "'Default SubmissionType' rows and violates the unique constraint. "
           "ProcedureType.submissiontype's setter calls "
           "SubmissionType.query_or_create, which builds the new row with cls() "
           "but never session.add()s it -- so it is not pending, autoflush has "
           "nothing to write, and the next construction's lookup misses it too. "
           "Only bites when the default row does not already exist, i.e. when "
           "bootstrapping a fresh database. Delete this xfail when fixed.",
)
def test_two_proceduretypes_in_one_transaction(db):
    """Bootstrapping several procedure types at once must not duplicate the default."""
    from backend.db.models import ProcedureType, SubmissionType

    for name in ("Alpha Procedure", "Beta Procedure"):
        db.add(ProcedureType(name=name))
    db.commit()

    defaults = db.query(SubmissionType).filter(
        SubmissionType.name == DEFAULT_SUBMISSIONTYPE).all()
    assert len(defaults) == 1
