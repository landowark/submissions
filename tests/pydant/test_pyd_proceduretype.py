from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydproceduretype_created_instance(reset_database):
    """Create a PydProcedureType instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created ReagentRole and ReagentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    proceduretype = pydant.PydProcedureType(
        name="Bob's ProcedureType",
        plate_columns=12,
        plate_rows=8,
        plate_cost=3.50,
        procedure=["Unknown Run-Unknown ProcedureType"],
        submissiontype=["Default SubmissionType"],
        resultstype=["Test ResultsType"],
        equipmentrole=["Test EquipmentRole"],
        reagentrole=["Test ReagentRole"]
        
    )
    return proceduretype


@pytest.fixture(scope="function")
def pydproceduretype_sql_instance(reset_database):
    pydproceduretype_sql_instance = models.ProcedureType.query(name="Test ProcedureType", limit=1)
    return pydproceduretype_sql_instance.to_pydantic() if pydproceduretype_sql_instance else None


def test_pydproceduretype_creation(pydproceduretype_created_instance):
    """Test that PydProcedureType properties are correctly set."""
    assert pydproceduretype_created_instance.name == "Bob's ProcedureType"
    assert pydproceduretype_created_instance.plate_columns == 12
    assert pydproceduretype_created_instance.plate_rows == 8
    assert pydproceduretype_created_instance.plate_cost == 3.50
    assert "Unknown Run-Unknown ProcedureType" in pydproceduretype_created_instance.procedure 
    assert "Default SubmissionType" in pydproceduretype_created_instance.submissiontype 
    assert "Test ResultsType" in pydproceduretype_created_instance.resultstype
    assert "Test EquipmentRole" in pydproceduretype_created_instance.equipmentrole
    assert "Test ReagentRole"  in pydproceduretype_created_instance.reagentrole


def test_pydproceduretype_to_sql(pydproceduretype_created_instance):
    """Test that PydProcedureType.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydproceduretype_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.ProcedureType)
    # Test that reagentrole is properly resolved (should not be None)
    assert sql_instance.procedure is not None
    assert len(sql_instance.procedure) > 0
    assert isinstance(sql_instance.procedure[0], models.procedures.Procedure)
    assert sql_instance.procedure[0].name == "Unknown Run-Unknown ProcedureType"
    # Test that reagentlot is properly resolved (should not be None)
    assert sql_instance.resultstype is not None
    assert len(sql_instance.resultstype) > 0
    assert isinstance(sql_instance.resultstype[0], models.procedures.ResultsType)
    assert sql_instance.resultstype[0].name == "Test ResultsType"
    # assert isinstance(sql_instance.eol_ext, timedelta)
    # Test that reagentlot is properly resolved (should not be None)
    assert sql_instance.submissiontype is not None
    assert isinstance(sql_instance.submissiontype, models.procedures.SubmissionType)
    assert sql_instance.submissiontype.name == "Default SubmissionType"
    # 
    assert sql_instance.equipmentrole is not None
    assert len(sql_instance.equipmentrole) > 0
    assert isinstance(sql_instance.equipmentrole[0], models.procedures.EquipmentRole)
    assert sql_instance.equipmentrole[0].name == "Test EquipmentRole"
    # 
    assert sql_instance.reagentrole is not None
    assert len(sql_instance.reagentrole) > 0
    assert isinstance(sql_instance.reagentrole[0], models.procedures.ReagentRole)
    assert sql_instance.reagentrole[0].name == "Test ReagentRole"


