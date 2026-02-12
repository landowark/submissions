import pytest
from sqlalchemy.ext.associationproxy import _AssociationList
from datetime import datetime, date, time, timedelta
from custom_resources import DatabaseTestCase
from pytz import timezone as tz
from backend.db.models import ReagentLot, Equipment, Sample, ProcedureType, Run, Procedure


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


def test_procedure_query(procedure):
    assert isinstance(procedure, Procedure)


def test_procedure_get_reagentlot(procedure):
    assert isinstance(procedure.reagentlot, _AssociationList)
    assert isinstance(procedure.reagentlot[0], ReagentLot)


def test_procedure_set_reagentlot(procedure):
    test_insert = ReagentLot(name="Insert ReagentLot")
    procedure.reagentlot = [test_insert]
    assert test_insert in procedure.reagentlot

    test_insert = dict(lot="Dict ReagentLot")
    procedure.reagentlot = [test_insert]
    assert "Dict ReagentLot" in [item.lot for item in procedure.reagentlot]


def test_procedure_get_equipment(procedure):
    assert isinstance(procedure.equipment, _AssociationList)
    assert isinstance(procedure.equipment[0], Equipment)


def test_procedure_set_equipment(procedure):
    test_insert = Equipment(name="Insert Equipment")
    procedure.equipment = [test_insert]
    assert test_insert in procedure.equipment

    test_insert = dict(name="Dict Equipment")
    procedure.equipment = [test_insert]
    assert "Dict Equipment" in [item.name for item in procedure.equipment]


def test_procedure_get_sample(procedure):
    assert isinstance(procedure.sample, _AssociationList)
    assert isinstance(procedure.sample[0], Sample)


def test_procedure_set_sample_and_rank(procedure):
    test_insert = Sample(sample_id="Insert Sample", _misc_info={"rank": 3})
    procedure.sample = [test_insert]
    assert test_insert in procedure.sample
    assert procedure.proceduresampleassociation[0].procedure_rank == 3

    test_insert = dict(sample_id="Dict Sample")
    procedure.sample = [test_insert]
    assert "Dict Sample" in [item.name for item in procedure.sample]
    assert procedure.proceduresampleassociation[0].procedure_rank == 1


def test_procedure_get_started_date(procedure):
    assert isinstance(procedure.started_date, datetime)
    dt = datetime.combine(date.today() - timedelta(days=1), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
    assert procedure.started_date == dt


def test_procedure_set_started_date(procedure):
    test_insert = "2026-02-02"
    dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
    procedure.started_date = test_insert
    assert procedure.started_date == dt


def test_procedure_get_completed_date(procedure):
    assert isinstance(procedure.completed_date, datetime)
    dt = datetime.combine(date.today(), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
    assert procedure.completed_date == dt


def test_procedure_set_completed_date(procedure):
    test_insert = "2026-02-02"
    dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
    procedure.completed_date = test_insert
    assert procedure.completed_date == dt


def test_procedure_get_proceduretype(procedure):
    assert isinstance(procedure.proceduretype, ProcedureType)


def test_procedure_set_proceduretype(procedure):
    test_insert = ProcedureType(name="Insert ProcedureType")
    procedure.proceduretype = test_insert
    assert test_insert == procedure.proceduretype

    test_insert = dict(name="Dict ProcedureType")
    procedure.proceduretype = test_insert
    assert "Dict ProcedureType" == procedure.proceduretype.name


def test_procedure_get_run(procedure):
    assert isinstance(procedure.run, Run)


def test_procedure_set_run(procedure):
    clientsub = procedure.run.clientsubmission
    test_insert = Run(rsl_plate_number="Insert Run", clientsubmission=clientsub)
    procedure.run = test_insert
    assert test_insert == procedure.run

    test_insert = dict(rsl_plate_number="Dict Run", clientsubmission=clientsub)
    procedure.run = test_insert
    assert "Dict Run" == procedure.run.rsl_plate_number


def test_procedure_custom_context_events(procedure):
    expected = ["Add Results", "Add Equipment", "Edit", "Add Comment", "Show Details", "Delete"]
    assert set(procedure.custom_context_events.keys()) == set(expected)


def test_procedure_get_default_info(procedure):
    assert set(procedure.get_default_info("form_ignore")) == set(
        [
            "reagents",
            "ctx",
            "id",
            "cost",
            "extraction_info",
            "signed_by",
            "comment",
            "namer",
            "submission_object",
            "tips",
            "contact_phone",
            "custom",
            "cost_centre",
            "completed_date",
            "control",
            "origin_plate",
            "filepath",
            "sample",
            "csv",
            "comment",
            "equipment",
        ]
    )
    assert set(procedure.get_default_info("singles")) == set(["id"])
    assert set(procedure.get_default_info("details_ignore")) == set(
        [
            "excluded",
            "reagents",
            "sample",
            "extraction_info",
            "comment",
            "barcode",
            "platemap",
            "export_map",
            "equipment",
            "tips",
            "custom",
            "reagentlot",
            "reagent_lot",
            "results",
            "proceduresampleassociation",
            "sample",
            "procedurereagentlotassociation",
            "procedureequipmentassociation",
            "proceduretipsassociation",
            "reagent",
            "equipment",
            "tips",
            "control",
        ]
    )
    assert set(procedure.get_default_info("form_recover")) == set(["filepath", "sample", "csv", "comment", "equipment"])


def test_procedure_get_submissiontype(procedure):
    assert procedure.submissiontype.name == "Default SubmissionType"


def test_procedure_set_cost(procedure):
    assert procedure.cost == 0.0
    assert procedure.procedurereagentlotassociation[0].reagentlot.reagent is not None
    procedure.set_cost()
    assert procedure.cost is not None
    assert procedure.cost == 1.25
