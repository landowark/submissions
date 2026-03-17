from datetime import date, timedelta
import logging
import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureEquipmentTipslotAssociation,
    EquipmentRole,
    Equipment,
    Process,
    Tips,
    TipsLot
)

logger = logging.getLogger(f"testing.{__name__}")


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
def procedureequipmenttipslotassociation(db):
    return ProcedureEquipmentTipslotAssociation.query(limit=1)


def test_procedureequipmenttipslotassociation_query(procedureequipmenttipslotassociation):
    assert isinstance(procedureequipmenttipslotassociation, ProcedureEquipmentTipslotAssociation)


def test_procedureequipmenttipslotassociation_get_name(procedureequipmenttipslotassociation):
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert procedureequipmenttipslotassociation.name == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00(Test EquipmentRole)->ACME Tips - XXXX - 098765"


def test_procedureequipmenttipslotassociation_get_tipslot(procedureequipmenttipslotassociation):
    
    assert isinstance(procedureequipmenttipslotassociation.tipslot, TipsLot)
    assert procedureequipmenttipslotassociation.tipslot.name == "ACME Tips - XXXX - 098765"


def test_procedureequipmenttipslotassociation_set_equipment(procedureequipmenttipslotassociation):
    tips = Tips.query(limit=1)
    test_insert = TipsLot(lot="Insert Lot", tips=tips)
    procedureequipmenttipslotassociation.tipslot = test_insert
    assert test_insert == procedureequipmenttipslotassociation.tipslot

    test_insert = dict(lot="Dict Lot", tips=tips)
    procedureequipmenttipslotassociation.tipslot = test_insert
    assert "ACME Tips - XXXX - Dict Lot" == procedureequipmenttipslotassociation.tipslot.name


