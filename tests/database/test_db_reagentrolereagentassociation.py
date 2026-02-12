import logging
import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import (
    ReagentRoleReagentAssociation,
    ReagentRole,
    Reagent
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
def reagentrolereagentassociation(db):
    return ReagentRoleReagentAssociation.query(limit=1)


def test_reagentrolereagentassociation_query(reagentrolereagentassociation):
    assert isinstance(reagentrolereagentassociation, ReagentRoleReagentAssociation)


def test_reagentrolereagentassociation_get_name(reagentrolereagentassociation):
    assert reagentrolereagentassociation.name == "Test ReagentRole->Test Solution"


def test_reagentrolereagentassociation_get_reagent(reagentrolereagentassociation):
    assert isinstance(reagentrolereagentassociation.reagent, Reagent)
    assert reagentrolereagentassociation.reagent.name == "Test Solution"


def test_reagentrolereagentassociation_set_reagent(reagentrolereagentassociation):
    test_insert = Reagent(name="Insert Reagent")
    reagentrolereagentassociation.reagent = test_insert
    assert test_insert == reagentrolereagentassociation.reagent

    test_insert = dict(name="Dict Reagent")
    reagentrolereagentassociation.reagent = test_insert
    assert "Dict Reagent" == reagentrolereagentassociation.reagent.name


def test_reagentrolereagentassociation_get_reagentrole(reagentrolereagentassociation):
    assert isinstance(reagentrolereagentassociation.reagentrole, ReagentRole)
    assert reagentrolereagentassociation.reagentrole.name == "Test ReagentRole"


def test_reagentrolereagentassociation_set_reagentrole(reagentrolereagentassociation):
    test_insert = ReagentRole(name="Insert ReagentRole")
    reagentrolereagentassociation.reagentrole = test_insert
    assert test_insert == reagentrolereagentassociation.reagentrole

    test_insert = dict(name="Dict ReagentRole")
    reagentrolereagentassociation.reagentrole = test_insert
    assert "Dict ReagentRole" == reagentrolereagentassociation.reagentrole.name

