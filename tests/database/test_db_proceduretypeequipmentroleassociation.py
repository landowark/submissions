import logging
import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureTypeEquipmentRoleAssociation,
    
    ProcedureType,
    EquipmentRole,
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
def proceduretypeequipmentroleassociation(db):
    return ProcedureTypeEquipmentRoleAssociation.query(limit=1)


def test_proceduretypeequipmentroleassociation_query(proceduretypeequipmentroleassociation):
    assert isinstance(proceduretypeequipmentroleassociation, ProcedureTypeEquipmentRoleAssociation)


def test_proceduretypeequipmentroleassociation_get_proceduretype(proceduretypeequipmentroleassociation):
    assert isinstance(proceduretypeequipmentroleassociation.proceduretype, ProcedureType)


def test_proceduretypeequipmentroleassociation_set_proceduretype(proceduretypeequipmentroleassociation):
    test_insert = ProcedureType(name="Insert ProcedureType")
    proceduretypeequipmentroleassociation.proceduretype = test_insert
    assert proceduretypeequipmentroleassociation.proceduretype == test_insert

    test_insert = dict(name="Dict ProcedureType")
    proceduretypeequipmentroleassociation.proceduretype = test_insert
    assert proceduretypeequipmentroleassociation.proceduretype.name == "Dict ProcedureType"


def test_proceduretypeequipmentroleassociation_get_equipmentrole(proceduretypeequipmentroleassociation):
    assert isinstance(proceduretypeequipmentroleassociation.equipmentrole, EquipmentRole)


def test_proceduretypeequipmentroleassociation_set_equipmentrole(proceduretypeequipmentroleassociation):
    test_insert = EquipmentRole(name="Insert EquipmentRole")
    proceduretypeequipmentroleassociation.equipmentrole = test_insert
    assert proceduretypeequipmentroleassociation.equipmentrole == test_insert

    test_insert = dict(name="Dict EquipmentRole")
    proceduretypeequipmentroleassociation.equipmentrole = test_insert
    assert proceduretypeequipmentroleassociation.equipmentrole.name == "Dict EquipmentRole"



