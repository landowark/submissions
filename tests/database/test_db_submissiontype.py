import pytest
from datetime import timedelta
from custom_resources import DatabaseTestCase
from backend.db.models import SubmissionType, ClientSubmission, ProcedureType


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
def submissiontype(db):
    return SubmissionType.query(limit=1)


def test_submissiontype_query(submissiontype):
    assert isinstance(submissiontype, SubmissionType)


def test_submissiontype_file_name_template(submissiontype):
    assert (
        submissiontype.file_name_template
        == "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
    )


def test_submissiontype_get_clientsubmission(submissiontype):
    assert isinstance(submissiontype.clientsubmission, list)
    assert isinstance(submissiontype.clientsubmission[0], ClientSubmission)


def test_submissiontype_set_clientsubmission(submissiontype):
    test_insert = ClientSubmission(name="Insert ClientSubmission")
    submissiontype.clientsubmission = [test_insert]
    assert test_insert in submissiontype.clientsubmission

    test_insert = dict(submitter_plate_id="Dict ClientSubmission")
    submissiontype.clientsubmission = [test_insert]
    assert "Dict ClientSubmission" in [item.submitter_plate_id for item in submissiontype.clientsubmission]


def test_submissiontype_get_proceduretype(submissiontype):
    assert isinstance(submissiontype.proceduretype, list)
    assert isinstance(submissiontype.proceduretype[0], ProcedureType)


def test_submissiontype_set_proceduretype(submissiontype):
    test_insert = ProcedureType(name="Insert ProcedureType")
    submissiontype.proceduretype = [test_insert]
    assert test_insert in submissiontype.proceduretype

    test_insert = dict(name="Dict ProcedureType")
    submissiontype.proceduretype = [test_insert]
    assert "Dict ProcedureType" in [item.name for item in submissiontype.proceduretype]


def test_submissiontype_turnaround_time(submissiontype):
    assert submissiontype.turnaround_time == timedelta(days=5)


def test_submissiontype_set_turnaround_time(submissiontype):
    submissiontype.turnaround_time = 3
    assert submissiontype.turnaround_time == timedelta(days=3)
    submissiontype.turnaround_time = "4"
    assert submissiontype.turnaround_time == timedelta(days=4)
    submissiontype.turnaround_time = None
    assert submissiontype.turnaround_time == timedelta(days=5)


def test_submissiontype_abbreviation(submissiontype):
    assert submissiontype.abbreviation == "XX"
    submissiontype.abbreviation = "XXXX"
    assert submissiontype.abbreviation == "XXXX"
    submissiontype.abbreviation = "XXXXenomorph"
    assert submissiontype.abbreviation == "XXXX"
    submissiontype.abbreviation = 1234
    assert submissiontype.abbreviation == "1234"
