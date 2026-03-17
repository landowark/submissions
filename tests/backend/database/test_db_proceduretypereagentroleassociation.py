import logging
from typing import Generator
import pytest
from sqlalchemy.ext.associationproxy import _AssociationList

from tests.resources.custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureTypeReagentRoleAssociation,
    Reagent,
    ProcedureType,
    ReagentRole,
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
def proceduretypereagentroleassociation(db):
    return ProcedureTypeReagentRoleAssociation.query(limit=1)


def test_proceduretypereagentroleassociation_query(proceduretypereagentroleassociation):
    assert isinstance(proceduretypereagentroleassociation, ProcedureTypeReagentRoleAssociation)


def test_proceduretypereagentroleassociation_get_proceduretype(proceduretypereagentroleassociation):
    assert isinstance(proceduretypereagentroleassociation.proceduretype, ProcedureType)


def test_proceduretypereagentroleassociation_set_proceduretype(proceduretypereagentroleassociation):
    test_insert = ProcedureType(name="Insert ProcedureType")
    proceduretypereagentroleassociation.proceduretype = test_insert
    assert proceduretypereagentroleassociation.proceduretype == test_insert

    test_insert = dict(name="Dict ProcedureType")
    proceduretypereagentroleassociation.proceduretype = test_insert
    assert proceduretypereagentroleassociation.proceduretype.name == "Dict ProcedureType"


def test_proceduretypereagentroleassociation_get_reagentrole(proceduretypereagentroleassociation):
    assert isinstance(proceduretypereagentroleassociation.reagentrole, ReagentRole)


def test_proceduretypereagentroleassociation_set_reagentrole(proceduretypereagentroleassociation):
    test_insert = ReagentRole(name="Insert ReagentRole")
    proceduretypereagentroleassociation.reagentrole = test_insert
    assert proceduretypereagentroleassociation.reagentrole == test_insert

    test_insert = dict(name="Dict ReagentRole")
    proceduretypereagentroleassociation.reagentrole = test_insert
    assert proceduretypereagentroleassociation.reagentrole.name == "Dict ReagentRole"


def test_proceduretypereagentroleassociation_get_all_relevant_reagents(proceduretypereagentroleassociation):
    reagents = proceduretypereagentroleassociation.get_all_relevant_reagents()
    assert isinstance(reagents, Generator)
    for reagent in reagents:
        assert isinstance(reagent, Reagent)
