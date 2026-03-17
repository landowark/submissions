import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from tools import tz
from datetime import datetime, date
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import ReagentRole, Reagent, ReagentLot


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
def reagent(db):
    return Reagent.query(limit=1)


def test_reagent_query(reagent):
    assert isinstance(reagent, Reagent)


def test_reagent_get_reagentrole(reagent):
    assert isinstance(reagent.reagentrole, _AssociationList)
    assert isinstance(reagent.reagentrole[0], ReagentRole)


def test_reagent_set_reagentrole(reagent):
    test_insert = ReagentRole(name="Insert ReagentRole")
    reagent.reagentrole = [test_insert]
    assert test_insert in reagent.reagentrole

    test_insert = dict(name="Dict ReagentRole")
    reagent.reagentrole = [test_insert]
    assert "Dict ReagentRole" in [item.name for item in reagent.reagentrole]


def test_reagent_get_reagentlot(reagent):
    assert isinstance(reagent.reagentlot, list)
    assert isinstance(reagent.reagentlot[0], ReagentLot)


def test_reagent_set_reagentlot(reagent):
    test_insert = ReagentLot(name="Insert ReagentLot")
    reagent.reagentlot = [test_insert]
    assert test_insert in reagent.reagentlot

    test_insert = dict(lot="Dict ReagentLot")
    reagent.reagentlot = [test_insert]
    assert "Test Solution - Dict ReagentLot" in [item.name for item in reagent.reagentlot]


def test_reagent_lot_dicts(reagent):
    dt = datetime.combine(
        date(year=date.today().year + 1, month=date.today().month, day=date.today().day),
        datetime.max.time(),
    ).replace(tzinfo=tz("America/Winnipeg"))

    try:
        expected_expiry = (dt + reagent.eol_ext)
    except Exception:
        try:
            expected_expiry = dt + reagent.eol_ext
        except Exception:
            expected_expiry = dt

    simplified_expected = {"name": "Test Solution", "lot": "012345", "expiry": expected_expiry}
    assert simplified_expected in reagent.lot_dicts
