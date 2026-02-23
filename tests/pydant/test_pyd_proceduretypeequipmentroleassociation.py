from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydproceduretypeequipmentroleassociation_created_instance(reset_database):
    """Create a Pydproceduretypeequipmentroleassociation instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Proceduretypeequipmentroleassociation and TipsLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    proceduretypeequipmentroleassociation = pydant.PydProcedureTypeEquipmentRoleAssociation(
        proceduretype = "Test ProcedureType",
        equipmentrole = "Test EquipmentRole"
    )
    return proceduretypeequipmentroleassociation


@pytest.fixture(scope="function")
def pydproceduretypeequipmentroleassociation_sql_instance(reset_database):
    pydproceduretypeequipmentroleassociation_sql_instance = models.ProcedureTypeEquipmentRoleAssociation.query(proceduretype="Test ProcedureType", equipmentrole="Test EquipmentRole", limit=1)
    return pydproceduretypeequipmentroleassociation_sql_instance.to_pydantic() if pydproceduretypeequipmentroleassociation_sql_instance else None


def test_pydproceduretypeequipmentroleassociation_creation(pydproceduretypeequipmentroleassociation_created_instance):
    """Test that Pydproceduretypeequipmentroleassociation properties are correctly set."""
    assert pydproceduretypeequipmentroleassociation_created_instance.equipmentrole == "Test EquipmentRole"
    assert pydproceduretypeequipmentroleassociation_created_instance.proceduretype == "Test ProcedureType"
    

def test_pydproceduretypeequipmentroleassociation_to_sql(pydproceduretypeequipmentroleassociation_created_instance):
    """Test that Pydproceduretypeequipmentroleassociation.to_sql() properly converts to SQL Tips with relationships."""
    sql_instance = pydproceduretypeequipmentroleassociation_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ProcedureTypeEquipmentRoleAssociation)
    # Test that proceduretypeequipmentroleassociation is properly resolved (should not be None)
    assert sql_instance.proceduretype is not None
    assert isinstance(sql_instance.proceduretype, models.procedures.ProcedureType)
    assert sql_instance.proceduretype.name == "Test ProcedureType"
    # Test that tipslot is properly resolved (should not be None)
    assert sql_instance.equipmentrole is not None
    
    assert isinstance(sql_instance.equipmentrole, models.procedures.EquipmentRole)
    assert sql_instance.equipmentrole.name == "Test EquipmentRole"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydproceduretypeequipmentroleassociation_improved_dict(pydproceduretypeequipmentroleassociation_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydproceduretypeequipmentroleassociation_created_instance.improved_dict
    assert "equipmentrole" in d
    assert d['equipmentrole'] == "Test EquipmentRole" 
    assert "proceduretype" in d
    assert  d['proceduretype'] == "Test ProcedureType"
    assert "static" in d
    assert d['static'] == True


def test_pydproceduretypeequipmentroleassociation_expand_fields(pydproceduretypeequipmentroleassociation_sql_instance):
    """Test that expand_fields properly expands proceduretypeequipmentroleassociation and tipslot."""
    expanded = pydproceduretypeequipmentroleassociation_sql_instance.improved_dict_expand_fields(["proceduretype"])
    assert isinstance(expanded['proceduretype'], dict)
    assert expanded['proceduretype']['name'] == "Test ProcedureType"
    expanded = pydproceduretypeequipmentroleassociation_sql_instance.improved_dict_expand_fields([{"equipmentrole":["equipment"]}])
    assert isinstance(expanded['equipmentrole'], dict)
    assert expanded['equipmentrole']['name'] == "Test EquipmentRole"
    assert expanded['equipmentrole']['equipment'][0]['name'] == "Test Instrument"
    

def test_pydproceduretypeequipmentroleassociation_fields(pydproceduretypeequipmentroleassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydproceduretypeequipmentroleassociation_created_instance.fields
    assert "name" in fields
    assert "static" in fields
    assert "proceduretype" in fields
    assert "equipmentrole" in fields
    

def test_pydproceduretypeequipmentroleassociation_described_fields(pydproceduretypeequipmentroleassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydproceduretypeequipmentroleassociation_created_instance.described_fields
    assert len(fields) == 1
    
    
def test_form_dictionary(pydproceduretypeequipmentroleassociation_sql_instance):
    list_ = [item for item in pydproceduretypeequipmentroleassociation_sql_instance.form_dictionary]
    assert len(list_) == 1


def test_update_instrumented_attribute(pydproceduretypeequipmentroleassociation_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydproceduretypeequipmentroleassociation_created_instance.update_instrumentedattribute("last_used", "Ma Kettle")
    assert pydproceduretypeequipmentroleassociation_created_instance.last_used == "Ma Kettle"


def test_aliases(pydproceduretypeequipmentroleassociation_created_instance):
    assert 'proceduretypeequipmentroleassociation' in pydproceduretypeequipmentroleassociation_created_instance.aliases
    assert 'equipmentroleproceduretypeassociation' in pydproceduretypeequipmentroleassociation_created_instance.aliases

