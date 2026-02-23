from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydreagentrole_created_instance(reset_database):
    """Create a PydReagentRole instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created ReagentRole and ReagentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    reagentrole = pydant.PydReagentRole(
        name="Bob's ReagentRole",
        reagent=["Test Solution"],
        proceduretype=["Test ProcedureType"]
    )
    return reagentrole


@pytest.fixture(scope="function")
def pydreagentrole_sql_instance(reset_database):
    pydreagentrole_sql_instance = models.ReagentRole.query(name="Test ReagentRole", limit=1)
    return pydreagentrole_sql_instance.to_pydantic() if pydreagentrole_sql_instance else None


def test_pydreagentrole_creation(pydreagentrole_created_instance):
    """Test that PydReagentRole properties are correctly set."""
    assert pydreagentrole_created_instance.name == "Bob's ReagentRole"
    assert pydreagentrole_created_instance.reagent == ["Test Solution"]
    assert pydreagentrole_created_instance.proceduretype == ["Test ProcedureType"]
    

def test_pydreagentrole_to_sql(pydreagentrole_created_instance):
    """Test that PydReagentRole.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydreagentrole_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ReagentRole)
    # Test that reagentrole is properly resolved (should not be None)
    assert sql_instance.proceduretype is not None
    assert len(sql_instance.proceduretype) > 0
    assert isinstance(sql_instance.proceduretype[0], models.procedures.ProcedureType)
    assert sql_instance.proceduretype[0].name == "Test ProcedureType"
    # Test that reagentlot is properly resolved (should not be None)
    assert sql_instance.reagent is not None
    assert len(sql_instance.reagent) > 0
    assert isinstance(sql_instance.reagent[0], models.procedures.Reagent)
    assert sql_instance.reagent[0].name == "Test Solution"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydreagentrole_improved_dict(pydreagentrole_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydreagentrole_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's ReagentRole"
    assert "reagent" in d
    assert d['reagent'] == ["Test Solution"]
    assert "proceduretype" in d
    assert d['proceduretype'] == ["Test ProcedureType"]


def test_pydreagentrole_expand_fields(pydreagentrole_sql_instance):
    """Test that expand_fields properly expands reagentrole and reagentlot."""
    expanded = pydreagentrole_sql_instance.improved_dict_expand_fields(["reagent"])
    assert isinstance(expanded['reagent'], list)
    assert expanded['reagent'][0]['name'] == "Test Solution"
    expanded = pydreagentrole_sql_instance.improved_dict_expand_fields({"proceduretype": ['submissiontype']})
    assert isinstance(expanded['proceduretype'], list)
    assert expanded['proceduretype'][0]['name'] == "Test ProcedureType"
    assert expanded['proceduretype'][0]['submissiontype'][0]['name'] == "Default SubmissionType"


def test_pydreagentrole_fields(pydreagentrole_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagentrole_created_instance.fields
    assert "name" in fields
    assert "reagent" in fields
    assert "proceduretype" in fields
    

def test_pydreagentrole_described_fields(pydreagentrole_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagentrole_created_instance.described_fields
    assert "name" in fields
    assert "reagent" in fields
    assert "proceduretype" in fields
    

def test_determine_field_type(pydreagentrole_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydreagentrole_created_instance.determine_field_type("name") == 'str'
    assert pydreagentrole_created_instance.determine_field_type("proceduretype") == 'ObjectAssociationProxyInstance'
    assert pydreagentrole_created_instance.determine_field_type("reagent") == 'ObjectAssociationProxyInstance'
    
    
def test_form_dictionary(pydreagentrole_sql_instance):
    list_ = [item for item in pydreagentrole_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    name_ = next((item for item in list_ if item['field'] == "name"), None)
    assert name_ is not None
    assert name_['value'] == "Test ReagentRole"
    assert name_['type'] == 'STR'
    reagent = next((item for item in list_ if item['field'] == "reagent"), None)
    assert reagent is not None
    assert reagent['value'] == ["Test Solution"]
    assert reagent['type'] == 'SKIPPED'
    proceduretype = next((item for item in list_ if item['field'] == "proceduretype"), None)
    assert proceduretype is not None
    assert proceduretype['value'] == ['Test ProcedureType']
    assert proceduretype['type'] == 'SKIPPED'


def test_add_remove_relationship(pydreagentrole_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new ReagentLot SQL instance to relate to
    new_lot = models.procedures.Reagent(name="New Reagent", reagentlot=None)
    new_lot.save()
    # Add the relationship using the PydReagentRole method
    pydreagentrole_created_instance.add_relationship("reagent", "New Reagent")
    # Check that the new lot is now in the reagentlot list
    assert any(lot == "New Reagent" for lot in pydreagentrole_created_instance.reagent)
    # Now remove the relationship
    pydreagentrole_created_instance.remove_relationship("reagent", "New Reagent")
    assert not any(lot == "New Reagent" for lot in pydreagentrole_created_instance.reagent)


def test_update_instrumented_attribute(pydreagentrole_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydreagentrole_created_instance.update_instrumentedattribute("manufacturer", "New Manufacturer")
    assert pydreagentrole_created_instance.manufacturer == "New Manufacturer"



