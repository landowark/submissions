from openpyxl import Workbook
import pytest
from test_manager_basic import managers
from pathlib import Path
from backend.db.models import Procedure
from backend.validators.pydant import PydProcedureType
from tests.resources.custom_resources import DatabaseTestCase


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
def procedure(db):
    return Procedure.query(limit=1)


def test_construction_from_sql(procedure):
    
    proceduremanager = managers.DefaultProcedureManager(None, input_object=procedure)
    assert isinstance(proceduremanager.proceduretype, PydProcedureType)
    assert procedure.proceduretype.name == "Test ProcedureType"
    # assert isinstance(procedure.pyd, PydProcedure)


# def test_construction_from_pyd(clientsubmission):
#     clientsubmission = clientsubmission.to_pydantic()
#     assert clientsubmission.submissiontype.get("value") == "Default SubmissionType"
#     clientmanager = managers.DefaultClientSubmissionManager(None, input_object=clientsubmission)
#     assert isinstance(clientmanager.submissiontype, SubmissionType)
#     assert clientmanager.submissiontype.name == "Default SubmissionType"
#     assert isinstance(clientmanager.pyd, PydClientSubmission)


# def test_write(clientsubmission):
#     clientmanager = managers.DefaultClientSubmissionManager(None, input_object=clientsubmission)
#     wb = Workbook()
#     workbook = clientmanager.write(wb)
#     assert isinstance(workbook, Workbook)
#     assert "Client Info" in workbook.sheetnames
#     ws = workbook['Client Info']
#     assert ws.cell(1,1).value == "Submitter Info"
#     assert ws.cell(13, 3).value == "Row"

