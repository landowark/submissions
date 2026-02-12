import pytest
from sqlalchemy.orm.collections import InstrumentedList
from custom_resources import DatabaseTestCase
from backend.db.models import TipsLot, ProcedureEquipmentTipslotAssociation, Procedure, Equipment
from datetime import datetime, date, time
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


@pytest.fixture(scope="function")
def tipslot(db):
    return TipsLot.query(limit=1)


def test_tipslot_query(tipslot):
    assert isinstance(tipslot, TipsLot)


def test_tipslot_get_expiry(tipslot):
    assert isinstance(tipslot.expiry, datetime)
    expected = datetime.combine(
        date(year=date.today().year + 1, month=date.today().month, day=date.today().day),
        datetime.max.time(),
    ).replace(tzinfo=tz("America/Winnipeg"))
    assert tipslot.expiry == expected


def test_tipslot_set_expiry(tipslot):
    test_insert = "2026-02-02"
    dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
    tipslot.expiry = test_insert
    assert tipslot.expiry == dt


def test_tipslot_get_procedureequipmenttipslotassociation(tipslot):
    assert isinstance(tipslot.procedureequipmenttipslotassociation, InstrumentedList)
    assert isinstance(tipslot.procedureequipmenttipslotassociation[0], ProcedureEquipmentTipslotAssociation)


def test_tipslot_set_procedureequipmenttipslotassociation(tipslot):
    test_insert = ProcedureEquipmentTipslotAssociation(procedure=Procedure(name="Insert Procedure"), equipment=Equipment(name="Insert Equipment"), tipslot=tipslot)
    tipslot.procedureequipmenttipslotassociation = [test_insert]
    assert test_insert in tipslot.procedureequipmenttipslotassociation


def test_tipslot_get_capacity_and_name(tipslot):
    assert tipslot.capacity == "1000uL"
    assert tipslot.name == "ACME Tips - XXXX - 098765"


def test_tipslot_set_active(tipslot):
    tipslot.active = 0
    assert not tipslot.active
    tipslot.active = "on"
    assert tipslot.active


def test_tips_get_name(tipslot):
    assert tipslot.tips.name == "ACME Tips-XXXX(1000)"