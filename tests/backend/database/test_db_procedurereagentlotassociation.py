from datetime import date, timedelta
import logging
import pytest
from sqlalchemy.ext.associationproxy import _AssociationList

from custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureReagentLotAssociation,
    Procedure,
    ReagentLot,
    ReagentRole
)

logger = logging.getLogger(f"testing.{__name__}")


@pytest.fixture(scope="function")
def db():
    tc = DatabaseTestCase()
    tc.setUp()
    yield tc
    try:
        tc.tearDown()
    except Exception:
        pass


@pytest.fixture(scope="function")
def procedurereagentlotassociation(db):
    return ProcedureReagentLotAssociation.query(limit=1)


def test_procedurereagentlotassociation_query(procedurereagentlotassociation):
    assert isinstance(procedurereagentlotassociation, ProcedureReagentLotAssociation)


def test_procedurereagentlotassociation_get_name(procedurereagentlotassociation):
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert procedurereagentlotassociation.name == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00->Test Solution - 012345"


def test_procedurereagentlotassociation_get_reagentlot(procedurereagentlotassociation):
    assert isinstance(procedurereagentlotassociation.reagentlot, ReagentLot)
    assert procedurereagentlotassociation.reagentlot.name == "Test Solution - 012345"


def test_procedurereagentlotassociation_set_reagentlot(procedurereagentlotassociation):
    test_insert = ReagentLot(lot="Insert ReagentLot", expiry="2027-01-01")
    procedurereagentlotassociation.reagentlot = test_insert
    assert test_insert == procedurereagentlotassociation.reagentlot

    test_insert = dict(lot="Dict ReagentLot", expiry="2027-01-01")
    procedurereagentlotassociation.reagentlot = test_insert
    assert "Unassigned Reagent - Dict ReagentLot" == procedurereagentlotassociation.reagentlot.name


def test_procedurereagentlotassociation_get_procedure(procedurereagentlotassociation):
    assert isinstance(procedurereagentlotassociation.procedure, Procedure)
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert procedurereagentlotassociation.procedure.name == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00"


def test_procedurereagentlotassociation_set_procedure(procedurereagentlotassociation):
    test_insert = Procedure(name="Insert Procedure")
    procedurereagentlotassociation.procedure = test_insert
    assert test_insert == procedurereagentlotassociation.procedure

    # test_insert = dict(name="Dict Procedure")
    # procedurereagentlotassociation.procedure = test_insert
    # assert "Dict Procedure" == procedurereagentlotassociation.procedure.name


def test_procedurereagentlotassociation_get_reagentrole(procedurereagentlotassociation):
    assert isinstance(procedurereagentlotassociation.reagentrole, ReagentRole)
    assert procedurereagentlotassociation.reagentrole.name == "Test ReagentRole"


def test_procedurereagentlotassociation_set_reagentrole(procedurereagentlotassociation):
    test_insert = ReagentRole(name="Insert ReagentRole")
    procedurereagentlotassociation.reagentrole = test_insert
    assert test_insert == procedurereagentlotassociation.reagentrole

    test_insert = dict(name="Dict ReagentRole")
    procedurereagentlotassociation.reagentrole = test_insert
    assert "Dict ReagentRole" == procedurereagentlotassociation.reagentrole.name


