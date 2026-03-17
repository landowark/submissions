import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import Equipment, Procedure, EquipmentRole
from sqlalchemy.ext.associationproxy import _AssociationList


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
def equipment(db):
    return Equipment.query(limit=1)


def test_equipment_query(equipment):
    assert isinstance(equipment, Equipment)


def test_equipment_get_procedure(equipment):
    assert isinstance(equipment.procedure, _AssociationList)
    assert isinstance(equipment.procedure[0], Procedure)


def test_equipment_set_procedure(equipment):
    test_insert = Procedure(name="Insert Procedure")
    equipment.procedure = [test_insert]
    assert test_insert in equipment.procedure

    # test_insert = dict(name="Dict Procedure")
    # equipment.procedure = [test_insert]
    # assert "Dict Procedure" in [item.name for item in equipment.procedure]


def test_equipment_get_equipmentrole(equipment):
    assert isinstance(equipment.equipmentrole, _AssociationList)
    assert isinstance(equipment.equipmentrole[0], EquipmentRole)


def test_equipment_set_equipmentrole(equipment):
    test_insert = EquipmentRole(name="Insert EquipmentRole")
    equipment.equipmentrole = [test_insert]
    assert test_insert in equipment.equipmentrole

    test_insert = dict(name="Dict EquipmentRole")
    equipment.equipmentrole = [test_insert]
    assert "Dict EquipmentRole" in [item.name for item in equipment.equipmentrole]


def test_equipment_nickname(equipment):
    assert equipment.nickname == "Testerino"
    equipment.nickname = ""
    assert equipment.nickname == equipment.name
