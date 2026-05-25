import logging
import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import (
    EquipmentRoleEquipmentAssociation,
    EquipmentRole,
    Equipment,
    ProcessVersion,
    Process
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
def equipmentroleequipmentassociation(db):
    return EquipmentRoleEquipmentAssociation.query(limit=1)


def test_equipmentroleequipmentassociation_query(equipmentroleequipmentassociation):
    assert isinstance(equipmentroleequipmentassociation, EquipmentRoleEquipmentAssociation)


def test_equipmentroleequipmentassociation_get_name(equipmentroleequipmentassociation):
    assert equipmentroleequipmentassociation.name == "Test EquipmentRole->Test Instrument"


def test_equipmentroleequipmentassociation_get_equipment(equipmentroleequipmentassociation):
    assert isinstance(equipmentroleequipmentassociation.equipment, Equipment)
    assert equipmentroleequipmentassociation.equipment.name == "Test Instrument"


def test_equipmentroleequipmentassociation_set_equipment(equipmentroleequipmentassociation):
    test_insert = Equipment(name="Insert Equipment")
    equipmentroleequipmentassociation.equipment = test_insert
    assert test_insert == equipmentroleequipmentassociation.equipment

    test_insert = dict(name="Dict Equipment")
    equipmentroleequipmentassociation.equipment = test_insert
    assert "Dict Equipment" == equipmentroleequipmentassociation.equipment.name


def test_equipmentroleequipmentassociation_get_equipmentrole(equipmentroleequipmentassociation):
    assert isinstance(equipmentroleequipmentassociation.equipmentrole, EquipmentRole)
    assert equipmentroleequipmentassociation.equipmentrole.name == "Test EquipmentRole"


def test_equipmentroleequipmentassociation_set_equipmentrole(equipmentroleequipmentassociation):
    test_insert = EquipmentRole(name="Insert EquipmentRole")
    equipmentroleequipmentassociation.equipmentrole = test_insert
    assert test_insert == equipmentroleequipmentassociation.equipmentrole

    test_insert = dict(name="Dict EquipmentRole")
    equipmentroleequipmentassociation.equipmentrole = test_insert
    assert "Dict EquipmentRole" == equipmentroleequipmentassociation.equipmentrole.name


def test_equipmentroleequipmentassociation_get_processversion(equipmentroleequipmentassociation):
    assert isinstance(equipmentroleequipmentassociation.process, list)
    assert isinstance(equipmentroleequipmentassociation.process[0], Process)
    assert equipmentroleequipmentassociation.process[0].name == "Test Process"


def test_equipmentroleequipmentassociation_set_process(equipmentroleequipmentassociation):
    test_insert = Process(name="Insert Process")
    equipmentroleequipmentassociation.process = test_insert
    assert test_insert in equipmentroleequipmentassociation.process
    test_insert = dict(name="Dict Process")
    equipmentroleequipmentassociation.process = test_insert
    assert "Dict Process" in [item.name for item in equipmentroleequipmentassociation.process]






