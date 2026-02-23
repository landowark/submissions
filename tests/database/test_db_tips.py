import pytest
from sqlalchemy.orm.collections import InstrumentedList
from custom_resources import DatabaseTestCase
from backend.db.models import Process, Tips


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
def tips(db):
    return Tips.query(limit=1)


def test_tips_query(tips):
    assert isinstance(tips, Tips)


def test_tips_get_name(tips):
    assert tips.name == "ACME Tips - XXXX(1000uL)"


def test_tips_get_process(tips):
    assert isinstance(tips.process, InstrumentedList)
    assert isinstance(tips.process[0], Process)


def test_tips_set_process(tips):
    test_insert = Process(name="Insert Process")
    tips.process = [test_insert]
    assert test_insert in tips.process

    test_insert = dict(name="Dict Process")
    tips.process = [test_insert]
    assert "Dict Process" in [item.name for item in tips.process]
