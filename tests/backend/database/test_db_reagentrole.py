import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from custom_resources import DatabaseTestCase
from backend.db.models import ReagentRole, ProcedureType, Reagent

@pytest.fixture(scope="function")
def db():
    tc = DatabaseTestCase()
    tc.setUp()
    yield tc
    try:
        tc.tearDown()
    except Exception:
        pass

@pytest.fixture(scope="function")
def reagentrole(db):
    return ReagentRole.query(limit=1)

def test_query(reagentrole):
    assert isinstance(reagentrole, ReagentRole)

def test_get_proceduretype(reagentrole):
    pt = reagentrole.proceduretype
    try:
        assert isinstance(pt, _AssociationList)
    except AssertionError as e:
        print(f"Expected list, got {type(pt)}")
        raise e
    assert isinstance(pt[0], ProcedureType)

def set_proceduretype_objects_and_dicts(reagentrole):
    obj = ProcedureType(name="Insert ProcedureType")
    reagentrole.proceduretype = [obj]
    assert obj in reagentrole.proceduretype
    d = {"name": "Dict ProcedureType"}
    reagentrole.proceduretype = [d]
    assert "Dict ProcedureType" in [c.name for c in reagentrole.proceduretype]

def test_get_reagent(reagentrole):
    r = reagentrole.reagent
    try:
        assert isinstance(r, _AssociationList)
    except AssertionError as e:
        print(f"Expected list, got {type(r)}")
        raise e
    assert isinstance(r[0], Reagent)

def test_get_reagents(reagentrole):
    output = reagentrole.get_reagents()
    assert isinstance(output, list)