def test_pydproceduretype_improved_dict(pydproceduretype_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydproceduretype_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's ProcedureType"
    assert "plate_columns" in d
    assert d['plate_columns'] == 12
    assert "plate_rows" in d
    assert d['plate_rows'] == 8
    assert "plate_cost" in d
    assert d['plate_cost'] == 3.50
    assert "procedure" in d
    assert "Unknown Run-Unknown ProcedureType" in d['procedure']
    assert "submissiontype" in d
    assert "Default SubmissionType" in d['submissiontype']
    assert "resultstype" in d
    assert "Test ResultsType" in d['resultstype'] 
    assert "equipmentrole" in d
    assert "Test EquipmentRole" in d['equipmentrole']
    assert "reagentrole" in d
    assert "Test ReagentRole" in d['reagentrole'] 


def test_pydproceduretype_expand_fields(pydproceduretype_sql_instance):
    """Test that expand_fields properly expands reagentrole and reagentlot."""
    expanded = pydproceduretype_sql_instance.improved_dict_expand_fields(["equipmentrole"])
    assert isinstance(expanded['equipmentrole'], list)
    assert expanded['equipmentrole'][0]['name'] == "Test EquipmentRole"
    expanded = pydproceduretype_sql_instance.improved_dict_expand_fields({"reagentrole": ['reagent']})
    assert isinstance(expanded['reagentrole'], list)
    assert expanded['reagentrole'][0]['name'] == "Test ReagentRole"
    assert expanded['reagentrole'][0]['reagent'][0]['name'] == "Test Solution"


def test_pydproceduretype_fields(pydproceduretype_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydproceduretype_created_instance.fields
    assert "procedure" in fields
    assert "proceduretypeequipmentroleassociation" not in fields
    assert "proceduretypereagentroleassociation" not in fields
    assert "equipmentrole" in fields
    assert "plate_columns" in fields
    assert "plate_rows" in fields
    assert "reagentrole" in fields
    assert "resultstype" in fields
    assert "discount" not in fields
    assert "submissiontype" in fields
    assert "excluded" not in fields
    assert "name" in fields


def test_pydproceduretype_described_fields(pydproceduretype_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydproceduretype_created_instance.described_fields
    assert "equipmentrole" in fields
    assert "plate_columns" in fields
    assert "plate_rows" in fields
    assert "reagentrole" in fields
    assert "resultstype" in fields
    assert "submissiontype" in fields
    assert "name" in fields
    

def test_determine_field_type(pydproceduretype_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydproceduretype_created_instance.determine_field_type("name") == 'str'
    assert pydproceduretype_created_instance.determine_field_type("plate_columns") == 'int'
    assert pydproceduretype_created_instance.determine_field_type("plate_rows") == 'int'
    assert pydproceduretype_created_instance.determine_field_type("plate_cost") == 'float'
    assert pydproceduretype_created_instance.determine_field_type("submissiontype") == 'RelationshipList'
    assert pydproceduretype_created_instance.determine_field_type("resultstype") == 'RelationshipList'
    assert pydproceduretype_created_instance.determine_field_type("equipmentrole") == 'ObjectAssociationProxyInstance'
    assert pydproceduretype_created_instance.determine_field_type("reagentrole") == 'ObjectAssociationProxyInstance'
    

def test_form_dictionary(pydproceduretype_sql_instance):
    list_ = [item for item in pydproceduretype_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    # name_ = next((item for item in list_ if item['field'] == "name"), None)
    # assert name_ is not None
    # assert name_['value'] == "Test Solution"
    # assert name_['type'] == 'STR'
    name = next((item for item in list_ if item['field'] == "name"), None)
    assert name is not None
    assert name['value'] == "Test ProcedureType"
    assert name['type'] == 'STR'
    plate_columns = next((item for item in list_ if item['field'] == "plate_columns"), None)
    assert plate_columns is not None
    assert plate_columns['value'] == 12
    assert plate_columns['type'] == 'INT'
    plate_rows = next((item for item in list_ if item['field'] == "plate_rows"), None)
    assert plate_rows is not None
    assert plate_rows['value'] == 8
    assert plate_rows['type'] == 'INT'
    plate_cost = next((item for item in list_ if item['field'] == "plate_cost"), None)
    assert plate_cost is not None
    assert plate_cost['value'] == 1.00
    assert plate_cost['type'] == 'FLOAT'
    submissiontype = next((item for item in list_ if item['field'] == "submissiontype"), None)
    assert submissiontype is not None
    assert "Default SubmissionType" in submissiontype['value'] 
    assert submissiontype['type'] == 'RELATIONSHIPLIST'

    resultstype = next((item for item in list_ if item['field'] == "resultstype"), None)
    assert resultstype is not None
    assert "Test ResultsType" in resultstype['value']
    assert resultstype['type'] == 'RELATIONSHIPLIST'

    equipmentrole = next((item for item in list_ if item['field'] == "equipmentrole"), None)
    assert equipmentrole is not None
    assert "Test EquipmentRole" in equipmentrole['value']
    assert equipmentrole['type'] == 'SKIPPED'
    reagentrole = next((item for item in list_ if item['field'] == "reagentrole"), None)
    assert reagentrole is not None
    assert "Test ReagentRole" in reagentrole['value']
    assert reagentrole['type'] == 'SKIPPED'


def test_add_remove_relationship(pydproceduretype_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new ReagentLot SQL instance to relate to
    new_lot = models.procedures.EquipmentRole(name="New EquipmentRole")
    new_lot.save()
    # Add the relationship using the PydProcedureType method
    pydproceduretype_created_instance.add_relationship("equipmentrole", "New EquipmentRole")
    # Check that the new lot is now in the reagentlot list
    assert any(name == "New EquipmentRole" for name in pydproceduretype_created_instance.equipmentrole)
    # Now remove the relationship
    pydproceduretype_created_instance.remove_relationship("equipmentrole", "New EquipmentRole")
    assert not any(name == "New EquipmentRole" for name in pydproceduretype_created_instance.equipmentrole)


def test_update_instrumented_attribute(pydproceduretype_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydproceduretype_created_instance.update_instrumentedattribute("name", "New Name")
    assert pydproceduretype_created_instance.name == "New Name"



