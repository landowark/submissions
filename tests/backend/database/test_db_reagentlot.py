import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from datetime import datetime, date, timedelta
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import ReagentRole, Reagent, ReagentLot, Procedure
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
def reagentlot(db):
    return ReagentLot.query(limit=1)


def test_reagentlot_query(reagentlot):
    assert isinstance(reagentlot, ReagentLot)


def test_reagentlot_get_reagent(reagentlot):
    assert isinstance(reagentlot.reagent, Reagent)
    assert reagentlot.reagent.name == "Test Solution"


def test_reagentlot_set_reagent(reagentlot):
    test_insert = Reagent(name="Insert Reagent")
    reagentlot.reagent = test_insert
    assert test_insert == reagentlot.reagent

    test_insert = dict(name="Dict Reagent")
    reagentlot.reagent = test_insert
    assert "Dict Reagent" == reagentlot.reagent.name


def test_reagentlot_get_procedure(reagentlot):
    assert isinstance(reagentlot.procedure, _AssociationList)
    assert isinstance(reagentlot.procedure[0], Procedure)
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert reagentlot.procedure[0].name == f"RSL-XX-20260202-1 - Test ProcedureType - {day} 00:00:00"


def test_reagentlot_set_procedure(reagentlot):
    test_insert = Procedure(name="Insert Procedure")
    reagentlot.procedure = [test_insert]
    assert test_insert in reagentlot.procedure

    # test_insert = dict(name="Dict Procedure")
    # reagentlot.procedure = [test_insert]
    # assert "Dict Procedure" in [item.name for item in reagentlot.procedure]


def test_reagentlot_get_expiry(reagentlot):
    assert isinstance(reagentlot.expiry, datetime)
    assert reagentlot.expiry == datetime.combine(date(year=2050, month=6, day=30), datetime.max.time()).replace(tzinfo=tz("America/Winnipeg"))


def test_reagentlot_set_expiry(reagentlot):
    test_insert = "2026-02-02"
    dt = datetime.combine(date(2026, 2, 2), datetime.max.time()).replace(tzinfo=tz("America/Winnipeg"))
    reagentlot.expiry = test_insert
    assert reagentlot.expiry == dt


def test_reagentlot_get_name(reagentlot):
    assert reagentlot.name == "Test Solution - 012345"
