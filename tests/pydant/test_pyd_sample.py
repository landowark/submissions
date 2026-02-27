from datetime import timedelta, date, datetime
import pytest
from test_pyd_base import pydant, models
from sqlalchemy.ext.associationproxy import ObjectAssociationProxyInstance


@pytest.fixture(scope="function")
def pydsample_created_instance(reset_database):
    """Create a Pydsample instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Sample and Sample instances, so sql_instances
    will have all required relationships properly resolved.
    """
    result = models.Results.query(limit=1)
    sample = pydant.PydSample(
        sample_id="Bob's Sample",
        rank=1,
        row=2,
        column=3,
        enabled=True,
        results=[result.to_pydantic()],
        is_control=0,
        clientsubmission=["Test ClientSubmission"],
        run=['RSL-XX-20260202-1'],
        procedure=['Unknown Run-Unknown ProcedureType']
    )
    return sample


@pytest.fixture(scope="function")
def pydsample_sql_instance(reset_database):
    pydsample_sql_instance = models.Sample.query(name="Test Sample", limit=1)
    return pydsample_sql_instance.to_pydantic() if pydsample_sql_instance else None


def test_pydsample_creation(pydsample_created_instance):
    """Test that Pydsample properties are correctly set."""
    assert pydsample_created_instance.name == "BOB'S SAMPLE"
    assert pydsample_created_instance.rank == 1
    assert pydsample_created_instance.row == 2
    assert pydsample_created_instance.column == 3
    assert pydsample_created_instance.enabled == True
    assert len(pydsample_created_instance.results) > 0
    assert pydsample_created_instance.is_control == 0
    

def test_pydsample_to_sql(pydsample_created_instance):
    """Test that Pydsample.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydsample_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.submissions.Sample)
    assert sql_instance.name == "BOB'S SAMPLE"
    # assert "row" in sql_instance._misc_info
    # assert "column" in sql_instance._misc_info
    assert "rank" in sql_instance._misc_info
    # Test that sample is properly resolved (should not be None)
    
    assert isinstance(sql_instance.clientsubmission.parent, ObjectAssociationProxyInstance)
    assert len(sql_instance.clientsubmission) > 0
    assert all([isinstance(item, models.submissions.ClientSubmission) for item in sql_instance.clientsubmission])
    assert "Test ClientSubmission" in [c.name for c in sql_instance.clientsubmission]
    # Run
    assert isinstance(sql_instance.run.parent, ObjectAssociationProxyInstance)
    assert len(sql_instance.run) > 0
    assert all([isinstance(item, models.submissions.Run) for item in sql_instance.run])
    assert 'RSL-XX-20260202-1' in [r.name for r in sql_instance.run]
    # Procedure
    assert isinstance(sql_instance.procedure.parent, ObjectAssociationProxyInstance)
    assert len(sql_instance.procedure) > 0
    assert all([isinstance(item, models.procedures.Procedure) for item in sql_instance.procedure])
    assert 'Unknown Run-Unknown ProcedureType' in [r.name for r in sql_instance.procedure]
    # Test that sample is properly resolved (should not be None)
    assert sql_instance.is_control == 0
    

def test_pydsample_improved_dict(pydsample_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydsample_created_instance.improved_dict
    assert "sample_id" in d
    assert d['sample_id'] == "BOB'S SAMPLE"
    assert "rank" in d
    assert d['rank'] == 1
    assert "enabled" in d
    assert d['enabled'] == True
    assert "row" in d
    assert d['row'] == 2
    assert "column" in d
    assert d['column'] == 3
    assert "is_control" in d
    assert d['is_control'] == 0
    assert "clientsubmission" in d
    assert d['clientsubmission'] == ['Test ClientSubmission']
    assert "run" in d
    assert d['run'] == ['RSL-XX-20260202-1']
    assert "procedure" in d
    assert d['procedure'] == ['Unknown Run-Unknown ProcedureType']
    assert "name" in d
    assert d['name'] == d['sample_id']


def test_pydsample_expand_fields(pydsample_sql_instance):
    """Test that expand_fields properly expands sample and sample."""
    expanded = pydsample_sql_instance.improved_dict_expand_fields(["clientsubmission"])
    assert isinstance(expanded['clientsubmission'], list)
    assert expanded['clientsubmission'][0]['submitter_plate_id'] == "Test ClientSubmission"
    expanded = pydsample_sql_instance.improved_dict_expand_fields({"procedure": ['submissiontype']})
    assert isinstance(expanded['procedure'], list)
    assert expanded['procedure'][0]['name'] == "RSL-XX-20260202-1-Test ProcedureType-2026-02-25 00:00:00"
    assert expanded['procedure'][0]['submissiontype']['name'] == "Default SubmissionType"


def test_pydsample_fields(pydsample_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydsample_created_instance.fields
    assert 'is_control' in fields
    assert 'clientsubmission' in fields
    assert 'procedure' in fields
    assert 'enabled' in fields
    assert 'row' in fields
    assert 'column' in fields
    assert 'name' in fields
    assert 'rank' in fields
    assert 'sample_id' in fields
    assert 'run' in fields
    assert 'results' in fields
    

def test_pydsample_described_fields(pydsample_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydsample_created_instance.described_fields
    assert len(fields) == 0
    

def test_determine_field_type(pydsample_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydsample_created_instance.determine_field_type("is_control") == 'int'
    assert pydsample_created_instance.determine_field_type("clientsubmission") == 'ObjectAssociationProxyInstance'
    assert pydsample_created_instance.determine_field_type("run") == 'ObjectAssociationProxyInstance'
    assert pydsample_created_instance.determine_field_type("procedure") == 'ObjectAssociationProxyInstance'
    assert pydsample_created_instance.determine_field_type("sample_id") == 'str'
   
    
def test_form_dictionary(pydsample_sql_instance):
    list_ = [item for item in pydsample_sql_instance.form_dictionary]
    assert len(list_) == 0


def test_add_remove_relationship(pydsample_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new Sample SQL instance to relate to
    new_lot = models.submissions.ClientSubmission(name="New Sub")
    new_lot.save()
    # Add the relationship using the Pydsample method
    pydsample_created_instance.add_relationship("clientsubmission", "New Sub")
    # Check that the new lot is now in the sample list
    assert any([procedure == "New Sub" for procedure in pydsample_created_instance.clientsubmission])
    # Now remove the relationship
    pydsample_created_instance.remove_relationship("clientsubmission", "New Sub")
    assert not any([procedure == "New Sub" for procedure in pydsample_created_instance.clientsubmission])


def test_update_instrumented_attribute(pydsample_created_instance):
    """Test that updating an SolutionedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydsample_created_instance.update_instrumentedattribute("sample_id", "New ID")
    assert pydsample_created_instance.sample_id == "NEW ID"



