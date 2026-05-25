from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydequipmentroleequipmentassociation_created_instance(reset_database):
    """Create a Pydequipmentroleequipmentassociation instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Proceduretypeequipmentroleassociation and TipsLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    equipmentroleequipmentassociation = pydant.PydEquipmentRoleEquipmentAssociation(
        equipment = "Test Instrument",
        equipmentrole = "Test EquipmentRole",
        process = ["Test Process"]
    )
    return equipmentroleequipmentassociation


@pytest.fixture(scope="function")
def pydequipmentroleequipmentassociation_sql_instance(reset_database):
    pydequipmentroleequipmentassociation_sql_instance = models.EquipmentRoleEquipmentAssociation.query(equipment="Test Instrument", equipmentrole="Test EquipmentRole", limit=1)
    return pydequipmentroleequipmentassociation_sql_instance.to_pydantic() if pydequipmentroleequipmentassociation_sql_instance else None


def test_pydequipmentroleequipmentassociation_creation(pydequipmentroleequipmentassociation_created_instance):
    """Test that Pydequipmentroleequipmentassociation properties are correctly set."""
    assert pydequipmentroleequipmentassociation_created_instance.equipmentrole == "Test EquipmentRole"
    assert pydequipmentroleequipmentassociation_created_instance.equipment == "Test Instrument"
    

def test_pydequipmentroleequipmentassociation_to_sql(pydequipmentroleequipmentassociation_created_instance):
    """Test that Pydequipmentroleequipmentassociation.to_sql() properly converts to SQL Tips with relationships."""
    sql_instance = pydequipmentroleequipmentassociation_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.EquipmentRoleEquipmentAssociation)
    # Test that equipmentroleequipmentassociation is properly resolved (should not be None)
    assert sql_instance.equipment is not None
    assert isinstance(sql_instance.equipment, models.procedures.Equipment)
    assert sql_instance.equipment.name == "Test Instrument"
    # Test that tipslot is properly resolved (should not be None)
    assert sql_instance.equipmentrole is not None
    
    assert isinstance(sql_instance.equipmentrole, models.procedures.EquipmentRole)
    assert sql_instance.equipmentrole.name == "Test EquipmentRole"
    # assert isinstance(sql_instance.eol_ext, timedelta)
    assert len(sql_instance.process) > 0
    assert "Test Process" in [item.name for item in sql_instance.process]


def test_pydequipmentroleequipmentassociation_improved_dict(pydequipmentroleequipmentassociation_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydequipmentroleequipmentassociation_created_instance.improved_dict
    assert "equipmentrole" in d
    assert d['equipmentrole'] == "Test EquipmentRole" 
    assert "equipment" in d
    assert  d['equipment'] == "Test Instrument"
    assert "process" in d
    assert "Test Process" in d['process']


def test_pydequipmentroleequipmentassociation_expand_fields(pydequipmentroleequipmentassociation_sql_instance):
    """Test that expand_fields properly expands equipmentroleequipmentassociation and tipslot."""
    expanded = pydequipmentroleequipmentassociation_sql_instance.improved_dict_expand_fields(["equipment"])
    assert isinstance(expanded['equipment'], dict)
    assert expanded['equipment']['name'] == "Test Instrument"
    expanded = pydequipmentroleequipmentassociation_sql_instance.improved_dict_expand_fields([{"equipmentrole":["equipment"]}])
    assert isinstance(expanded['equipmentrole'], dict)
    assert expanded['equipmentrole']['name'] == "Test EquipmentRole"
    assert expanded['equipmentrole']['equipment'][0]['name'] == "Test Instrument"
    

def test_pydequipmentroleequipmentassociation_fields(pydequipmentroleequipmentassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydequipmentroleequipmentassociation_created_instance.fields
    assert "name" in fields
    assert "process" in fields
    assert "equipment" in fields
    assert "equipmentrole" in fields
    

def test_pydequipmentroleequipmentassociation_described_fields(pydequipmentroleequipmentassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydequipmentroleequipmentassociation_created_instance.described_fields
    assert len(fields) == 1
    
    
def test_form_dictionary(pydequipmentroleequipmentassociation_sql_instance):
    list_ = [item for item in pydequipmentroleequipmentassociation_sql_instance.form_dictionary]
    assert len(list_) == 1


def test_update_instrumented_attribute(pydequipmentroleequipmentassociation_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydequipmentroleequipmentassociation_created_instance.update_instrumentedattribute("last_used", "Ma Kettle")
    assert pydequipmentroleequipmentassociation_created_instance.last_used == "Ma Kettle"


def test_aliases(pydequipmentroleequipmentassociation_created_instance):
    assert 'equipmentroleequipmentassociation' in pydequipmentroleequipmentassociation_created_instance.aliases
    assert 'equipmentequipmentroleassociation' in pydequipmentroleequipmentassociation_created_instance.aliases

