from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydreagent_created_instance(reset_database):
    """Create a PydReagent instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created ReagentRole and ReagentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    reagent = pydant.PydReagent(
        name="Test Reagent",
        eol_ext=60,
        reagentrole=["Test ReagentRole"],
        manufacturer="Acme Corp",
        ref="AC12345",
        comment="This is only a test.",
        cost_per_ml=0.5,
        reagentlot=["012345"]
    )
    return reagent


@pytest.fixture(scope="function")
def pydreagent_sql_instance(reset_database):
    pydreagent_sql_instance = models.Reagent.query(name="Test Solution", limit=1)
    return pydreagent_sql_instance.to_pydantic() if pydreagent_sql_instance else None


def test_pydreagent_creation(pydreagent_created_instance):
    """Test that PydReagent properties are correctly set."""
    assert pydreagent_created_instance.name == "Test Reagent"
    assert pydreagent_created_instance.eol_ext == 60
    assert pydreagent_created_instance.reagentrole == ["Test ReagentRole"]
    assert pydreagent_created_instance.manufacturer == "Acme Corp"
    assert pydreagent_created_instance.ref == "AC12345"
    assert pydreagent_created_instance.cost_per_ml == 0.5
    assert pydreagent_created_instance.reagentlot == ["012345"]


def test_pydreagent_to_sql(pydreagent_created_instance):
    """Test that PydReagent.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydreagent_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.Reagent)
    # Test that reagentrole is properly resolved (should not be None)
    assert sql_instance.reagentrole is not None
    assert len(sql_instance.reagentrole) > 0
    assert isinstance(sql_instance.reagentrole[0], models.procedures.ReagentRole)
    assert sql_instance.reagentrole[0].name == "Test ReagentRole"
    # Test that reagentlot is properly resolved (should not be None)
    assert sql_instance.reagentlot is not None
    assert len(sql_instance.reagentlot) > 0
    assert isinstance(sql_instance.reagentlot[0], models.procedures.ReagentLot)
    assert sql_instance.reagentlot[0].lot == "012345"
    assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydreagent_improved_dict(pydreagent_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydreagent_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Test Reagent"
    assert "eol_ext" in d
    assert d['eol_ext'] == 60
    assert "reagentrole" in d
    assert d['reagentrole'] == ["Test ReagentRole"]
    assert "manufacturer" in d
    assert d['manufacturer'] == "Acme Corp"
    assert "ref" in d
    assert d['ref'] == "AC12345"
    assert "cost_per_ml" in d
    assert d['cost_per_ml'] == 0.5
    assert "reagentlot" in d
    assert d['reagentlot'] == ["012345"]


def test_pydreagent_expand_fields(pydreagent_sql_instance):
    """Test that expand_fields properly expands reagentrole and reagentlot."""
    expanded = pydreagent_sql_instance.improved_dict_expand_fields(["reagentlot"])
    assert isinstance(expanded['reagentlot'], list)
    assert expanded['reagentlot'][0]['name'] == "Test Solution - 012345"
    expanded = pydreagent_sql_instance.improved_dict_expand_fields({"reagentrole": ['proceduretype']})
    assert isinstance(expanded['reagentrole'], list)
    assert expanded['reagentrole'][0]['name'] == "Test ReagentRole"
    assert expanded['reagentrole'][0]['proceduretype'][0]['name'] == "Test ProcedureType"


def test_pydreagent_fields(pydreagent_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagent_created_instance.fields
    assert "name" in fields
    assert "eol_ext" in fields
    assert "manufacturer" in fields
    assert "ref" in fields
    assert "cost_per_ml" in fields


def test_pydreagent_described_fields(pydreagent_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagent_created_instance.described_fields
    assert "name" in fields
    assert "eol_ext" in fields
    assert "manufacturer" in fields
    assert "ref" in fields
    assert "cost_per_ml" in fields
    assert "reagentrole" in fields
    assert "reagentlot" in fields
    assert "comment" not in fields


def test_determine_field_type(pydreagent_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydreagent_created_instance.determine_field_type("name") == 'str'
    assert pydreagent_created_instance.determine_field_type("eol_ext") == 'int'
    assert pydreagent_created_instance.determine_field_type("manufacturer") == 'str'
    assert pydreagent_created_instance.determine_field_type("ref") == 'str'
    assert pydreagent_created_instance.determine_field_type("cost_per_ml") == 'float'
    assert pydreagent_created_instance.determine_field_type("reagentrole") == 'ObjectAssociationProxyInstance'
    assert pydreagent_created_instance.determine_field_type("reagentlot") == 'RelationshipList'


def test_form_dictionary(pydreagent_sql_instance):
    list_ = [item for item in pydreagent_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    name_ = next((item for item in list_ if item['field'] == "name"), None)
    assert name_ is not None
    assert name_['value'] == "Test Solution"
    assert name_['type'] == 'STR'
    reagentrole = next((item for item in list_ if item['field'] == "reagentrole"), None)
    assert reagentrole is not None
    assert reagentrole['value'] == ["Test ReagentRole"]
    assert reagentrole['type'] == 'SKIPPED'
    eol_ext = next((item for item in list_ if item['field'] == "eol_ext"), None)
    assert eol_ext is not None
    assert eol_ext['value'] == 30
    assert eol_ext['type'] == 'INT'
    manufacturer = next((item for item in list_ if item['field'] == "manufacturer"), None)
    assert manufacturer is not None
    assert manufacturer['value'] == "NA"
    assert manufacturer['type'] == 'STR'
    ref = next((item for item in list_ if item['field'] == "ref"), None)
    assert ref is not None
    assert ref['value'] == "NA"
    assert ref['type'] == 'STR'
    reagentlot = next((item for item in list_ if item['field'] == "reagentlot"), None)
    assert reagentlot is not None
    assert reagentlot['value'] == ['Test Solution - 012345']
    assert reagentlot['type'] == 'RELATIONSHIPLIST'


def test_add_remove_relationship(pydreagent_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new ReagentLot SQL instance to relate to
    new_lot = models.procedures.ReagentLot(lot="New Lot", reagent_id=None)
    new_lot.save()
    # Add the relationship using the PydReagent method
    pydreagent_created_instance.add_relationship("reagentlot", "New Lot")
    # Check that the new lot is now in the reagentlot list
    assert any(lot == "New Lot" for lot in pydreagent_created_instance.reagentlot)
    # Now remove the relationship
    pydreagent_created_instance.remove_relationship("reagentlot", "New Lot")
    assert not any(lot == "New Lot" for lot in pydreagent_created_instance.reagentlot)


def test_update_instrumented_attribute(pydreagent_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydreagent_created_instance.update_instrumentedattribute("manufacturer", "New Manufacturer")
    assert pydreagent_created_instance.manufacturer == "New Manufacturer"



