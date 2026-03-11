from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydproceduretypereagentroleassociation_created_instance(reset_database):
    """Create a Pydproceduretypereagentroleassociation instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Proceduretypereagentroleassociation and TipsLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    proceduretypereagentroleassociation = pydant.PydProcedureTypeReagentRoleAssociation(
        proceduretype = "Test ProcedureType",
        reagentrole = "Test ReagentRole"
    )
    return proceduretypereagentroleassociation


@pytest.fixture(scope="function")
def pydproceduretypereagentroleassociation_sql_instance(reset_database):
    pydproceduretypereagentroleassociation_sql_instance = models.ProcedureTypeReagentRoleAssociation.query(proceduretype="Test ProcedureType", reagentrole="Test ReagentRole", limit=1)
    return pydproceduretypereagentroleassociation_sql_instance.to_pydantic() if pydproceduretypereagentroleassociation_sql_instance else None


def test_pydproceduretypereagentroleassociation_creation(pydproceduretypereagentroleassociation_created_instance):
    """Test that Pydproceduretypereagentroleassociation properties are correctly set."""
    assert pydproceduretypereagentroleassociation_created_instance.reagentrole == "Test ReagentRole"
    assert pydproceduretypereagentroleassociation_created_instance.proceduretype == "Test ProcedureType"
    

def test_pydproceduretypereagentroleassociation_to_sql(pydproceduretypereagentroleassociation_created_instance):
    """Test that Pydproceduretypereagentroleassociation.to_sql() properly converts to SQL Tips with relationships."""
    sql_instance = pydproceduretypereagentroleassociation_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ProcedureTypeReagentRoleAssociation)
    # Test that proceduretypereagentroleassociation is properly resolved (should not be None)
    assert sql_instance.proceduretype is not None
    assert isinstance(sql_instance.proceduretype, models.procedures.ProcedureType)
    assert sql_instance.proceduretype.name == "Test ProcedureType"
    # Test that tipslot is properly resolved (should not be None)
    assert sql_instance.reagentrole is not None
    
    assert isinstance(sql_instance.reagentrole, models.procedures.ReagentRole)
    assert sql_instance.reagentrole.name == "Test ReagentRole"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydproceduretypereagentroleassociation_improved_dict(pydproceduretypereagentroleassociation_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydproceduretypereagentroleassociation_created_instance.improved_dict
    assert "reagentrole" in d
    assert d['reagentrole'] == "Test ReagentRole" 
    assert "proceduretype" in d
    assert  d['proceduretype'] == "Test ProcedureType"
    assert "last_used" in d
    assert d['last_used'] == "NA"


def test_pydproceduretypereagentroleassociation_expand_fields(pydproceduretypereagentroleassociation_sql_instance):
    """Test that expand_fields properly expands proceduretypereagentroleassociation and tipslot."""
    expanded = pydproceduretypereagentroleassociation_sql_instance.improved_dict_expand_fields(["proceduretype"])
    assert isinstance(expanded['proceduretype'], dict)
    assert expanded['proceduretype']['name'] == "Test ProcedureType"
    expanded = pydproceduretypereagentroleassociation_sql_instance.improved_dict_expand_fields([{"reagentrole":["reagent"]}])
    assert isinstance(expanded['reagentrole'], dict)
    assert expanded['reagentrole']['name'] == "Test ReagentRole"
    assert expanded['reagentrole']['reagent'][0]['name'] == "Test Solution"
    

def test_pydproceduretypereagentroleassociation_fields(pydproceduretypereagentroleassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydproceduretypereagentroleassociation_created_instance.fields
    assert "name" in fields
    assert "last_used" in fields
    assert "proceduretype" in fields
    assert "reagentrole" in fields
    

def test_pydproceduretypereagentroleassociation_described_fields(pydproceduretypereagentroleassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydproceduretypereagentroleassociation_created_instance.described_fields
    assert len(fields) == 0
    
    
def test_form_dictionary(pydproceduretypereagentroleassociation_sql_instance):
    list_ = [item for item in pydproceduretypereagentroleassociation_sql_instance.form_dictionary]
    assert len(list_) == 0


def test_update_instrumented_attribute(pydproceduretypereagentroleassociation_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydproceduretypereagentroleassociation_created_instance.update_instrumentedattribute("last_used", "Ma Kettle")
    assert pydproceduretypereagentroleassociation_created_instance.last_used == "Ma Kettle"


def test_aliases(pydproceduretypereagentroleassociation_created_instance):
    assert 'proceduretypereagentroleassociation' in pydproceduretypereagentroleassociation_created_instance.aliases
    assert 'reagentroleproceduretypeassociation' in pydproceduretypereagentroleassociation_created_instance.aliases

