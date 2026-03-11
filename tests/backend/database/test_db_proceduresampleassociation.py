import logging
import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureSampleAssociation,
    Sample,
    Procedure,
    Results
)

logger = logging.getLogger(f"testing.{__name__}")


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
def proceduresampleassociation(db):
    return ProcedureSampleAssociation.query(limit=1)


def test_proceduresampleassociation_query(proceduresampleassociation):
    assert isinstance(proceduresampleassociation, ProcedureSampleAssociation)


def test_proceduresampleassociation_get_name(proceduresampleassociation):
    assert proceduresampleassociation.name == "Unknown Run-Unknown ProcedureType->Test Sample (rank=1)"


def test_proceduresampleassociation_get_sample(proceduresampleassociation):
    assert isinstance(proceduresampleassociation.sample, Sample)
    assert proceduresampleassociation.sample.sample_id == "Test Sample"


def test_proceduresampleassociation_set_sample(proceduresampleassociation):
    test_insert = Sample(sample_id="Insert Sample")
    proceduresampleassociation.sample = test_insert
    assert proceduresampleassociation.sample == test_insert
    test_insert = dict(sample_id="Dict Sample")
    proceduresampleassociation.sample = test_insert
    assert proceduresampleassociation.sample.sample_id == "Dict Sample"


def test_proceduresampleassociation_get_procedure(proceduresampleassociation):
    assert isinstance(proceduresampleassociation.procedure, Procedure)
    assert proceduresampleassociation.procedure.name == "Unknown Run-Unknown ProcedureType"


def test_proceduresampleassociation_set_procedure(proceduresampleassociation):
    
    test_insert = Procedure(name="Insert Procedure")
    proceduresampleassociation.procedure = test_insert
    assert proceduresampleassociation.procedure == test_insert
    test_insert = dict(name="Dict Procedure")
    proceduresampleassociation.procedure = test_insert
    assert proceduresampleassociation.procedure.name == "Dict Procedure"


def test_proceduresampleassociation_get_rank(proceduresampleassociation):
    assert proceduresampleassociation.procedure_rank == 1


def test_proceduresampleassociation_get_results(proceduresampleassociation):
    assert isinstance(proceduresampleassociation.results, list)
    assert isinstance(proceduresampleassociation.results[0], Results)
    assert proceduresampleassociation.results[0].resultstype == proceduresampleassociation.procedure.proceduretype.resultstype[0]


# TODO: Add test for setting results when that method is implemented.
    