from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from sqlalchemy.orm.collections import InstrumentedList
from custom_resources import DatabaseTestCase
from backend.db.models import (ClientSubmission, Sample, ReagentRole, 
                               ResultsType, SubmissionType, Procedure, Run,
                               Contact, ClientLab, ClientSubmissionSampleAssociation)
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


# ClientSubmission
@pytest.fixture(scope="function")
def clientsubmission(db):
    return ClientSubmission.query(limit=1)


def test_clientsubmission_query(clientsubmission):
    assert isinstance(clientsubmission, ClientSubmission)


def test_clientsubmission_get_clientlab(clientsubmission):
    assert isinstance(clientsubmission.clientlab, ClientLab)
    # assert isinstance(clientsubmission.clientlab[0], EquipmentRole)
    assert clientsubmission.clientlab.name == "Test Lab"


def test_clientsubmission_set_clientlab(clientsubmission):
    test_insert = ClientLab(name="Insert ClientLab")
    clientsubmission.clientlab = test_insert
    assert test_insert == clientsubmission.clientlab
    test_insert = dict(name="Dict ClientLab")
    clientsubmission.clientlab = test_insert
    assert "Dict ClientLab" == clientsubmission.clientlab.name


def test_clientsubmission_get_submission_category(clientsubmission):
    assert clientsubmission.submission_category == "Test Category"


def test_clientsubmission_get_contact(clientsubmission):
    assert isinstance(clientsubmission.contact, Contact)
    assert clientsubmission.contact.name == "Johnny Test"


def test_clientsubmission_set_contact(clientsubmission):
    test_insert = Contact(name="Insert Contact")
    clientsubmission.contact = test_insert
    assert test_insert == clientsubmission.contact
    test_insert = dict(name="Dict Contact")
    clientsubmission.contact = test_insert
    assert "Dict Contact" == clientsubmission.contact.name


def test_clientsubmission_get_run(clientsubmission):
    assert isinstance(clientsubmission.run, InstrumentedList)
    assert isinstance(clientsubmission.run[0], Run)


def test_clientsubmission_set_run(clientsubmission):
    test_insert = Run(rsl_plate_number="Insert Run")
    clientsubmission.run = test_insert
    assert test_insert in clientsubmission.run
    test_insert = dict(rsl_plate_number="Dict Run")
    clientsubmission.run = test_insert
    assert "Dict Run" in [run.rsl_plate_number for run in clientsubmission.run]


def test_clientsubmission_get_submissiontype(clientsubmission):
    assert isinstance(clientsubmission.submissiontype, SubmissionType)
    assert clientsubmission.submissiontype_name == "Default SubmissionType"


def test_clientsubmission_set_submissiontype(clientsubmission):
    test_insert = SubmissionType(name="Insert SubmissionType")
    clientsubmission.submissiontype = test_insert
    assert test_insert == clientsubmission.submissiontype
    test_insert = dict(name="Dict SubmissionType")
    clientsubmission.submissiontype = test_insert
    assert "Dict SubmissionType" == clientsubmission.submissiontype.name


def test_clientsubmission_get_clientsubmissionsampleassociation(clientsubmission):
    assert isinstance(clientsubmission.clientsubmissionsampleassociation, InstrumentedList)
    assert isinstance(clientsubmission.clientsubmissionsampleassociation[0], ClientSubmissionSampleAssociation)


def test_clientsubmission_get_sample(clientsubmission):
    assert isinstance(clientsubmission.sample, _AssociationList)
    assert isinstance(clientsubmission.sample[0], Sample)


def test_clientsubmission_set_sample(clientsubmission):
    test_insert = Sample(sample_id="Insert Sample")
    clientsubmission.sample = test_insert
    assert test_insert in clientsubmission.sample
    test_insert = dict(sample_id="Dict Sample")
    clientsubmission.sample = test_insert
    assert "Dict Sample"in [sample.sample_id for sample in clientsubmission.sample]


def test_clientsubmission_get_submitted_date(clientsubmission):
    assert clientsubmission.submitted_date == datetime.combine((datetime.today() - timedelta(days=1)), datetime.min.time()).replace(tzinfo=tz("America/Winnipeg"))


def test_clientsubmission_set_submitted_date(clientsubmission):
    clientsubmission.submitted_date = "2026-02-26"
    assert isinstance(clientsubmission.submitted_date, datetime)
    clientsubmission.submitted_date = 1772085600
    assert isinstance(clientsubmission.submitted_date, datetime)


def test_clientsubmission_get_name(clientsubmission):
    assert clientsubmission.name == clientsubmission.submitter_plate_id


def test_clientsubmission_get_sample_count(clientsubmission):
    assert clientsubmission.sample_count == 1


def test_clientsubmission_get_max_sample_rank(clientsubmission):
    assert clientsubmission.max_sample_rank == 0
    clientsubmission.clientsubmissionsampleassociation[0].submission_rank = 2
    assert clientsubmission.max_sample_rank == 2


def test_clientsubmission_get_custom_context_events(clientsubmission):
    assert ["Add Run", "Edit", "Add Comment", "Show Details", "Delete"] == list(clientsubmission.custom_context_events.keys())
    assert all([callable(obj) for obj in clientsubmission.custom_context_events.values()])

