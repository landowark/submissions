import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from sqlalchemy.orm.collections import InstrumentedList
from custom_resources import DatabaseTestCase
from backend.db.models import ProcedureType, EquipmentRole, ReagentRole, ResultsType, SubmissionType, Procedure, Run
from backend.validators.pydant import PydProcedure


@pytest.fixture(scope="function")
def db():
    tc = DatabaseTestCase()
    tc.setUp()
    yield tc
    try:
        tc.tearDown()
    except Exception:
        pass


# ProcedureType
@pytest.fixture(scope="function")
def proceduretype(db):
    return ProcedureType.query(limit=1)


def test_proceduretype_query(proceduretype):
    assert isinstance(proceduretype, ProcedureType)


def test_proceduretype_get_equipmentrole(proceduretype):
    assert isinstance(proceduretype.equipmentrole, _AssociationList)
    assert isinstance(proceduretype.equipmentrole[0], EquipmentRole)


def test_proceduretype_set_equipmentrole(proceduretype):
    test_insert = EquipmentRole(name="Insert EquipmentRole")
    proceduretype.equipmentrole = [test_insert]
    assert test_insert in proceduretype.equipmentrole
    test_insert = dict(name="Dict EquipmentRole")
    proceduretype.equipmentrole = [test_insert]
    assert "Dict EquipmentRole" in [item.name for item in proceduretype.equipmentrole]


def test_proceduretype_get_reagentrole(proceduretype):
    assert isinstance(proceduretype.reagentrole, _AssociationList)
    assert isinstance(proceduretype.reagentrole[0], ReagentRole)


def test_proceduretype_set_reagentrole(proceduretype):
    test_insert = ReagentRole(name="Insert ReagentRole")
    proceduretype.reagentrole = [test_insert]
    assert test_insert in proceduretype.reagentrole
    test_insert = dict(name="Dict ReagentRole")
    proceduretype.reagentrole = [test_insert]
    assert "Dict ReagentRole" in [item.name for item in proceduretype.reagentrole]


def test_proceduretype_get_resultstype(proceduretype):
    assert isinstance(proceduretype.resultstype, InstrumentedList)
    assert isinstance(proceduretype.resultstype[0], ResultsType)


def test_proceduretype_set_resultstype(proceduretype):
    test_insert = ResultsType(name="Insert ResultsType")
    proceduretype.resultstype = [test_insert]
    assert test_insert in proceduretype.resultstype
    test_insert = dict(name="Dict ResultsType")
    proceduretype.resultstype = [test_insert]
    assert "Dict ResultsType" in [item.name for item in proceduretype.resultstype]


def test_proceduretype_get_submissiontype(proceduretype):
    assert isinstance(proceduretype.submissiontype, InstrumentedList)
    assert isinstance(proceduretype.submissiontype[0], SubmissionType)


def test_proceduretype_set_submissiontype(proceduretype):
    test_insert = SubmissionType(name="Insert SubmissionType")
    proceduretype.submissiontype = [test_insert]
    assert test_insert in proceduretype.submissiontype
    test_insert = dict(name="Dict SubmissionType")
    proceduretype.submissiontype = [test_insert]
    assert "Dict SubmissionType" in [item.name for item in proceduretype.submissiontype]


def test_proceduretype_get_procedure(proceduretype):
    assert isinstance(proceduretype.procedure, InstrumentedList)
    assert isinstance(proceduretype.procedure[0], Procedure)


def test_proceduretype_set_procedure(proceduretype):
    test_insert = Procedure(name="Insert Procedure")
    proceduretype.procedure = [test_insert]
    assert test_insert in proceduretype.procedure
    # test_insert = dict(name="Dict Procedure")
    # proceduretype.procedure = [test_insert]
    # assert "Dict Procedure" in [item.name for item in proceduretype.procedure]


def test_proceduretype_construct_dummy_procedure(proceduretype):
    run = Run.query()[0]
    pyd = proceduretype.construct_dummy_procedure(run=run)
    assert isinstance(pyd, PydProcedure)


def test_proceduretype_ranked_plate(proceduretype):
    rp = proceduretype.ranked_plate
    assert isinstance(rp, dict)
    assert len(rp.keys()) == 96
    assert max([value[0] for k, value in rp.items()]) == 8
    assert max([value[1] for k, value in rp.items()]) == 12


def test_proceduretype_total_wells(proceduretype):
    assert proceduretype.total_wells == 96


def test_proceduretype_allowed_result_method(proceduretype):
    assert isinstance(proceduretype.allowed_result_methods, list)
    assert proceduretype.allowed_result_methods[0]["name"] == "Test ResultsType"


def test_proceduretype_to_html(proceduretype):
    assert isinstance(proceduretype.to_html(), str)
