import pytest
import sys
if "C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
from backend.validators.pydant import PydBaseClass
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


def test_baseclass_creation():
    # Test that we can create an instance of PydBaseClass
    instance = PydBaseClass()
    assert isinstance(instance, PydBaseClass)
    assert isinstance(instance.sql_instance, models.BaseClass)


@pytest.fixture(scope="function", autouse=True)
def baseclass_instance():
    """
    Because PydBaseClass is abstract, we create a concrete subclass for testing.
    """
    class PydConcreteBaseClass(PydBaseClass):

        test_dict: Field(default_factory=dict, repr=False)
        
        @property
        def constructed_name(self) -> str:
            return "ConcreteBaseClass"
        
    @classproperty
    def _sql_name(cls) -> str:
        return "BaseClass"

    # @classproperty
    # def _sql_class(cls) -> models.BaseClass:
    #     # Lazy import here to reduce the chance of circular-import issues
    #     # (models may import pydant elsewhere during package import).
        
    #     try:
    #         return getattr(models, cls._sql_name)
       
    #     except AttributeError as e:
    #         # Provide a clearer error message listing available top-level
    #         # model names to help debugging name mismatches / import order.
    #         available = [n for n in dir(models) if not n.startswith("_")]
    #         raise AttributeError(
    #             f"SQL model '{cls._sql_name}' not found on backend.db.models. "
    #             f"Available top-level attributes: {available}") from e
        
    instance = PydConcreteBaseClass(test_dict={"value": 1, "name": 2})
    return instance


def test_filter_fields(baseclass_instance):
    filtered = baseclass_instance.filter_fields("test_dict")
    assert filtered == 1