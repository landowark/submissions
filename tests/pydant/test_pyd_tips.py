from datetime import timedelta
import pytest
from test_pyd_base import pydant, models


@pytest.fixture(scope="function")
def pydtips_created_instance(reset_database):
    """Create a PydTips instance for testing.
    
    Uses the toy database populated by conftest.py which includes
    pre-created ReagentRole and ReagentLot instances, so sql_instances
    will have all required relationships properly resolved.
    """
    tips = pydant.PydTips(
        tipslot=["Test TipsLot"],
        manufacturer="Acme Corp",
        ref="AC12345",
        capacity=100,
        process=["Test Process"],
        cost_per_tip=0.05
    )
    return tips


@pytest.fixture(scope="function")
def pydtips_sql_instance(reset_database):
    pydtips_sql_instance = models.Tips.query(name="ACME Tips-XXXX(1000uL)", limit=1)
    return pydtips_sql_instance.to_pydantic() if pydtips_sql_instance else None


def test_pydtips_creation(pydtips_created_instance):
    """Test that Pydtips properties are correctly set."""
    assert pydtips_created_instance.name == "Acme Corp-AC12345(100uL)"
    assert pydtips_created_instance.capacity == 100
    assert pydtips_created_instance.tipslot == ["Test TipsLot"]
    assert pydtips_created_instance.manufacturer == "Acme Corp"
    assert pydtips_created_instance.ref == "AC12345"
    assert pydtips_created_instance.process == ["Test Process"]
    assert pydtips_created_instance.cost_per_tip == 0.05


def test_pydtips_to_sql(pydtips_created_instance):
    """Test that Pydtips.to_sql() properly converts to SQL Reagent with relationships."""
    sql_instance = pydtips_created_instance.to_sql()
    assert isinstance(sql_instance, tuple)
    if isinstance(sql_instance, tuple):
        sql_instance = sql_instance[0]
    assert isinstance(sql_instance, models.procedures.Tips)
    # Test that reagentrole is properly resolved (should not be None)
    assert sql_instance.process is not None
    assert len(sql_instance.process) > 0
    assert isinstance(sql_instance.process[0], models.procedures.Process)
    assert sql_instance.process[0].name == "Test Process"
    # Test that reagentlot is properly resolved (should not be None)
    assert sql_instance.tipslot is not None
    assert len(sql_instance.tipslot) > 0
    assert isinstance(sql_instance.tipslot[0], models.procedures.TipsLot)
    assert sql_instance.tipslot[0].lot == "098765"
    # assert isinstance(sql_instance.eol_ext, timedelta)


def test_pydtips_improved_dict(pydtips_created_instance):
    """Test that the improved_dict property includes all fields."""
    d = pydtips_created_instance.improved_dict
    assert "name" in d
    assert d['name'] == "Acme Corp-AC12345(100uL)"
    assert "manufacturer" in d
    assert d['manufacturer'] == "Acme Corp"
    assert "ref" in d
    assert d['ref'] == "AC12345"
    assert "manufacturer" in d
    assert d['manufacturer'] == "Acme Corp"
    assert "ref" in d
    assert d['ref'] == "AC12345"
    assert "cost_per_tip" in d
    assert d['cost_per_tip'] == 0.05
    assert "tipslot" in d
    assert d['tipslot'] == ["Test TipsLot"]


def test_pydtips_expand_fields(pydtips_sql_instance):
    """Test that expand_fields properly expands reagentrole and reagentlot."""
    expanded = pydtips_sql_instance.improved_dict_expand_fields(["tipslot"])
    assert isinstance(expanded['tipslot'], list)
    assert expanded['tipslot'][0]['name'] == "ACME Tips - XXXX - 098765"
    expanded = pydtips_sql_instance.improved_dict_expand_fields({"process": ['processversion']})
    assert isinstance(expanded['process'], list)
    assert expanded['process'][0]['name'] == "Test Process"
    assert expanded['process'][0]['processversion'][0]['version'] == 1.0


