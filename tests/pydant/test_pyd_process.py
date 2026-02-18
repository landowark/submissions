from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydprocess_created_instance(reset_database):
    """Create a Pydprocess instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Process and TipsLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    process = pydant.PydProcess(
        name="Bob's Process",
        tips=["ACME Tips-XXXX(1000uL)"],
        processversion=["Test Process-v1.0"]
    )
    return process


@pytest.fixture(scope="function")
def pydprocess_sql_instance(reset_database):
    pydprocess_sql_instance = models.Process.query(name="Test Process", limit=1)
    return pydprocess_sql_instance.to_pydantic() if pydprocess_sql_instance else None


def test_pydprocess_creation(pydprocess_created_instance):
    """Test that Pydprocess properties are correctly set."""
    assert pydprocess_created_instance.name == "Bob's Process"
    assert pydprocess_created_instance.tips == ["ACME Tips-XXXX(1000uL)"]
    assert pydprocess_created_instance.processversion == ["Test Process-v1.0"]
    

def test_pydprocess_to_sql(pydprocess_created_instance):
    """Test that Pydprocess.to_sql() properly converts to SQL Tips with relationships."""
    sql_instance = pydprocess_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.Process)
    # Test that process is properly resolved (should not be None)
    assert sql_instance.processversion is not None
    assert len(sql_instance.processversion) > 0
    assert isinstance(sql_instance.processversion[0], models.procedures.ProcessVersion)
    assert sql_instance.processversion[0].name == "Bob's Process-v1.0"
    # Test that tipslot is properly resolved (should not be None)
    assert sql_instance.tips is not None
    assert len(sql_instance.tips) > 0
    assert isinstance(sql_instance.tips[0], models.procedures.Tips)
    assert sql_instance.tips[0].name == "ACME Tips-XXXX(1000uL)"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydprocess_improved_dict(pydprocess_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydprocess_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's Process"
    assert "tips" in d
    assert d['tips'] == ["ACME Tips-XXXX(1000uL)"]
    assert "processversion" in d
    assert d['processversion'] == ["Test Process-v1.0"]


def test_pydprocess_expand_fields(pydprocess_sql_instance):
    """Test that expand_fields properly expands process and tipslot."""
    expanded = pydprocess_sql_instance.improved_dict_expand_fields(["tips"])
    assert isinstance(expanded['tips'], list)
    assert expanded['tips'][0]['name'] == "ACME Tips-XXXX(1000uL)"
    expanded = pydprocess_sql_instance.improved_dict_expand_fields(["processversion"])
    assert isinstance(expanded['processversion'], list)
    assert expanded['processversion'][0]['name'] == "Test Process-v1.0"
    

def test_pydprocess_fields(pydprocess_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydprocess_created_instance.fields
    assert "name" in fields
    assert "tips" not in fields
    assert "processversion" not in fields
    

def test_pydprocess_described_fields(pydprocess_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydprocess_created_instance.described_fields
    assert "name" in fields
    assert "tips" in fields
    assert "processversion" in fields
    

def test_determine_field_type(pydprocess_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydprocess_created_instance.determine_field_type("name") == 'str'
    assert pydprocess_created_instance.determine_field_type("processversion") == 'RelationshipList'
    assert pydprocess_created_instance.determine_field_type("tips") == 'RelationshipList'
    
    
def test_form_dictionary(pydprocess_sql_instance):
    list_ = [item for item in pydprocess_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    name_ = next((item for item in list_ if item['field'] == "name"), None)
    assert name_ is not None
    assert name_['value'] == "Test Process"
    assert name_['type'] == 'STR'
    tips = next((item for item in list_ if item['field'] == "tips"), None)
    assert tips is not None
    assert tips['value'] == ["ACME Tips - XXXX - 098765"]
    assert tips['type'] == 'RELATIONSHIPLIST'
    processversion = next((item for item in list_ if item['field'] == "processversion"), None)
    assert processversion is not None
    assert processversion['value'] == ['Test Process-v1.0']
    assert processversion['type'] == 'RELATIONSHIPLIST'


def test_add_remove_relationship(pydprocess_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new TipsLot SQL instance to relate to
    new_lot = models.procedures.Tips(name="New Tips", tipslot=None)
    new_lot.save()
    # Add the relationship using the Pydprocess method
    pydprocess_created_instance.add_relationship("tips", "New Tips")
    # Check that the new lot is now in the tipslot list
    assert any(lot == "New Tips" for lot in pydprocess_created_instance.tips)
    # Now remove the relationship
    pydprocess_created_instance.remove_relationship("tips", "New Tips")
    assert not any(lot == "New Tips" for lot in pydprocess_created_instance.tips)


def test_update_instrumented_attribute(pydprocess_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydprocess_created_instance.update_instrumentedattribute("manufacturer", "New Manufacturer")
    assert pydprocess_created_instance.manufacturer == "New Manufacturer"



