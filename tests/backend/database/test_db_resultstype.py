import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import ProcedureType, ResultsType, Results


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
def resultstype(db):
    return ResultsType.query(limit=1)


def test_resultstype_query(resultstype):
    assert isinstance(resultstype, ResultsType)


def test_resultstype_get_proceduretype(resultstype):
    assert isinstance(resultstype.proceduretype, list)
    assert isinstance(resultstype.proceduretype[0], ProcedureType)


def test_resultstype_set_proceduretype(resultstype):
    test_insert = ProcedureType(name="Insert ProcedureType")
    resultstype.proceduretype = [test_insert]
    assert test_insert in resultstype.proceduretype

    test_insert = dict(name="Dict ProcedureType")
    resultstype.proceduretype = [test_insert]
    assert "Dict ProcedureType" in [item.name for item in resultstype.proceduretype]


def test_resultstype_get_results(resultstype):
    assert isinstance(resultstype.results, list)
    assert isinstance(resultstype.results[0], Results)


def test_resultstype_set_results(resultstype):
    test_insert = Results(result=dict(test="Insert Results", value=1234))
    resultstype.results = [test_insert]
    assert test_insert in resultstype.results