import logging
import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import (
    ClientSubmissionSampleAssociation,
    Sample,
    ClientSubmission
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
def clientsubmissionsampleassociation(db):
    return ClientSubmissionSampleAssociation.query(limit=1)


def test_clientsubmissionsampleassociation_query(clientsubmissionsampleassociation):
    assert isinstance(clientsubmissionsampleassociation, ClientSubmissionSampleAssociation)


def test_clientsubmissionsampleassociation_get_name(clientsubmissionsampleassociation):
    assert clientsubmissionsampleassociation.name == "Test ClientSubmission->Test Sample (rank=0)"


def test_clientsubmissionsampleassociation_get_sample(clientsubmissionsampleassociation):
    assert isinstance(clientsubmissionsampleassociation.sample, Sample)
    assert clientsubmissionsampleassociation.sample.sample_id == "Test Sample"


def test_clientsubmissionsampleassociation_set_sample(clientsubmissionsampleassociation):
    test_insert = Sample(sample_id="Insert Sample")
    clientsubmissionsampleassociation.sample = test_insert
    assert clientsubmissionsampleassociation.sample == test_insert
    test_insert = dict(sample_id="Dict Sample")
    clientsubmissionsampleassociation.sample = test_insert
    assert clientsubmissionsampleassociation.sample.sample_id == "Dict Sample"


def test_clientsubmissionsampleassociation_get_clientsubmission(clientsubmissionsampleassociation):
    assert isinstance(clientsubmissionsampleassociation.clientsubmission, ClientSubmission)
    assert clientsubmissionsampleassociation.clientsubmission.submitter_plate_id == "Test ClientSubmission"


def test_clientsubmissionsampleassociation_set_clientsubmission(clientsubmissionsampleassociation):
    test_insert = ClientSubmission(submitter_plate_id="Insert ClientSubmission")
    clientsubmissionsampleassociation.clientsubmission = test_insert
    assert clientsubmissionsampleassociation.clientsubmission == test_insert
    test_insert = dict(submitter_plate_id="Dict ClientSubmission")
    clientsubmissionsampleassociation.clientsubmission = test_insert
    assert clientsubmissionsampleassociation.clientsubmission.submitter_plate_id == "Dict ClientSubmission"














