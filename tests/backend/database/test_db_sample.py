from datetime import date, datetime, timedelta
import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from sqlalchemy.orm.collections import InstrumentedList
from custom_resources import DatabaseTestCase
from backend.db.models import (Sample, Run, Procedure, 
                               ClientSubmission)

from pytz import timezone as tz


@pytest.fixture(scope="function")
def db():
    tc = DatabaseTestCase()
    tc.setUp()
    yield tc
    try:
        tc.tearDown()
    except Exception:
        pass


# Sample
@pytest.fixture(scope="function")
def sample(db):
    return Sample.query(limit=1)


def test_sample_query(sample):
    assert isinstance(sample, Sample)


def test_sample_get_clientsubmission(sample):
    assert isinstance(sample.clientsubmission, _AssociationList)
    assert isinstance(sample.clientsubmission[0], ClientSubmission)
    # assert isinstance(sample.clientsubmission[0], EquipmentRole)
    assert sample.clientsubmission[0].name == "Test ClientSubmission"


def test_sample_set_clientsubmission(sample):
    test_insert = ClientSubmission(submitter_plate_id="Insert ClientSubmission")
    sample.clientsubmission = test_insert
    assert test_insert in sample.clientsubmission
    test_insert = ClientSubmission(submitter_plate_id="Dict ClientSubmission")
    test_insert.save()
    test_insert = dict(submitter_plate_id="Dict ClientSubmission")
    sample.clientsubmission = test_insert
    assert "Dict ClientSubmission" in [cl.name for cl in  sample.clientsubmission]


def test_sample_get_run(sample):
    assert isinstance(sample.run, _AssociationList)
    assert isinstance(sample.run[0], Run)
    # assert isinstance(sample.run[0], EquipmentRole)
    assert sample.run[0].name == "RSL-XX-20260202-1"


def test_sample_set_run(sample):
    test_insert = Run(rsl_plate_number="Insert Run")
    sample.run = test_insert
    assert test_insert in sample.run
    test_insert = Run(rsl_plate_number="Dict Run")
    test_insert.save()
    test_insert = dict(rsl_plate_number="Dict Run")
    sample.run = test_insert
    assert "Dict Run" in [r.name for r in  sample.run]


def test_sample_get_procedure(sample):
    assert isinstance(sample.procedure, _AssociationList)
    assert isinstance(sample.procedure[0], Procedure)
    # assert isinstance(sample.procedure[0], EquipmentRole)
    day = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert sample.procedure[0].name == f"RSL-XX-20260202-1 - Test ProcedureType (1) - {day} 00:00:00"


def test_sample_set_procedure(sample):
    test_insert = Procedure(name="Insert Procedure")
    sample.procedure = test_insert
    assert test_insert in sample.procedure
    # test_insert = Procedure(name="Dict Procedure")
    # test_insert.save()
    # test_insert = dict(name="Dict Procedure")
    # sample.procedure = test_insert
    # assert "Dict Procedure" in [p.name for p in  sample.procedure]


def test_sample_get_is_control(sample):
    assert sample.is_control == 0


def test_sample_set_is_control(sample):
    sample.is_control = 1
    assert sample.is_control == 1
    sample.is_control = -9
    assert sample.is_control == -1
    sample.is_control = True
    assert sample.is_control == 1
    sample.is_control = "negative"
    assert sample.is_control == -1

