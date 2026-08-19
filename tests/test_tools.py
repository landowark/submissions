"""
The pure helpers in ``tools``.

Nothing here touches the database or Qt, so this module is fast and can be run on
its own while iterating. These functions look trivial, which is exactly why they
are worth pinning: several of them encode conventions the rest of the codebase
silently depends on.

``handle_results`` is the clearest example. It is the filter every template value
passes through, and it turns ``None`` into the string ``"NA"``. That single
behavior is why removing the ``"NA"`` fallback from ``Run.signed_by`` left the
*display* correct while breaking a template condition that read the raw value --
the sentinel was being manufactured in two places and only one of them changed.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest


# --------------------------------------------------------------------------- #
# handle_results: the template display filter.                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [
        ("plain", "plain"),
        (42, "42"),
        (3.5, "3.5"),
        (True, "True"),
        (False, "False"),
        (None, "NA"),
    ],
)
def test_handle_results_scalars(value, expected):
    from tools import handle_results

    assert handle_results(value) == expected


def test_handle_results_turns_none_into_the_na_sentinel():
    """
    ``None`` displays as ``"NA"``.

    Any code comparing a *raw* model value against ``"NA"`` is therefore comparing
    against something only this filter produces. Templates must either apply the
    filter or test truthiness -- never compare the unfiltered value to the string.
    """
    from tools import handle_results

    assert handle_results(None) == "NA"


def test_handle_results_unwraps_sourced_field_dicts():
    """Values arrive from the pydantic layer as ``{"value": ..., "missing": ...}``."""
    from tools import handle_results

    assert handle_results({"value": "wrapped", "missing": False}) == "wrapped"


def test_handle_results_formats_datetimes_as_iso_days():
    from tools import handle_results

    assert handle_results(datetime(2026, 8, 19, 14, 30)) == "2026-08-19"


# @pytest.mark.xfail(
#     strict=True,
#     reason="tools/__init__.py:979 calls input_value.isoformat(timespec='minutes') "
#            "for the combined 'case datetime() | date()' branch, but date.isoformat "
#            "takes no arguments -- only datetime's does. A plain date therefore "
#            "raises TypeError. The models store TIMESTAMP columns so they yield "
#            "datetimes, but openpyxl can hand back a plain date and "
#            "backend/excel/writers/__init__.py:124 pipes cell values straight into "
#            "this filter. Fix: branch on datetime and date separately. Delete this "
#            "xfail when fixed.",
# )
def test_handle_results_formats_plain_dates():
    from tools import handle_results

    assert handle_results(date(2026, 8, 19)) == "2026-08-19"


def test_handle_results_escapes_html():
    """Output is injected into a page, so markup in the data must not survive."""
    from tools import handle_results

    assert "<script>" not in handle_results("<script>alert(1)</script>")


# --------------------------------------------------------------------------- #
# Plate coordinates.                                                           #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "well,row,column",
    [("A1", 1, 1), ("A12", 1, 12), ("H1", 8, 1), ("H12", 8, 12), ("D6", 4, 6)],
)
def test_convert_well_to_row_column(well, row, column):
    from tools import convert_well_to_row_column

    assert convert_well_to_row_column(well) == (row, column)


@pytest.mark.parametrize("well", ["A1", "A12", "H1", "H12", "D6"])
def test_well_conversion_round_trips(well):
    """
    ``well -> (row, column) -> well`` must be the identity.

    Sample positions are stored as row/column pairs and displayed as wells, so a
    mismatch between the two directions silently moves samples around the plate
    map.
    """
    from tools import convert_row_column_to_well, convert_well_to_row_column

    row, column = convert_well_to_row_column(well)
    assert convert_row_column_to_well(row, column) == well


# --------------------------------------------------------------------------- #
# Small predicates and coercions.                                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value,expected",
    [("text", True), (1, True), (0.0, True), (None, False), ("", False), ("nan", False)],
)
def test_check_not_nan(value, expected):
    from tools import check_not_nan

    assert check_not_nan(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [("nan", None), ("NaN", None), ("", None), ("real", "real")],
)
def test_convert_nans_to_nones(value, expected):
    from tools import convert_nans_to_nones

    assert convert_nans_to_nones(value) == expected


def test_flatten_list():
    from tools import flatten_list

    assert flatten_list([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]


def test_ensure_list_materializes_lazy_iterables_only():
    """
    Despite the name and the ``-> List`` annotation, ``ensure_list`` does not wrap
    scalars -- it only materializes generators, filters and maps, and returns
    everything else untouched. Callers that expect a list back from a scalar get
    the scalar. Pinned here because the name invites the opposite assumption.
    """
    from tools import ensure_list

    assert ensure_list(x for x in [1, 2, 3]) == [1, 2, 3]
    assert ensure_list(filter(None, [1, 0, 2])) == [1, 2]
    assert ensure_list(map(str, [1, 2])) == ["1", "2"]
    # A plain iterator is not a Generator, so it is passed through untouched.
    assert not isinstance(ensure_list(iter([1, 2, 3])), list)
    assert ensure_list(["a", "b"]) == ["a", "b"]
    assert ensure_list("one") == "one"          # not ["one"]
    assert ensure_list(None) is None


def test_divide_chunks_covers_every_element():
    from tools import divide_chunks

    source = list(range(10))
    chunks = list(divide_chunks(source, 3))
    assert sorted(x for chunk in chunks for x in chunk) == source


def test_is_internal_attr_key_recognises_sqlalchemy_bookkeeping():
    """
    ``BaseClass.__setattr__`` uses this to decide what may pass straight through
    to ``object.__setattr__``. A false negative here routes SQLAlchemy's internal
    state into the ``_misc_info`` JSON column and corrupts the row.
    """
    from tools import is_internal_attr_key

    assert is_internal_attr_key("_AssociationProxy_procedure_140280987586960")
    assert is_internal_attr_key("_sa_instance_state")
    assert not is_internal_attr_key("submitter_plate_id")


def test_sanitize_object_for_json_makes_dates_serializable():
    from json import dumps

    from tools import sanitize_object_for_json

    dumps(sanitize_object_for_json(datetime(2026, 8, 19, 9, 0)))


def test_sort_dict_by_list_orders_known_keys_first():
    from tools import sort_dict_by_list

    result = sort_dict_by_list({"c": 3, "a": 1, "b": 2}, ["a", "b", "c"])
    assert list(result.keys()) == ["a", "b", "c"]


def test_jinja_environment_registers_the_display_filters():
    """
    The templates call these by name; a rename in ``tools`` shows up as an
    empty page rather than an error, because Jinja resolves unknown filters at
    render time.
    """
    from tools import jinja_template_loading

    env = jinja_template_loading()
    for filter_name in ("handle_results", "get_type"):
        assert filter_name in env.filters, f"template filter {filter_name} is missing"
