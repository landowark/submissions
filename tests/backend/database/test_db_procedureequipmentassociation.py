from datetime import date, timedelta
import logging
import pytest
from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureEquipmentAssociation,
    EquipmentRole,
    Equipment,
    Process,
    ProcessVersion
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
def procedureequipmentassociation(db):
    return ProcedureEquipmentAssociation.query(limit=1)


def test_procedureequipmentassociation_query(procedureequipmentassociation):
    assert isinstance(procedureequipmentassociation, ProcedureEquipmentAssociation)


def test_procedureequipmentassociation_get_name(procedureequipmentassociation):
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert procedureequipmentassociation.name == f"RSL-XX-20260202-1 - Test ProcedureType - {day} 00:00:00->Test Instrument"


def test_procedureequipmentassociation_get_equipment(procedureequipmentassociation):
    
    assert isinstance(procedureequipmentassociation.equipment, Equipment)
    assert procedureequipmentassociation.equipment.name == "Test Instrument"


def test_procedureequipmentassociation_set_equipment(procedureequipmentassociation):
    test_insert = Equipment(name="Insert Equipment")
    procedureequipmentassociation.equipment = test_insert
    assert test_insert == procedureequipmentassociation.equipment

    test_insert = dict(name="Dict Equipment")
    procedureequipmentassociation.equipment = test_insert
    assert "Dict Equipment" == procedureequipmentassociation.equipment.name


def test_procedureequipmentassociation_get_equipmentrole(procedureequipmentassociation):
    assert isinstance(procedureequipmentassociation.equipmentrole, EquipmentRole)
    assert procedureequipmentassociation.equipmentrole.name == "Test EquipmentRole"


def test_procedureequipmentassociation_set_equipmentrole(procedureequipmentassociation):
    test_insert = EquipmentRole(name="Insert EquipmentRole")
    procedureequipmentassociation.equipmentrole = test_insert
    assert test_insert == procedureequipmentassociation.equipmentrole

    test_insert = dict(name="Dict EquipmentRole")
    procedureequipmentassociation.equipmentrole = test_insert
    assert "Dict EquipmentRole" == procedureequipmentassociation.equipmentrole.name


def test_procedureequipmentassociation_get_processversion(procedureequipmentassociation):
    
    assert isinstance(procedureequipmentassociation.processversion, ProcessVersion)
    assert procedureequipmentassociation.processversion.name == "Test Process - v1.0"


def test_procedureequipmentassociation_set_processversion(procedureequipmentassociation):
    pr = Process.query(limit=1)
    test_insert = ProcessVersion(version=2.0, process=pr)
    procedureequipmentassociation.processversion = test_insert
    assert test_insert == procedureequipmentassociation.processversion
    test_insert = dict(version=2.0, process=pr)
    procedureequipmentassociation.processversion = test_insert
    assert "Test Process - v2.0" == procedureequipmentassociation.processversion.name


def test_procedureequipmentassociation_details_dict_no_role(db):
    """Ensure details_dict gracefully handles missing equipmentrole.

    This mirrors a bug where ``equipmentrole`` was ``None`` on an
    association and accessing ``.name`` raised ``AttributeError``. The fix
    returns an empty string instead.
    """
    # create a new association without specifying equipmentrole
    assoc = ProcedureEquipmentAssociation(
        equipment="Test Instrument",
        procedure="Unknown Run-Unknown ProcedureType",
    )
    # The new object shouldn't have an equipmentrole set yet
    assert assoc.equipmentrole is None
    # Accessing details_dict must not raise and should include an empty value
    d = assoc.details_dict
    assert 'equipmentrole' in d
    assert d['equipmentrole'] == ""

