import logging
import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import (
    ClientSubmission,
    RunSampleAssociation,
    Sample,
    Run
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
def runsampleassociation(db):
    return RunSampleAssociation.query(limit=1)


def test_runsampleassociation_query(runsampleassociation):
    assert isinstance(runsampleassociation, RunSampleAssociation)


def test_runsampleassociation_get_name(runsampleassociation):
    assert runsampleassociation.name == "RSL-XX-20260202-1->Test Sample (rank=0)"


def test_runsampleassociation_get_sample(runsampleassociation):
    assert isinstance(runsampleassociation.sample, Sample)
    assert runsampleassociation.sample.sample_id == "Test Sample"


def test_runsampleassociation_set_sample(runsampleassociation):
    test_insert = Sample(sample_id="Insert Sample")
    runsampleassociation.sample = test_insert
    assert runsampleassociation.sample == test_insert
    test_insert = dict(sample_id="Dict Sample")
    runsampleassociation.sample = test_insert
    assert runsampleassociation.sample.sample_id == "Dict Sample"


def test_runsampleassociation_get_run(runsampleassociation):
    assert isinstance(runsampleassociation.run, Run)
    assert runsampleassociation.run.name == "RSL-XX-20260202-1"


def test_runsampleassociation_set_run(runsampleassociation):
    cl = ClientSubmission.query()[0]
    test_insert = Run(rsl_plate_number="Insert Run", clientsubmission=cl)
    runsampleassociation.run = test_insert
    assert runsampleassociation.run == test_insert
    test_insert = dict(rsl_plate_number="Dict Run", clientsubmission=cl)
    runsampleassociation.run = test_insert
    assert runsampleassociation.run.rsl_plate_number == "Dict Run"














