import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import Contact, ClientSubmission, ClientLab

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
def contact(db):
    return Contact.query(limit=1)

def test_contact_query(contact):
    assert isinstance(contact, Contact)

def test_contact_get_clientsubmission(contact):
    cs = contact.clientsubmission
    assert isinstance(cs, list)
    assert isinstance(cs[0], ClientSubmission)

def test_contact_set_clientsubmission_objects_and_dicts(contact):
    obj = ClientSubmission(submitter_plate_id="Insert Submission")
    contact.clientsubmission = [obj]
    assert obj in contact.clientsubmission
    d = {"submitter_plate_id": "Dict Submission"}
    contact.clientsubmission = [d]
    assert "Dict Submission" in [c.submitter_plate_id for c in contact.clientsubmission]

def test_contact_get_clientlab(contact):
    cls = contact.clientlab
    assert isinstance(cls, list)
    assert isinstance(cls[0], ClientLab)

def test_contact_set_clientlab_objects_and_dicts(contact):
    obj = ClientLab(name="Insert ClientLab")
    contact.clientlab = [obj]
    assert obj in contact.clientlab
    d = {"name": "Dict ClientLab"}
    contact.clientlab = [d]
    assert "Dict ClientLab" in [c.name for c in contact.clientlab]