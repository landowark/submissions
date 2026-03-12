from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from sqlalchemy.orm.collections import InstrumentedList
from custom_resources import DatabaseTestCase
from backend.db.models import (Run, Sample, ReagentRole, 
                               ResultsType, SubmissionType, Procedure, Run,
                               Contact, ClientSubmission, RunSampleAssociation)
from backend.validators.pydant import PydProcedure
from pytz import timezone as tz


@pytest.fixture(scope="function")
def db():
    tc = DatabaseTestCase()
    tc.setUp()
    yield tc
    try:
        tc.tearDown()
    except Exception:
        pass


# Run
@pytest.fixture(scope="function")
def run(db):
    return Run.query(limit=1)


def test_run_query(run):
    assert isinstance(run, Run)


def test_run_get_clientsubmission(run):
    assert isinstance(run.clientsubmission, ClientSubmission)
    # assert isinstance(run.clientsubmission[0], EquipmentRole)
    assert run.clientsubmission.name == "Test ClientSubmission"


def test_run_set_clientsubmission(run):
    test_insert = ClientSubmission(submitter_plate_id="Insert ClientSubmission")
    run.clientsubmission = test_insert
    assert test_insert == run.clientsubmission
    test_insert = dict(submitter_plate_id="Dict ClientSubmission")
    run.clientsubmission = test_insert
    assert "Dict ClientSubmission" == run.clientsubmission.name


def test_run_get_rsl_plate_number(run):
    assert run.rsl_plate_number == "RSL-XX-20260202-1"


def test_run_set_rsl_plate_number(run):
    run.rsl_plate_number = dict(value="Bob")
    assert run.rsl_plate_number == "Bob"


def test_run_get_procedure(run):
    assert isinstance(run.procedure, InstrumentedList)
    assert isinstance(run.procedure[0], Procedure)


def test_run_set_procedure(run):
    test_insert = Procedure(name="Insert Procedure")
    run.procedure = test_insert
    assert test_insert in run.procedure
    # test_insert = dict(name="Dict Procedure")
    # run.procedure = test_insert
    # assert "Dict Procedure" in [pro.name for pro in run.procedure]


def test_run_get_sample(run):
    assert isinstance(run.sample, _AssociationList)
    assert isinstance(run.sample[0], Sample)


def test_run_set_sample(run):
    test_insert = Sample(sample_id="Insert Sample")
    run.sample = test_insert
    assert test_insert in run.sample
    new_sample = Sample(sample_id="Dict Sample")
    new_sample.save()
    test_insert = dict(sample_id="Dict Sample")
    run.sample = test_insert
    assert "Dict Sample" in [samp.sample_id for samp in run.sample]


def test_run_get_started_date(run):
    assert isinstance(run.started_date, datetime)
    assert run.started_date == datetime.combine(date.today() - timedelta(days=1), datetime.min.time()).replace(tzinfo=tz("America/Winnipeg")) 


def test_run_set_started_date(run):
    run.started_date = "2026-02-26"
    assert isinstance(run.started_date, datetime)
    run.started_date = 1772085600
    assert isinstance(run.started_date, datetime)


def test_run_get_completed_date(run):
    assert run.completed_date is None
    run.signed_by = "Bob"
    assert isinstance(run.completed_date, datetime)
    assert run.completed_date == datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=tz("America/Winnipeg"))


def test_run_set_completed_date(run):
    run.completed_date = "2026-02-26"
    assert run.completed_date is None
    run.signed_by = "Bob"
    assert isinstance(run.completed_date, datetime)
    run.completed_date = 1772085600
    assert isinstance(run.completed_date, datetime)


def test_run_get_name(run):
    assert run.name == run.rsl_plate_number


def test_run_get_submission_type(run):
    assert isinstance(run.get_submission_type("Default SubmissionType"), SubmissionType)


def test_run_get_default_info(run):
    assert list(run.get_default_info(submissiontype="Default SubmissionType").keys()) == \
        ['singles', 'details_ignore', 'form_ignore', 'form_recover', 'submissiontype']


def test_run_get_sample_count(run):
    assert run.sample_count == 1


def test_run_get_custom_context_events(run):
    assert ["Add Procedure", "Edit", "Export", "Add Comment", "Show Details", "Delete"] == list(run.custom_context_events.keys())
    assert all([callable(obj) for obj in run.custom_context_events.values()])
