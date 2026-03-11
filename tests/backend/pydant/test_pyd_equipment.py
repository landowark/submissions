from datetime import timedelta, date, datetime
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydequipment_created_instance(reset_database):
    """Create a Pydequipment instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Equipment and Equipment instances, so sql_instances
    will have all required relationships properly resolved.
    """
    equipment = pydant.PydEquipment(
        name="Bob's Equipment",
        asset_number="2222",
        nickname="Scrapheap",
        manufacturer="Scrapyard",
        ref="0000",
        equipmentrole=["Test EquipmentRole"],
        procedure=["Unknown Run-Unknown ProcedureType"]
    )
    return equipment


@pytest.fixture(scope="function")
def pydequipment_sql_instance(reset_database):
    pydequipment_sql_instance = models.Equipment.query(name="Test Instrument", limit=1)
    return pydequipment_sql_instance.to_pydantic() if pydequipment_sql_instance else None


def test_pydequipment_creation(pydequipment_created_instance):
    """Test that Pydequipment properties are correctly set."""
    assert pydequipment_created_instance.name == "Bob's Equipment"
    assert "Unknown Run-Unknown ProcedureType" in pydequipment_created_instance.procedure 
    assert "Test EquipmentRole" in pydequipment_created_instance.equipmentrole
    assert pydequipment_created_instance.asset_number == "2222"
    assert pydequipment_created_instance.nickname == "Scrapheap"
    assert pydequipment_created_instance.manufacturer == "Scrapyard"
    assert pydequipment_created_instance.ref == "0000"
    

def test_pydequipment_to_sql(pydequipment_created_instance):
    """Test that Pydequipment.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydequipment_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.Equipment)
    # Test that equipment is properly resolved (should not be None)
    # assert sql_instance.equipmentrole is not None
    assert len(sql_instance.equipmentrole) > 0
    assert all([isinstance(item, models.procedures.EquipmentRole) for item in sql_instance.equipmentrole])
    assert "Test EquipmentRole" in [c.name for c in sql_instance.equipmentrole]
    # Test that equipment is properly resolved (should not be None)
    assert len(sql_instance.equipmentrole) > 0
    assert all([isinstance(item, models.procedures.Procedure) for item in sql_instance.procedure])
    assert "Unknown Run-Unknown ProcedureType" in [c.name for c in sql_instance.procedure]
    # assert len(sql_instance.equipmentrole) > 0
    assert sql_instance.nickname == "Scrapheap"
    assert sql_instance.asset_number == "2222"
    assert sql_instance.manufacturer == "Scrapyard"
    assert sql_instance.ref == "0000"


def test_pydequipment_improved_dict(pydequipment_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydequipment_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's Equipment"
    assert "equipmentrole" in d
    assert "Unknown Run-Unknown ProcedureType" in d['procedure']
    assert "equipmentrole" in d
    assert "Test EquipmentRole" in d['equipmentrole']
    assert "asset_number" in d
    assert d['asset_number'] == "2222"
    assert "manufacturer" in d
    assert d['manufacturer'] == "Scrapyard"
    assert "ref" in d
    assert d['ref'] == "0000"


def test_pydequipment_expand_fields(pydequipment_sql_instance):
    """Test that expand_fields properly expands equipment and equipment using a SQL-derived instance."""
    expanded = pydequipment_sql_instance.improved_dict_expand_fields(["equipmentrole"])
    assert isinstance(expanded['equipmentrole'], list)
    assert expanded['equipmentrole'][0]['name'] == "Test EquipmentRole"
    expanded = pydequipment_sql_instance.improved_dict_expand_fields({"procedure": ['submissiontype']})
    assert isinstance(expanded['procedure'], list)
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert expanded['procedure'][0]['name']['value'] == f"RSL-XX-20260202-1-Test ProcedureType-{day} 00:00:00"
    assert expanded['procedure'][0]['name']['missing'] == False
    assert expanded['procedure'][0]['submissiontype']['name'] == "Default SubmissionType"


def test_pydequipment_fields(pydequipment_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydequipment_created_instance.fields
    assert "name" in fields
    assert "equipmentrole" in fields
    assert "procedure" in fields
    assert "nickname" in fields
    assert "manufacturer" in fields
    assert "ref" in fields
    assert "asset_number" in fields
    

def test_pydequipment_described_fields(pydequipment_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydequipment_created_instance.described_fields
    assert "name" in fields
    assert "equipmentrole" in fields
    assert "asset_number" in fields
    assert "nickname" in fields
    assert "ref" in fields
    assert "manufacturer" in fields
    assert "procedure" not in fields
    

def test_determine_field_type(pydequipment_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydequipment_created_instance.determine_field_type("name") == 'str'
    assert pydequipment_created_instance.determine_field_type("equipmentrole") == 'ObjectAssociationProxyInstance'
    assert pydequipment_created_instance.determine_field_type("procedure") == 'ObjectAssociationProxyInstance'
    assert pydequipment_created_instance.determine_field_type("nickname") == 'str'
    assert pydequipment_created_instance.determine_field_type("manufacturer") == 'str'
    assert pydequipment_created_instance.determine_field_type("ref") == 'str'
    assert pydequipment_created_instance.determine_field_type("asset_number") == 'str'
    
    
def test_form_dictionary(pydequipment_sql_instance):
    list_ = [item for item in pydequipment_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    name = next((item for item in list_ if item['field'] == "name"), None)
    assert name is not None
    assert name['value'] == "Test Instrument"
    assert name['type'] == 'STR'
    equipmentrole = next((item for item in list_ if item['field'] == "equipmentrole"), None)
    assert equipmentrole is not None
    assert "Test EquipmentRole" in equipmentrole['value'] 
    assert equipmentrole['type'] == 'SKIPPED'
    nickname = next((item for item in list_ if item['field'] == "nickname"), None)
    assert nickname is not None
    assert nickname['value'] == "Testerino"
    assert nickname['type'] == 'STR'
    manufacturer = next((item for item in list_ if item['field'] == "manufacturer"), None)
    assert manufacturer is not None
    assert manufacturer['value'] == "ACME Corp"
    assert manufacturer['type'] == 'STR'
    ref = next((item for item in list_ if item['field'] == "ref"), None)
    assert ref is not None
    assert ref['value'] == "12345"
    assert ref['type'] == 'STR'
    asset_number = next((item for item in list_ if item['field'] == "asset_number"), None)
    assert asset_number is not None
    assert asset_number['value'] == "000000"
    assert asset_number['type'] == 'STR'


def test_add_remove_relationship(pydequipment_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new Equipment SQL instance to relate to
    new_lot = models.procedures.EquipmentRole(name="New EquipmentRole")
    new_lot.save()
    # Add the relationship using the Pydequipment method
    pydequipment_created_instance.add_relationship("equipmentrole", "New EquipmentRole")
    # Check that the new lot is now in the equipment list
    assert any(equipmentrole == "New EquipmentRole" for equipmentrole in pydequipment_created_instance.equipmentrole)
    # Now remove the relationship
    pydequipment_created_instance.remove_relationship("equipmentrole", "New EquipmentRole")
    assert not any(equipmentrole == "New Procedure" for equipmentrole in pydequipment_created_instance.equipmentrole)


def test_update_instrumented_attribute(pydequipment_created_instance):
    """Test that updating an SolutionedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydequipment_created_instance.update_instrumentedattribute("ref", "New Ref")
    assert pydequipment_created_instance.ref == "New Ref"



