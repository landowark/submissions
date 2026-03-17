import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import ClientLab, Contact, ClientSubmission

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
def clientlab(db):
    return ClientLab.query(limit=1)

def test_clientlab_query(clientlab):
    assert isinstance(clientlab, ClientLab)

def test_clientlab_get_clientsubmission(clientlab):
    cs = clientlab.clientsubmission
    assert isinstance(cs, list)
    assert isinstance(cs[0], ClientSubmission)

def test_clientlab_set_clientsubmission_objects_and_dicts(clientlab):
    obj = ClientSubmission(submitter_plate_id="Insert Submission")
    clientlab.clientsubmission = [obj]
    assert obj in clientlab.clientsubmission

    d = {"submitter_plate_id": "Dict Submission"}
    clientlab.clientsubmission = [d]
    assert "Dict Submission" in [item.submitter_plate_id for item in clientlab.clientsubmission]

def test_clientlab_get_contact(clientlab):
    contacts = clientlab.contact
    assert isinstance(contacts, list)
    assert isinstance(contacts[0], Contact)

def test_clientlab_set_contact_objects_and_dicts(clientlab):
    obj = Contact(name="Insert Contactington")
    clientlab.contact = [obj]
    assert obj in clientlab.contact
    d = {"name": "Dict Contactington"}
    clientlab.contact = [d]
    assert "Dict Contactington" in [c.name for c in clientlab.contact]

