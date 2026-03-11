from datetime import datetime, date, timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydresults_created_instance(reset_database):
    """Create a Pydresults instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created Results and EquipmentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    results = pydant.PydResults(
        result = dict(test="Positive", passed=True),
        resultstype="Test ResultsType",
        image=None,
        procedure="Unknown Run-Unknown ProcedureType",
        sample="Unknown Run-Unknown ProcedureType->Test Sample (rank=1)",
        date_analyzed=datetime.combine(date=date(2026, 2, 25), time=datetime.min.time())
    )
    return results


@pytest.fixture(scope="function")
def pydresults_sql_instance(reset_database):
    pydresults_sql_instance = models.Results.query(name="Unknown Run-Unknown ProcedureType-Test ResultsType", limit=1)
    return pydresults_sql_instance.to_pydantic() if pydresults_sql_instance else None


def test_pydresults_creation(pydresults_created_instance):
    """Test that Pydresults properties are correctly set."""
    assert pydresults_created_instance.name == "Unknown Run-Unknown ProcedureType-Test ResultsType"
    
    assert pydresults_created_instance.resultstype == "Test ResultsType"
    assert pydresults_created_instance.procedure == "Unknown Run-Unknown ProcedureType"
    assert pydresults_created_instance.image is None
    assert pydresults_created_instance.sample == "Unknown Run-Unknown ProcedureType->Test Sample (rank=1)"
    assert pydresults_created_instance.date_analyzed.strftime("%Y-%m-%d") == "2026-02-25"
        

def test_pydresults_to_sql(pydresults_created_instance):
    """Test that Pydresults.to_sql() properly converts to SQL Equipment with relationships."""
    sql_instance = pydresults_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.Results)
    # Test that results is properly resolved (should not be None)
    assert sql_instance.resultstype is not None
    assert isinstance(sql_instance.resultstype, models.procedures.ResultsType)
    assert sql_instance.resultstype.name == "Test ResultsType"
    # Test that clientsubmission is properly resolved (should not be None)
    assert sql_instance.procedure is not None
    assert isinstance(sql_instance.procedure, models.submissions.Procedure)
    assert sql_instance.procedure.name == "Unknown Run-Unknown ProcedureType"
    # Test that clientsubmission is properly resolved (should not be None)
    assert sql_instance.sampleprocedureassociation is not None
    assert isinstance(sql_instance.sampleprocedureassociation, models.submissions.ProcedureSampleAssociation)
    assert sql_instance.sampleprocedureassociation.name == "Unknown Run-Unknown ProcedureType->Test Sample (rank=1)"
    # misc
    assert sql_instance.image is None
    assert sql_instance.date_analyzed.strftime("%Y-%m-%d") == "2026-02-25"
    

def test_pydresults_improved_dict(pydresults_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydresults_created_instance.improved_dict
    assert "resultstype" in d
    assert d['resultstype'] == "Test ResultsType"
    assert "procedure" in d
    assert d['procedure'] == "Unknown Run-Unknown ProcedureType" 
    assert "result" in d
    assert d['result']['test'] == "Positive"
    assert d['result']
    assert "image" in d
    assert d['image'] is None
    assert "date_analyzed" in d
    assert d['date_analyzed'].strftime("%Y-%m-%d") == "2026-02-25"


def test_pydresults_expand_fields(pydresults_sql_instance):
    """Test that expand_fields properly expands results and resultslot."""
    expanded = pydresults_sql_instance.improved_dict_expand_fields(["procedure"])
    # NOTE: validation error downstream converting the clientsubmission - run - procedure (no sample.row or sample.column)
    assert isinstance(expanded['procedure'], dict)
    t = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert expanded['procedure']['name'] == {'missing': False, 'value': f'RSL-XX-20260202-1-Test ProcedureType-{t}'}
    expanded = pydresults_sql_instance.improved_dict_expand_fields({"resultstype": ['proceduretype']})
    assert isinstance(expanded['resultstype'], dict)
    assert expanded['resultstype']['name'] == "Test ResultsType"
    assert expanded['resultstype']['proceduretype'][0]['name'] == "Test ProcedureType"


def test_pydresults_fields(pydresults_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydresults_created_instance.fields
    assert "name" in fields
    assert "procedure" in fields
    assert "resultstype" in fields
    assert "result" in fields
    assert "date_analyzed" in fields
    

def test_pydresults_described_fields(pydresults_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydresults_created_instance.described_fields
    assert len(fields) == 0
    

def test_determine_field_type(pydresults_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    
    assert pydresults_created_instance.determine_field_type("resultstype") == "RelationshipScalar"
    assert pydresults_created_instance.determine_field_type("procedure") == "RelationshipScalar"
    assert pydresults_created_instance.determine_field_type("result") == 'dict'
    assert pydresults_created_instance.determine_field_type("date_analyzed") == "datetime"
    assert pydresults_created_instance.determine_field_type("sampleprocedureassociation") == "RelationshipScalar"
    assert pydresults_created_instance.determine_field_type("image") == "property"
    
    
def test_form_dictionary(pydresults_sql_instance):
    list_ = [item for item in pydresults_sql_instance.form_dictionary]
    # assert all(isinstance(item, dict) for item in list_)
    assert len(list_) == 0
    

def test_update_instrumented_attribute(pydresults_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydresults_created_instance.update_instrumentedattribute("result", dict(hi="ho"))
    assert pydresults_created_instance.result == dict(hi="ho")



