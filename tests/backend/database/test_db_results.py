import pytest
from tests.resources.custom_resources import DatabaseTestCase
from tests.resources.toy_database import make_toy_db
from backend.db.models import ResultsType, Results, Procedure, ProcedureSampleAssociation, Sample
from datetime import datetime, date, time, timedelta
from pytz import timezone as tz


@pytest.fixture(scope="function")
def db():
    """Create a fresh toy DB for each test function so the in-memory
    sqlite DB is reset before every test.
    """
    db = make_toy_db(populate=True)
    yield db


@pytest.fixture(scope="function")
def results(db):
    return Results.query(limit=1)


def test_results_query(results):
    assert isinstance(results, Results)


def test_results_get_resultstype(results):
    assert isinstance(results.resultstype, ResultsType)


def test_results_set_resultstype(results):
    test_insert = ResultsType(name="Insert ResultsType")
    results.resultstype = test_insert
    assert test_insert == results.resultstype

    test_insert = dict(name="Dict ResultsType")
    results.resultstype = test_insert
    assert "Dict ResultsType" == results.resultstype.name


def test_results_get_procedure(results):
    assert isinstance(results.procedure, Procedure)


def test_results_set_procedure(results):
    test_insert = Procedure(name="Insert Procedure")
    results.procedure = test_insert
    assert test_insert == results.procedure


def test_results_get_name(results):
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert results.name == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00 - Test ResultsType"


def test_results_date_analyzed(results):
    assert isinstance(results.date_analyzed, datetime)
    dt = datetime.now().replace(tzinfo=tz("America/Winnipeg"))
    assert results.date_analyzed.date() == dt.date()
    assert results.date_analyzed.hour == dt.hour
    assert results.date_analyzed.minute == dt.minute


def test_results_set_date_analyzed(results):
    test_insert = "2026-02-02"
    dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0))
    results.date_analyzed = test_insert
    assert results.date_analyzed == dt


def test_results_get_sampleprocedureassociation(results):
    assert isinstance(results.sampleprocedureassociation, ProcedureSampleAssociation)


def test_results_set_sampleprocedureassociation(results):
    test_insert = ProcedureSampleAssociation(procedure=Procedure(name="Insert Procedure"), sample=Sample(sample_id="Insert Sample"))
    results.sampleprocedureassociation = test_insert
    assert test_insert == results.sampleprocedureassociation


def test_results_get_sample_id(results):
    assert results.sample_id == "Test Sample"

