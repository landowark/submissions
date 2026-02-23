from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydsubmissiontype_created_instance(reset_database):
    """Create a Pydsubmissiontype instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created SubmissionType and EquipmentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    submissiontype = pydant.PydSubmissionType(
        name="Bob's SubmissionType",
        defaults={"test_key": "test_value"},
        file_name_template="{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}",
        turnaround_time = 3,
        abbreviation = "BST",
        clientsubmission=["Test ClientSubmission"],
        proceduretype=["Test ProcedureType"]
    )
    return submissiontype


@pytest.fixture(scope="function")
def pydsubmissiontype_sql_instance(reset_database):
    pydsubmissiontype_sql_instance = models.SubmissionType.query(name="Default SubmissionType", limit=1)
    return pydsubmissiontype_sql_instance.to_pydantic() if pydsubmissiontype_sql_instance else None


def test_pydsubmissiontype_creation(pydsubmissiontype_created_instance):
    """Test that Pydsubmissiontype properties are correctly set."""
    assert pydsubmissiontype_created_instance.name == "Bob's SubmissionType"
    
    assert pydsubmissiontype_created_instance.proceduretype == ["Test ProcedureType"]
    assert pydsubmissiontype_created_instance.clientsubmission == ["Test ClientSubmission"]
    assert pydsubmissiontype_created_instance.file_name_template == "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
    assert pydsubmissiontype_created_instance.turnaround_time == 3
    assert pydsubmissiontype_created_instance.abbreviation == "BST"
    assert pydsubmissiontype_created_instance.defaults == {"test_key": "test_value"}
    

def test_pydsubmissiontype_to_sql(pydsubmissiontype_created_instance):
    """Test that Pydsubmissiontype.to_sql() properly converts to SQL Equipment with relationships."""
    sql_instance = pydsubmissiontype_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.SubmissionType)
    # Test that submissiontype is properly resolved (should not be None)
    assert sql_instance.proceduretype is not None
    assert len(sql_instance.proceduretype) > 0
    assert isinstance(sql_instance.proceduretype[0], models.procedures.ProcedureType)
    assert sql_instance.proceduretype[0].name == "Test ProcedureType"
    # Test that clientsubmission is properly resolved (should not be None)
    assert sql_instance.clientsubmission is not None
    assert len(sql_instance.clientsubmission) > 0
    assert isinstance(sql_instance.clientsubmission[0], models.submissions.ClientSubmission)
    assert sql_instance.clientsubmission[0].name == "Test ClientSubmission"
    # misc
    assert sql_instance.file_name_template == "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
    assert sql_instance.turnaround_time == timedelta(days=3)
    assert sql_instance.abbreviation == "BST"
    assert sql_instance.defaults is None # This field gets filtered out by PydSubmissionType.filter_field


def test_pydsubmissiontype_improved_dict(pydsubmissiontype_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydsubmissiontype_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Bob's SubmissionType"
    assert "proceduretype" in d
    assert d['proceduretype'] == ["Test ProcedureType"]
    assert "clientsubmission" in d
    assert "Test ClientSubmission" in d['clientsubmission'] 
    assert "file_name_template" in d
    assert d['file_name_template'] == "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}"
    assert "turnaround_time" in d
    assert d['turnaround_time'] == 3
    assert "abbreviation" in d
    assert d['abbreviation'] == "BST"
    assert "defaults" in d
    # NOTE: This field gets filtered out by PydSubmissionType.filter_field
    assert d['defaults'] is None


def test_pydsubmissiontype_expand_fields(pydsubmissiontype_sql_instance):
    """Test that expand_fields properly expands submissiontype and resultslot."""
    expanded = pydsubmissiontype_sql_instance.improved_dict_expand_fields(["clientsubmission"])
    # NOTE: validation error downstream converting the clientsubmission - run - procedure (no sample.row or sample.column)
    assert isinstance(expanded['clientsubmission'], list)
    assert expanded['clientsubmission'][0]['name'] == "Test ClientSubmission"
    expanded = pydsubmissiontype_sql_instance.improved_dict_expand_fields({"proceduretype": ['equipmentrole']})
    assert isinstance(expanded['proceduretype'], list)
    assert expanded['proceduretype'][0]['name'] == "Test ProcedureType"
    assert expanded['proceduretype'][0]['equipmentrole'][0]['name'] == "Test EquipmentRole"


def test_pydsubmissiontype_fields(pydsubmissiontype_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydsubmissiontype_created_instance.fields
    assert "name" in fields
    assert "proceduretype" in fields
    assert "clientsubmission" in fields
    assert "file_name_template" in fields
    assert "turnaround_time" in fields
    assert "abbreviation" in fields
    assert "defaults" not in fields
    

def test_pydsubmissiontype_described_fields(pydsubmissiontype_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydsubmissiontype_created_instance.described_fields
    assert "name" in fields
    assert "proceduretype" in fields
    assert "clientsubmission" not in fields
    assert "file_name_template" not in fields
    assert "turnaround_time" in fields
    assert "abbreviation" in fields
    assert "defaults" not in fields
    

def test_determine_field_type(pydsubmissiontype_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydsubmissiontype_created_instance.determine_field_type("name") == 'str'
    assert pydsubmissiontype_created_instance.determine_field_type("proceduretype") == "RelationshipList"
    assert pydsubmissiontype_created_instance.determine_field_type("clientsubmission") == "RelationshipList"
    assert pydsubmissiontype_created_instance.determine_field_type("file_name_template") == 'str'
    assert pydsubmissiontype_created_instance.determine_field_type("turnaround_time") == "int"
    assert pydsubmissiontype_created_instance.determine_field_type("abbreviation") == "str"
    assert pydsubmissiontype_created_instance.determine_field_type("defaults") == "dict"
    
    
def test_form_dictionary(pydsubmissiontype_sql_instance):
    list_ = [item for item in pydsubmissiontype_sql_instance.form_dictionary]
    # assert all(isinstance(item, dict) for item in list_)
    assert len(list_) > 0
    name_ = next((item for item in list_ if item['field'] == "name"), None)
    assert name_ is not None
    assert name_['value'] == "Default SubmissionType"
    assert name_['type'] == 'STR'
    turnaround_time = next((item for item in list_ if item['field'] == "turnaround_time"), None)
    assert turnaround_time is not None
    assert turnaround_time['value'] == 5
    assert turnaround_time['type'] == 'INT'
    abbreviation = next((item for item in list_ if item['field'] == "abbreviation"), None)
    assert abbreviation is not None
    assert abbreviation['value'] == "XX"
    assert abbreviation['type'] == 'STR'
    proceduretype = next((item for item in list_ if item['field'] == "proceduretype"), None)
    assert proceduretype is not None
    assert proceduretype['value'] == ['Test ProcedureType']
    assert proceduretype['type'] == 'RELATIONSHIPLIST'


def test_add_remove_relationship(pydsubmissiontype_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new EquipmentLot SQL instance to relate to
    new_lot = models.submissions.ClientSubmission(name="New Equipment")
    new_lot.save()
    # Add the relationship using the Pydsubmissiontype method
    pydsubmissiontype_created_instance.add_relationship("clientsubmission", "New Equipment")
    # Check that the new lot is now in the resultslot list
    assert any(name == "New Equipment" for name in pydsubmissiontype_created_instance.clientsubmission)
    # Now remove the relationship
    pydsubmissiontype_created_instance.remove_relationship("clientsubmission", "New Equipment")
    assert not any(lot == "New Equipment" for lot in pydsubmissiontype_created_instance.clientsubmission)


def test_update_instrumented_attribute(pydsubmissiontype_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydsubmissiontype_created_instance.update_instrumentedattribute("abbreviation", "New Manufacturer")
    assert pydsubmissiontype_created_instance.abbreviation == "New Manufacturer"



