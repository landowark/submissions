import pytest, sys
if "C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
from backend import managers

def test_create_default_manager():
    with pytest.raises(NotImplementedError, match="Parse only implemented in subclasses."):
        managers.DefaultManager(None, r"tests\resources\226C4100.xlsx") 
