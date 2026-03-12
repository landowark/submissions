from datetime import date, timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydresultstype_created_instance(reset_database):
    """Create a Pydresultstype instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created ResultsType and EquipmentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    resultstype = pydant.PydResultsType(
        name="Bob's ResultsType",
        results=[f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00 - Test ResultsType"],
        proceduretype=["Test ProcedureType"]
    )
    return resultstype


@pytest.fixture(scope="function")
def pydresultstype_sql_instance(reset_database):
    pydresultstype_sql_instance = models.ResultsType.query(name="Test ResultsType", limit=1)
    return pydresultstype_sql_instance.to_pydantic() if pydresultstype_sql_instance else None


def test_pydresultstype_creation(pydresultstype_created_instance):
    """Test that Pydresultstype properties are correctly set."""
    assert pydresultstype_created_instance.name == "Bob's ResultsType"
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert pydresultstype_created_instance.results == [f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00 - Test ResultsType"]
    assert pydresultstype_created_instance.proceduretype == ["Test ProcedureType"]
    

def test_pydresultstype_to_sql(pydresultstype_created_instance):
    """Test that Pydresultstype.to_sql() properly converts to SQL Equipment with relationships."""
    sql_instance = pydresultstype_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ResultsType)
    # Test that resultstype is properly resolved (should not be None)
    assert sql_instance.proceduretype is not None
    assert len(sql_instance.proceduretype) > 0
    assert isinstance(sql_instance.proceduretype[0], models.procedures.ProcedureType)
    assert sql_instance.proceduretype[0].name == "Test ProcedureType"
    # Test that resultslot is properly resolved (should not be None)
    assert sql_instance.results is not None
    assert len(sql_instance.results) > 0
    assert isinstance(sql_instance.results[0], models.procedures.Results)
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert sql_instance.results[0].name == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00 - Bob's ResultsType"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydresultstype_improved_dict(pydresultstype_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydresultstype_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's ResultsType"
    assert "results" in d
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert d['results'] == [f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00 - Test ResultsType"]
    assert "proceduretype" in d
    assert d['proceduretype'] == ["Test ProcedureType"]


def test_pydresultstype_expand_fields(pydresultstype_sql_instance):
    """Test that expand_fields properly expands resultstype and resultslot."""
    expanded = pydresultstype_sql_instance.improved_dict_expand_fields(["results"])
    assert isinstance(expanded['results'], list)
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert expanded['results'][0]['name'] == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00-Test ResultsType"
    expanded = pydresultstype_sql_instance.improved_dict_expand_fields({"proceduretype": ['submissiontype']})
    assert isinstance(expanded['proceduretype'], list)
    assert expanded['proceduretype'][0]['name'] == "Test ProcedureType"
    assert expanded['proceduretype'][0]['submissiontype'][0]['name'] == "Default SubmissionType"


def test_pydresultstype_fields(pydresultstype_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydresultstype_created_instance.fields
    assert "name" in fields
    assert "results" in fields
    assert "proceduretype" in fields
    

def test_pydresultstype_described_fields(pydresultstype_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydresultstype_created_instance.described_fields
    # assert "name" in fields
    assert len(fields) == 0
    assert "results" not in fields
    assert "proceduretype" not in fields
    

def test_determine_field_type(pydresultstype_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydresultstype_created_instance.determine_field_type("name") == 'str'
    assert pydresultstype_created_instance.determine_field_type("proceduretype") == 'RelationshipList'
    assert pydresultstype_created_instance.determine_field_type("results") == 'RelationshipList'
    
    
def test_form_dictionary(pydresultstype_sql_instance):
    list_ = [item for item in pydresultstype_sql_instance.form_dictionary]
    # assert all(isinstance(item, dict) for item in list_)
    assert len(list_) == 0
    # name_ = next((item for item in list_ if item['field'] == "name"), None)
    # assert name_ is not None
    # assert name_['value'] == "Test ResultsType"
    # assert name_['type'] == 'STR'
    # results = next((item for item in list_ if item['field'] == "results"), None)
    # assert results is not None
    # assert results['value'] == ["Unknown Run-Unknown ProcedureType->Test Sample (rank=1)-Test ResultsType"]
    # assert results['type'] == 'SKIPPED'
    # proceduretype = next((item for item in list_ if item['field'] == "proceduretype"), None)
    # assert proceduretype is not None
    # assert proceduretype['value'] == ['Test ProcedureType']
    # assert proceduretype['type'] == 'SKIPPED'


def test_add_remove_relationship(pydresultstype_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new EquipmentLot SQL instance to relate to
    new_lot = models.procedures.Equipment(name="New Equipment", resultslot=None)
    new_lot.save()
    # Add the relationship using the Pydresultstype method
    pydresultstype_created_instance.add_relationship("results", "New Equipment")
    # Check that the new lot is now in the resultslot list
    assert any(lot == "New Equipment" for lot in pydresultstype_created_instance.results)
    # Now remove the relationship
    pydresultstype_created_instance.remove_relationship("results", "New Equipment")
    assert not any(lot == "New Equipment" for lot in pydresultstype_created_instance.results)


def test_update_instrumented_attribute(pydresultstype_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydresultstype_created_instance.update_instrumentedattribute("manufacturer", "New Manufacturer")
    assert pydresultstype_created_instance.manufacturer == "New Manufacturer"



