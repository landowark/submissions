from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydequipmentrole_created_instance(reset_database):
    """Create a Pydequipmentrole instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created EquipmentRole and EquipmentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    equipmentrole = pydant.PydEquipmentRole(
        name="Bob's EquipmentRole",
        equipment=["Test Instrument"],
        proceduretype=["Test ProcedureType"]
    )
    return equipmentrole


@pytest.fixture(scope="function")
def pydequipmentrole_sql_instance(reset_database):
    pydequipmentrole_sql_instance = models.EquipmentRole.query(name="Test EquipmentRole", limit=1)
    return pydequipmentrole_sql_instance.to_pydantic() if pydequipmentrole_sql_instance else None


def test_pydequipmentrole_creation(pydequipmentrole_created_instance):
    """Test that Pydequipmentrole properties are correctly set."""
    assert pydequipmentrole_created_instance.name == "Bob's EquipmentRole"
    assert pydequipmentrole_created_instance.equipment == ["Test Instrument"]
    assert pydequipmentrole_created_instance.proceduretype == ["Test ProcedureType"]
    

def test_pydequipmentrole_to_sql(pydequipmentrole_created_instance):
    """Test that Pydequipmentrole.to_sql() properly converts to SQL Equipment with relationships."""
    sql_instance = pydequipmentrole_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.EquipmentRole)
    # Test that equipmentrole is properly resolved (should not be None)
    assert sql_instance.proceduretype is not None
    assert len(sql_instance.proceduretype) > 0
    assert isinstance(sql_instance.proceduretype[0], models.procedures.ProcedureType)
    assert sql_instance.proceduretype[0].name == "Test ProcedureType"
    # Test that equipmentlot is properly resolved (should not be None)
    assert sql_instance.equipment is not None
    assert len(sql_instance.equipment) > 0
    assert isinstance(sql_instance.equipment[0], models.procedures.Equipment)
    assert sql_instance.equipment[0].name == "Test Instrument"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydequipmentrole_improved_dict(pydequipmentrole_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydequipmentrole_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's EquipmentRole"
    assert "equipment" in d
    assert d['equipment'] == ["Test Instrument"]
    assert "proceduretype" in d
    assert d['proceduretype'] == ["Test ProcedureType"]


def test_pydequipmentrole_expand_fields(pydequipmentrole_sql_instance):
    """Test that expand_fields properly expands equipmentrole and equipmentlot."""
    expanded = pydequipmentrole_sql_instance.improved_dict_expand_fields(["equipment"])
    assert isinstance(expanded['equipment'], list)
    assert expanded['equipment'][0]['name'] == "Test Instrument"
    expanded = pydequipmentrole_sql_instance.improved_dict_expand_fields({"proceduretype": ['submissiontype']})
    assert isinstance(expanded['proceduretype'], list)
    assert expanded['proceduretype'][0]['name'] == "Test ProcedureType"
    assert expanded['proceduretype'][0]['submissiontype'][0]['name'] == "Default SubmissionType"


def test_pydequipmentrole_fields(pydequipmentrole_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydequipmentrole_created_instance.fields
    assert "name" in fields
    assert "equipment" in fields
    assert "proceduretype" in fields
    

def test_pydequipmentrole_described_fields(pydequipmentrole_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydequipmentrole_created_instance.described_fields
    assert "name" in fields
    assert "equipment" in fields
    assert "proceduretype" in fields
    

def test_determine_field_type(pydequipmentrole_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydequipmentrole_created_instance.determine_field_type("name") == 'str'
    assert pydequipmentrole_created_instance.determine_field_type("proceduretype") == 'ObjectAssociationProxyInstance'
    assert pydequipmentrole_created_instance.determine_field_type("equipment") == 'ObjectAssociationProxyInstance'
    
    
def test_form_dictionary(pydequipmentrole_sql_instance):
    list_ = [item for item in pydequipmentrole_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    name_ = next((item for item in list_ if item['field'] == "name"), None)
    assert name_ is not None
    assert name_['value'] == "Test EquipmentRole"
    assert name_['type'] == 'STR'
    equipment = next((item for item in list_ if item['field'] == "equipment"), None)
    assert equipment is not None
    assert equipment['value'] == ["Test Instrument"]
    assert equipment['type'] == 'SKIPPED'
    proceduretype = next((item for item in list_ if item['field'] == "proceduretype"), None)
    assert proceduretype is not None
    assert proceduretype['value'] == ['Test ProcedureType']
    assert proceduretype['type'] == 'SKIPPED'


def test_add_remove_relationship(pydequipmentrole_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new EquipmentLot SQL instance to relate to
    new_lot = models.procedures.Equipment(name="New Equipment", equipmentlot=None)
    new_lot.save()
    # Add the relationship using the Pydequipmentrole method
    pydequipmentrole_created_instance.add_relationship("equipment", "New Equipment")
    # Check that the new lot is now in the equipmentlot list
    assert any(lot == "New Equipment" for lot in pydequipmentrole_created_instance.equipment)
    # Now remove the relationship
    pydequipmentrole_created_instance.remove_relationship("equipment", "New Equipment")
    assert not any(lot == "New Equipment" for lot in pydequipmentrole_created_instance.equipment)


def test_update_instrumented_attribute(pydequipmentrole_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydequipmentrole_created_instance.update_instrumentedattribute("manufacturer", "New Manufacturer")
    assert pydequipmentrole_created_instance.manufacturer == "New Manufacturer"



