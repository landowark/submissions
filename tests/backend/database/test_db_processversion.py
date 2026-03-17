import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import Process, ProcessVersion


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
def processversion(db):
    return ProcessVersion.query(limit=1)


def test_processversion_query(processversion):
    assert isinstance(processversion, ProcessVersion)


def test_processversion_get_process(processversion):
    assert isinstance(processversion.process, Process)


def test_processversion_set_process(processversion):
    test_insert = Process(name="Insert Process")
    processversion.process = test_insert
    assert test_insert == processversion.process

    test_insert = dict(name="Dict Process")
    processversion.process = test_insert
    assert "Dict Process" == processversion.process.name


def test_processversion_get_name(processversion):
    assert processversion.name == "Test Process - v1.0"


def test_processversion_set_active(processversion):
    processversion.active = 0
    assert not processversion.active
    processversion.active = "on"
    assert processversion.active
