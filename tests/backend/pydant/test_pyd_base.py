import datetime
import pytest
import sys
if "C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
from backend.validators import pydant
from backend.db import models
from pydantic import Field


class classproperty(property):
    """
    Allows for properties on classes as well as objects.
    """
    def __init__(self, f):
        self.f = f
    def __get__(self, obj, cls=None):
        if cls is None:
            cls = type(obj)
        return self.f(cls)


def test_baseclass_creation(reset_database):
    """Test that we can create an instance of PydBaseClass with the test database."""
    instance = pydant.PydBaseClass()
    assert isinstance(instance, pydant.PydBaseClass)
    assert isinstance(instance.sql_instance, models.BaseClass)


@pytest.fixture(scope="function")
def baseclass_instance(reset_database):
    """
    Create a concrete subclass of PydBaseClass for testing.
    
    This fixture uses the toy database populated by conftest.py, ensuring
    that sql_instances are properly bound to the test database session.
    """
    class PydConcreteBaseClass(pydant.PydBaseClass):

        test_dict: Field(default_factory=dict, repr=False)
        described_field: str = Field(default="NA", description="A field with a description.")
        
        @property
        def constructed_name(self) -> str:
            return "ConcreteBaseClass"
        
        @classproperty
        def _sql_name(cls) -> str:
            return "BaseClass"

        @classproperty
        def _sql_class(cls) -> models.BaseClass:
            # Lazy import here to reduce the chance of circular-import issues
            # (models may import pydant elsewhere during package import).
            try:
                return getattr(models, cls._sql_name)
           
            except AttributeError as e:
                # Provide a clearer error message listing available top-level
                # model names to help debugging name mismatches / import order.
                available = [n for n in dir(models) if not n.startswith("_")]
                raise AttributeError(
                    f"SQL model '{cls._sql_name}' not found on backend.db.models. "
                    f"Available top-level attributes: {available}") from e
        
    instance = PydConcreteBaseClass(test_dict={"value": 1, "name": 2}, bob="bob")
    return instance


def test_filter_fields(baseclass_instance):
    filtered = baseclass_instance.filter_field("test_dict")
    assert filtered == 1

def test_improved_dict(baseclass_instance):
    d = baseclass_instance.improved_dict
    assert "test_dict" in d
    assert d["test_dict"] == 1
    assert "bob" in d
    assert "described_field" in d

# def test_improved_dict_expand_fields(baseclass_instance):
#     d = baseclass_instance.improved_dict_expand_fields(fields=["test_dict"])
#     assert "test_dict" in d
#     assert d["test_dict"] == {"value": 1, "name": 2}

def test_fields(baseclass_instance):
    fields = baseclass_instance.fields
    assert "test_dict" in fields
    assert "bob" in fields
    assert "described_field" in fields


def test_described_fields(baseclass_instance):
    described = baseclass_instance.described_fields
    assert "described_field" in described
    

def test_sql_classes(baseclass_instance):
    sql_classes = baseclass_instance.sql_classes
    assert isinstance(sql_classes, list)
    assert "baseclass" in sql_classes
    assert "configitem" in sql_classes


def test_sqlalchemy_fields_includes_hybrid_properties():
    hybrid_fields = models.ReagentRole.sqlalchemy_fields
    assert "proceduretype" in hybrid_fields
    assert "reagent" in hybrid_fields


def test_clean_details_for_render(baseclass_instance):
    sql=models.Reagent(name="Test")
    sql.eol_ext=30
    sql.cost_per_ml=0.5
    pyd=sql.to_pydantic()
    if isinstance(pyd, tuple):
        pyd = pyd[0]
    d = dict(
        date = datetime.datetime(2024, 1, 1),
        baud = bytes(10),
        test_dict={"value": 1, "name": 2},
        sql=sql,
        pyd=pyd
    )
    d = baseclass_instance.clean_details_for_render(d)
    assert "test_dict" in d
    assert d["test_dict"] == 2
    assert "baud" not in d
    assert d['date'] == "2024-01-01"
    assert d['sql'] == "Test"
    assert d['pyd'] == "Test"
    