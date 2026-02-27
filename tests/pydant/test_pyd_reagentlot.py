from datetime import timedelta, date, datetime
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydreagentlot_created_instance(reset_database):
    """Create a Pydreagentlot instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created ReagentLot and ReagentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    reagentlot = pydant.PydReagentLot(
        lot="Bob's ReagentLot",
        reagent="Test Solution",
        reagentrole="Test ReagentRole",
        expiry=datetime.combine(date=date(2026, 2, 25), time=datetime.min.time()),
        missing=False,
        active=True,
        procedure=["Test Procedure"]
    )
    return reagentlot


@pytest.fixture(scope="function")
def pydreagentlot_sql_instance(reset_database):
    pydreagentlot_sql_instance = models.ReagentLot.query(name="Test Solution - 012345", limit=1)
    return pydreagentlot_sql_instance.to_pydantic() if pydreagentlot_sql_instance else None


def test_pydreagentlot_creation(pydreagentlot_created_instance):
    """Test that Pydreagentlot properties are correctly set."""
    assert pydreagentlot_created_instance.name == "Test Solution - Bob's ReagentLot"
    assert pydreagentlot_created_instance.reagent == "Test Solution"
    assert pydreagentlot_created_instance.reagentrole == "Test ReagentRole"
    assert pydreagentlot_created_instance.expiry.strftime("%Y-%m-%d") == "2026-02-25"
    assert pydreagentlot_created_instance.missing == False
    assert pydreagentlot_created_instance.active == True
    

def test_pydreagentlot_to_sql(pydreagentlot_created_instance):
    """Test that Pydreagentlot.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydreagentlot_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ReagentLot)
    # Test that reagentlot is properly resolved (should not be None)
    # assert sql_instance.reagentrole is not None
    # assert isinstance(sql_instance.reagentrole, models.procedures.ReagentRole)
    # assert sql_instance.reagentrole.name == "Test ReagentRole"
    # Test that reagentlot is properly resolved (should not be None)
    assert sql_instance.reagent is not None
    # assert len(sql_instance.reagent) > 0
    assert isinstance(sql_instance.reagent, models.procedures.Reagent)
    assert sql_instance.reagent.name == "Test Solution"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydreagentlot_improved_dict(pydreagentlot_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydreagentlot_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Test Solution - Bob's ReagentLot"
    assert "reagent" in d
    assert d['reagent'] == "Test Solution"
    assert "reagentrole" in d
    assert d['reagentrole'] == "Test ReagentRole"


def test_pydreagentlot_expand_fields(pydreagentlot_sql_instance):
    """Test that expand_fields properly expands reagentlot and reagentlot."""
    expanded = pydreagentlot_sql_instance.improved_dict_expand_fields(["reagent"])
    assert isinstance(expanded['reagent'], dict)
    assert expanded['reagent']['name'] == "Test Solution"
    expanded = pydreagentlot_sql_instance.improved_dict_expand_fields({"procedure": ['submissiontype']})
    assert isinstance(expanded['procedure'], list)
    assert expanded['procedure'][0]['name'] == "RSL-XX-20260202-1-Test ProcedureType-2026-02-25 00:00:00"
    assert expanded['procedure'][0]['submissiontype']['name'] == "Default SubmissionType"


def test_pydreagentlot_fields(pydreagentlot_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagentlot_created_instance.fields
    assert "name" in fields
    assert "reagent" in fields
    assert "procedure" in fields
    assert "active" in fields
    assert "expiry" in fields
    assert "lot" in fields
    

def test_pydreagentlot_described_fields(pydreagentlot_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydreagentlot_created_instance.described_fields
    assert "lot" in fields
    assert "reagent" in fields
    assert "expiry" in fields
    assert "active" in fields
    assert "procedure" not in fields
    
    

def test_determine_field_type(pydreagentlot_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydreagentlot_created_instance.determine_field_type("lot") == 'str'
    assert pydreagentlot_created_instance.determine_field_type("reagent") == 'RelationshipScalar'
    assert pydreagentlot_created_instance.determine_field_type("expiry") == 'datetime'
    assert pydreagentlot_created_instance.determine_field_type("active") == 'bool'
    
    
def test_form_dictionary(pydreagentlot_sql_instance):
    list_ = [item for item in pydreagentlot_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    lot = next((item for item in list_ if item['field'] == "lot"), None)
    assert lot is not None
    assert lot['value'] == "012345"
    assert lot['type'] == 'STR'
    reagent = next((item for item in list_ if item['field'] == "reagent"), None)
    assert reagent is not None
    assert reagent['value'] == "Test Solution"
    assert reagent['type'] == 'RELATIONSHIPSCALAR'
    expiry = next((item for item in list_ if item['field'] == "expiry"), None)
    assert expiry is not None
    assert expiry['value'].strftime("%Y-%m-%d") == (date.today() + timedelta(days=365)).strftime("%Y-%m-%d")
    assert expiry['type'] == 'DATETIME'
    active = next((item for item in list_ if item['field'] == "active"), None)
    assert active is not None
    assert active['value'] == True
    assert active['type'] == 'BOOL'


# def test_add_remove_relationship(pydreagentlot_created_instance):
#     """Test that add_relationship properly adds a related SQL instance."""
#     # Create a new ReagentLot SQL instance to relate to
#     new_lot = models.procedures.Procedure(name="My Procedure", run="Test Run")
#     new_lot.save()
#     # Add the relationship using the Pydreagentlot method
#     pydreagentlot_created_instance.add_relationship("procedure", "New Procedure")
#     # Check that the new lot is now in the reagentlot list
#     assert any(procedure == "New Procedure" for procedure in pydreagentlot_created_instance.procedure)
#     # Now remove the relationship
#     pydreagentlot_created_instance.remove_relationship("procedure", "New Procedure")
#     assert not any(procedure == "New Procedure" for procedure in pydreagentlot_created_instance.procedure)


def test_update_instrumented_attribute(pydreagentlot_created_instance):
    """Test that updating an SolutionedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydreagentlot_created_instance.update_instrumentedattribute("lot", "New Lot")
    assert pydreagentlot_created_instance.lot == "New Lot"



