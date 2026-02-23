import pytest
from custom_resources import DatabaseTestCase
from backend.db.models import Process, ProcessVersion, EquipmentRoleEquipmentAssociation, Equipment, EquipmentRole, Tips
from sqlalchemy.orm.collections import InstrumentedList
from datetime import date


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
def process(db):
    return Process.query(limit=1)


def test_process_query(process):
    assert isinstance(process, Process)


def test_process_get_processversion(process):
    assert isinstance(process.processversion, InstrumentedList)
    assert isinstance(process.processversion[0], ProcessVersion)


def test_process_set_processversion(process):
    test_insert = ProcessVersion(name="Insert ProcessVersion")
    process.processversion = [test_insert]
    assert test_insert in process.processversion

    test_insert = dict(version=1.0, date_verified=date.today(), project="NA", active=True)
    process.processversion = [test_insert]
    assert "NA" in [item.project for item in process.processversion]


def test_process_get_equipmentroleequipmentassociation(process):
    assert isinstance(process.equipmentroleequipmentassociation, InstrumentedList)
    assert isinstance(process.equipmentroleequipmentassociation[0], EquipmentRoleEquipmentAssociation)


def test_process_set_equipmentroleequipmentassociation(process):
    test_insert = EquipmentRoleEquipmentAssociation(equipment=Equipment(name="Insert Equipment"), equipmentrole=EquipmentRole(name="Insert EquipmentRole"))
    process.equipmentroleequipmentassociation = [test_insert]
    assert test_insert in process.equipmentroleequipmentassociation


def test_process_get_tips(process):
    assert isinstance(process.tips, InstrumentedList)
    assert isinstance(process.tips[0], Tips)


def test_process_set_tips(process):
    test_insert = Tips(name="Insert Tips")
    process.tips = [test_insert]
    assert test_insert in process.tips

    test_insert = dict(manufacturer="Sir Tipsalot", capacity=100, ref="YYYY")
    process.tips = [test_insert]
    assert "Sir Tipsalot - YYYY(100uL)" in [item.name for item in process.tips]
