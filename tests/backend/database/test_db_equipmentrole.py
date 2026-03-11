import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import EquipmentRole, Equipment, ProcedureType
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
def equipmentrole(db):
    return EquipmentRole.query(limit=1)


def test_equipmentrole_query(equipmentrole):
    assert isinstance(equipmentrole, EquipmentRole)


def test_equipmentrole_get_equipment(equipmentrole):
    assert isinstance(equipmentrole.equipment, _AssociationList)
    assert isinstance(equipmentrole.equipment[0], Equipment)


def test_equipmentrole_set_equipment(equipmentrole):
    test_insert = Equipment(name="Insert Equipment")
    equipmentrole.equipment = [test_insert]
    assert test_insert in equipmentrole.equipment

    test_insert = dict(name="Dict Equipment")
    equipmentrole.equipment = [test_insert]
    assert "Dict Equipment" in [item.name for item in equipmentrole.equipment]


def test_equipmentrole_get_proceduretype(equipmentrole):
    assert isinstance(equipmentrole.proceduretype, _AssociationList)
    assert isinstance(equipmentrole.proceduretype[0], ProcedureType)


def test_equipmentrole_set_proceduretype(equipmentrole):
    test_insert = ProcedureType(name="Insert ProcedureType")
    equipmentrole.proceduretype = [test_insert]
    assert test_insert in equipmentrole.proceduretype

    test_insert = dict(name="Dict ProcedureType")
    equipmentrole.proceduretype = [test_insert]
    assert "Dict ProcedureType" in [item.name for item in equipmentrole.proceduretype]
