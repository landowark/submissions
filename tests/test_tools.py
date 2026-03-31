import pytest, sys
if "C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
from tools import *
from pathlib import WindowsPath
from typing import Generator
import pandas as pd, numpy as np
from datetime import datetime, date



@pytest.fixture(scope="function")
def setup_df():
    dicts = [{'points': 50, 'month': "may"}, 
                {'points': 25, 'month': "february"}, 
                {'points':90, 'month': 'january'}, 
                {'points':20, 'month': 'june'}]
    return pd.DataFrame(dicts)


def test_setup():
    assert os_config_dir == 'AppData/local'
    assert isinstance(main_aux_dir, WindowsPath)
    assert main_aux_dir.__str__() == 'C:\\Users\\lwark\\AppData\\local\\procedure'
    assert CONFIGDIR.__str__() == 'C:\\Users\\lwark\\AppData\\local\\procedure\\config'
    assert LOGDIR.__str__() == 'C:\\Users\\lwark\\AppData\\local\\procedure\\logs'
    assert row_map[1] == "A"
    assert row_map[8] == "H"
    assert row_map[12] == "L"
    assert row_keys["A"] == 1
    assert row_keys["H"] == 8
    assert row_keys["L"] == 12
    assert main_form_style == '''
                        QComboBox:!editable, QDateEdit {
                            background-color:light gray;
                        }
                '''
    assert page_size == 250


def test_tools_divide_chunks():
    b = divide_chunks([1,2,3,4], 4)
    assert isinstance(b, Generator)
    assert [item for item in b] == [[1], [2], [3], [4]]
    b = divide_chunks([1,2,3,4], 2)
    assert [item for item in b] == [[1, 2], [3, 4]]


def test_tools_get_unique_values_in_df_column(setup_df):
    uni = get_unique_values_in_df_column(setup_df, "points")
    assert uni == [20, 25, 50, 90]


def test_tools_check_not_nan():
    assert check_not_nan(np.nan) is False
    assert check_not_nan(pd.NaT) is False
    assert check_not_nan("none") is False
    assert check_not_nan("void") is False
    assert check_not_nan("Hello") is True


def test_tools_convert_nans_to_nones():
    assert convert_nans_to_nones("NAN") is None
    assert convert_nans_to_nones("BLANk") is None


def test_tools_get_first_blank_df_row(setup_df):
    assert get_first_blank_df_row(setup_df) == 5


def test_tools_check_if_app():
    assert check_if_app() is False


def test_tools_convert_well_to_row_column():
    assert convert_well_to_row_column("A1") == (1, 1)


def test_tools_list_str_comparator():
    assert list_str_comparator("jockey", ["j", "o"], mode="starts_with") is True
    assert list_str_comparator("jockey", ["o"], mode="starts_with") is False
    assert list_str_comparator("jockey", ["o"], mode="contains") is True


def test_tools_sort_dict_by_list():
    example_dict = {
        "banana": 3,
        "apple": 5,
        "cherry": 2,
        "date": 10,
        "elderberry": 8
    }
    example_order = ["cherry", "apple", "fig", "banana"]
    sorted_res = sort_dict_by_list(example_dict, example_order)
    assert list(sorted_res.keys())[0] == "cherry"
    assert list(sorted_res.keys())[-1] == "elderberry"


def test_tools_is_developer():
    # print(ctx.super_users)
    assert is_developer() is True


def test_tools_is_power_user():
    assert is_power_user() is True


def test_tools_is_list_etc():
    assert is_list_etc("hi there") is False
    assert is_list_etc([1,2,3]) is True


def test_tools_flatten_list():
    l = flatten_list([[1,2,3], [4,5,6]])
    assert len(l) == 6
    assert l[2] == 3

# def test_tools_sanitize_object_for_json():
    
#     from backend.db.models import ClientSubmission
    
#     test_dict = {
#         "integer": 42,
#         "float": 3.14,
#         "boolean": True,
#         "string": "Hello World",
#         "date_obj": date(2023, 10, 5),
#         "datetime_obj": datetime(2023, 10, 5, 14, 30, 0),
#         "nested_dict": {
#             "inner_key": "inner_value",
#             "inner_date": date(2024, 1, 1)
#         },
#         "list_of_mixed": [
#             "string_in_list",
#             date(2025, 12, 25),
#             {"list_dict_key": 100}
#         ],
#         "unserializable": ClientSubmission(submitter_plate_id="Bob")
#     }
#     output = sanitize_object_for_json(test_dict)
#     assert output['integer'] == 42
#     assert output['float'] == 3.14
#     assert output['boolean'] is True
#     assert output['string'] == "Hello World"
#     assert output['unserializable'] == "Bob"
#     assert output['date_obj'] == '2023-10-05'
#     assert output['datetime_obj'] == '2023-10-05T14:30:00'
#     assert output['nested_dict'] == {'inner_key': 'inner_value', 'inner_date': '2024-01-01'}
#     assert output['list_of_mixed'] == ['string_in_list', '2025-12-25', {'list_dict_key': 100}]


import pytest
from typing import Literal, Tuple
from unittest.mock import MagicMock

# Assuming the function is in a module named 'utils'
# from your_module import find_first_matching_dict

def test_find_first_matching_dict_pop_success():
    data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    
    # Test popping the first element
    result = find_first_matching_dict(data, "id", 1, mode="pop")
    
    assert result == {"id": 1, "name": "Alice"}
    assert len(data) == 1
    assert data[0]["id"] == 2

def test_find_first_matching_dict_return_mode():
    data = [{"id": 1}, {"id": 2}]
    
    result = find_first_matching_dict(data, "id", 2, mode="return")
    
    assert result == {"id": 2}
    assert len(data) == 2  # Ensure it wasn't removed

def test_find_first_matching_dict_index_mode():
    data = [{"id": 10}, {"id": 20}, {"id": 30}]
    
    index, item = find_first_matching_dict(data, "id", 20, mode="index")
    
    assert index == 1
    assert item == {"id": 20}

def test_find_first_matching_dict_not_found():
    data = [{"id": 1}]
    
    with pytest.raises(StopIteration, match="Could not find id value"):
        find_first_matching_dict(data, "id", 99)

def test_find_first_matching_dict_with_objects():
    # Mocking PydBaseClass and BaseClass behavior since they use getattr
    class MockModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    # We mock the issubclass check by using a class that the function would recognize
    # In a real scenario, you'd import your actual BaseClasses
    obj = MockModel(id=5, name="Test")
    data = [obj]

    # Note: For this to work in your specific function, MockModel 
    # must actually inherit from PydBaseClass or BaseClass.
    # Here we simulate the dict-like access via getattr
    result = find_first_matching_dict(data, "id", 5, mode="return")
    assert result.name == "Test"

def test_find_first_matching_dict_invalid_type():
    data = ["not a dict"]
    
    with pytest.raises(ValueError, match="Unmatched value"):
        find_first_matching_dict(data, "id", 1)