def test_pydtips_fields(pydtips_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydtips_created_instance.fields
    assert "name" in fields
    assert "manufacturer" in fields
    assert "ref" in fields
    assert "cost_per_tip" in fields
    assert "capacity" in fields


def test_pydtips_described_fields(pydtips_created_instance):
    """Test that the fields property lists all field names."""
    fields = pydtips_created_instance.described_fields
    assert "tipslot" in fields
    assert "process" in fields
    assert "manufacturer" in fields
    assert "ref" in fields
    assert "cost_per_tip" in fields
    assert "capacity" in fields
    

def test_determine_field_type(pydtips_created_instance):
    """Test that determine_field_type correctly identifies field types."""
    assert pydtips_created_instance.determine_field_type("tipslot") == 'RelationshipList'
    assert pydtips_created_instance.determine_field_type("process") == 'RelationshipList'
    assert pydtips_created_instance.determine_field_type("manufacturer") == 'str'
    assert pydtips_created_instance.determine_field_type("ref") == 'str'
    assert pydtips_created_instance.determine_field_type("cost_per_tip") == 'float'
    assert pydtips_created_instance.determine_field_type("capacity") == 'int'
    

def test_form_dictionary(pydtips_sql_instance):
    list_ = [item for item in pydtips_sql_instance.form_dictionary]
    assert all(isinstance(item, dict) for item in list_)
    # name_ = next((item for item in list_ if item['field'] == "name"), None)
    # assert name_ is not None
    # assert name_['value'] == "Test Solution"
    # assert name_['type'] == 'STR'
    tipslot = next((item for item in list_ if item['field'] == "tipslot"), None)
    assert tipslot is not None
    assert tipslot['value'] == ["ACME Tips - XXXX - 098765"]
    assert tipslot['type'] == 'RELATIONSHIPLIST'
    capacity = next((item for item in list_ if item['field'] == "capacity"), None)
    assert capacity is not None
    assert capacity['value'] == 1000
    assert capacity['type'] == 'INT'
    manufacturer = next((item for item in list_ if item['field'] == "manufacturer"), None)
    assert manufacturer is not None
    assert manufacturer['value'] == "ACME Tips"
    assert manufacturer['type'] == 'STR'
    ref = next((item for item in list_ if item['field'] == "ref"), None)
    assert ref is not None
    assert ref['value'] == "XXXX"
    assert ref['type'] == 'STR'
    cost_per_tip = next((item for item in list_ if item['field'] == "cost_per_tip"), None)
    assert cost_per_tip is not None
    assert cost_per_tip['value'] == 0.02
    assert cost_per_tip['type'] == 'FLOAT'
    process = next((item for item in list_ if item['field'] == "process"), None)
    assert process is not None
    assert process['value'] == ['Test Process']
    assert process['type'] == 'RELATIONSHIPLIST'


def test_add_remove_relationship(pydtips_created_instance):
    """Test that add_relationship properly adds a related SQL instance."""
    # Create a new ReagentLot SQL instance to relate to
    new_lot = models.procedures.Process(name="New Process", processversion=None)
    new_lot.save()
    # Add the relationship using the Pydtips method
    pydtips_created_instance.add_relationship("process", "New Process")
    # Check that the new lot is now in the reagentlot list
    assert any(lot == "New Process" for lot in pydtips_created_instance.process)
    # Now remove the relationship
    pydtips_created_instance.remove_relationship("process", "New Process")
    assert not any(lot == "New Process" for lot in pydtips_created_instance.process)


def test_update_instrumented_attribute(pydtips_created_instance):
    """Test that updating an InstrumentedAttribute field works correctly."""
    # Update the manufacturer field, which is a simple string
    pydtips_created_instance.update_instrumentedattribute("manufacturer", "New Manufacturer")
    assert pydtips_created_instance.manufacturer == "New Manufacturer"



