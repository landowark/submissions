from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydreagentrolereagentassociation_created_instance(reset_database):
    """Create a Pydreagentrolereagentassociation instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Proceduretypereagentroleassociation and TipsLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    reagentrolereagentassociation = pydant.PydReagentRoleReagentAssociation(
        reagent = "Test Solution",
        reagentrole = "Test ReagentRole",
        ml_used_per_sample = 0.200
    )
    return reagentrolereagentassociation


@pytest.fixture(scope="function")
def pydreagentrolereagentassociation_sql_instance(reset_database):
    pydreagentrolereagentassociation_sql_instance = models.ReagentRoleReagentAssociation.query(reagent="Test Reagent", reagentrole="Test ReagentRole", limit=1)
    return pydreagentrolereagentassociation_sql_instance.to_pydantic() if pydreagentrolereagentassociation_sql_instance else None


def test_pydreagentrolereagentassociation_creation(pydreagentrolereagentassociation_created_instance):
    """Test that Pydreagentrolereagentassociation properties are correctly set."""
    assert pydreagentrolereagentassociation_created_instance.reagentrole == "Test ReagentRole"
    assert pydreagentrolereagentassociation_created_instance.reagent == "Test Solution"
    

def test_pydreagentrolereagentassociation_to_sql(pydreagentrolereagentassociation_created_instance):
    """Test that Pydreagentrolereagentassociation.to_sql() properly converts to SQL Tips with relationships."""
    sql_instance = pydreagentrolereagentassociation_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ReagentRoleReagentAssociation)
    # Test that reagentrolereagentassociation is properly resolved (should not be None)
    assert sql_instance.reagent is not None
    assert isinstance(sql_instance.reagent, models.procedures.Reagent)
    assert sql_instance.reagent.name == "Test Solution"
    # Test that tipslot is properly resolved (should not be None)
    assert sql_instance.reagentrole is not None
    
    assert isinstance(sql_instance.reagentrole, models.procedures.ReagentRole)
    assert sql_instance.reagentrole.name == "Test ReagentRole"
    # assert isinstance(sql_instance.eol_ext, timedelta)
    assert sql_instance.ml_used_per_sample == 0.2


def test_pydreagentrolereagentassociation_improved_dict(pydreagentrolereagentassociation_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydreagentrolereagentassociation_created_instance.improved_dict
    assert "reagentrole" in d
    assert d['reagentrole'] == "Test ReagentRole" 
    assert "reagent" in d
    assert  d['reagent'] == "Test Solution"
    assert "ml_used_per_sample" in d
    assert d['ml_used_per_sample'] == 0.200


def test_pydreagentrolereagentassociation_expand_fields(pydreagentrolereagentassociation_sql_instance):
    """Test that expand_fields properly expands reagentrolereagentassociation and tipslot."""
    expanded = pydreagentrolereagentassociation_sql_instance.improved_dict_expand_fields(["reagent"])
    assert isinstance(expanded['reagent'], dict)
    assert expanded['reagent']['name'] == "Test Solution"
    expanded = pydreagentrolereagentassociation_sql_instance.improved_dict_expand_fields([{"reagentrole":["reagent"]}])
    assert isinstance(expanded['reagentrole'], dict)
    assert expanded['reagentrole']['name'] == "Test ReagentRole"
    assert expanded['reagentrole']['reagent'][0]['name'] == "Test Solution"
    

def test_pydreagentrolereagentassociation_fields(pydreagentrolereagentassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagentrolereagentassociation_created_instance.fields
    assert "name" in fields
    assert "ml_used_per_sample" in fields
    assert "reagent" in fields
    assert "reagentrole" in fields
    

def test_pydreagentrolereagentassociation_described_fields(pydreagentrolereagentassociation_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagentrolereagentassociation_created_instance.described_fields
    assert len(fields) == 1
    
    
def test_form_dictionary(pydreagentrolereagentassociation_sql_instance):
    list_ = [item for item in pydreagentrolereagentassociation_sql_instance.form_dictionary]
    assert len(list_) == 1


def test_update_instrumented_attribute(pydreagentrolereagentassociation_created_instance):
    """Test that updating an ReagentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydreagentrolereagentassociation_created_instance.update_instrumentedattribute("last_used", "Ma Kettle")
    assert pydreagentrolereagentassociation_created_instance.last_used == "Ma Kettle"


def test_aliases(pydreagentrolereagentassociation_created_instance):
    assert 'reagentrolereagentassociation' in pydreagentrolereagentassociation_created_instance.aliases
    assert 'reagentreagentroleassociation' in pydreagentrolereagentassociation_created_instance.aliases

