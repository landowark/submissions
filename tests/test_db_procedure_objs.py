from datetime import date, datetime, time, timedelta
from custom_resources import DatabaseTestCase
from backend.db.models import (
    ClientSubmission,
    ReagentRole,
    ProcedureType,
    Reagent,
    ReagentLot,
    SubmissionType,
    EquipmentRole,
    ResultsType,
    Procedure,
    Run,
    Equipment,
    Sample,
    Process,
    ProcessVersion,
    EquipmentRoleEquipmentAssociation,
    Tips,
    TipsLot,
    ProcedureEquipmentTipslotAssociation,
    Results,
    ProcedureSampleAssociation
)
from backend.validators.pydant import (
    PydProcedure
)
from sqlalchemy.orm import Session
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.ext.associationproxy import _AssociationList

from unittest import main
from pytz import timezone as tz
import logging


logger = logging.getLogger(f"testing.{__name__}")



class DBBasicFunctions(DatabaseTestCase):

    def test_db_creation(self):
        self.assertIsInstance(self.session, Session)
        self.assertEqual(self.engine.url.render_as_string(), "sqlite:///:memory:")


class DBReagentRole(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.reagentrole = ReagentRole.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.reagentrole, ReagentRole)

    def test_get_proceduretype(self):
        try:
            self.assertIsInstance(self.reagentrole.proceduretype, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.reagentrole.proceduretype)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.reagentrole.proceduretype[0], ProcedureType)
        except AssertionError as e:
            logger.error(f"{self.reagentrole.proceduretype[0]} is not a ProcedureType object.")
            raise e
        
    def test_set_proceduretype(self):
        test_insert = ProcedureType(name="Insert ProcedureType")
        self.reagentrole.proceduretype = [test_insert]
        self.assertIn(test_insert, self.reagentrole.proceduretype)
        test_insert = dict(name="Dict ProcedureType")
        self.reagentrole.proceduretype = [test_insert]
        self.assertIn("Dict ProcedureType", [item.name for item in self.reagentrole.proceduretype])

    def test_get_reagent(self):
        try:
            self.assertIsInstance(self.reagentrole.reagent, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.reagentrole.reagent)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.reagentrole.reagent[0], Reagent)
        except AssertionError as e:
            logger.error(f"{self.reagentrole.reagent[0]} is not a Reagent object.")
            raise e

    def test_set_reagent(self):
        test_insert = Reagent(name="Insert Reagent")
        self.reagentrole.reagent = [test_insert]
        self.assertIn(test_insert, self.reagentrole.reagent)
        test_insert = dict(name="Dict Reagent")
        self.reagentrole.reagent = [test_insert]
        self.assertIn("Dict Reagent", [item.name for item in self.reagentrole.reagent])
    
    def test_get_reagents(self):
        output = self.reagentrole.get_reagents()
        self.assertIsInstance(output, list)


class DBReagent(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.reagent = Reagent.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.reagent, Reagent)

    def test_get_reagentrole(self):
        try:
            self.assertIsInstance(self.reagent.reagentrole, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.reagent.reagentrole)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.reagent.reagentrole[0], ReagentRole)
        except AssertionError as e:
            logger.error(f"{self.reagent.reagentrole[0]} is not a ReagentRole object.")
            raise e
        
    def test_set_reagentrole(self):
        test_insert = ReagentRole(name="Insert ReagentRole")
        self.reagent.reagentrole = [test_insert]
        self.assertIn(test_insert, self.reagent.reagentrole)
        test_insert = dict(name="Dict ReagentRole")
        self.reagent.reagentrole = [test_insert]
        self.assertIn("Dict ReagentRole", [item.name for item in self.reagent.reagentrole])

    def test_get_reagentlot(self):
        try:
            self.assertIsInstance(self.reagent.reagentlot, list)
        except AssertionError as e:
            logger.error(f"{type(self.reagent.reagentlot)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.reagent.reagentlot[0], ReagentLot)
        except AssertionError as e:
            logger.error(f"{self.reagent.reagentlot[0]} is not a ReagentLot object.")
            raise e
        
    def test_set_reagentlot(self):
        test_insert = ReagentLot(name="Insert ReagentLot")
        self.reagent.reagentlot = [test_insert]
        self.assertIn(test_insert, self.reagent.reagentlot)
        test_insert = dict(lot="Dict ReagentLot")
        self.reagent.reagentlot = [test_insert]
        self.assertIn("Test Solution - Dict ReagentLot", [item.name for item in self.reagent.reagentlot])

    def test_lot_dicts(self):
        # Base expiry as set in the toy database (date one year from today at max time)
        dt = datetime.combine(date(year=date.today().year + 1, month=date.today().month, day=date.today().day), datetime.max.time()).replace(tzinfo=tz("America/Winnipeg"))
        # Reagent.lot_dicts returns lot.expiry + reagent.eol_ext; include that in expected
        try:
            expected_expiry = (dt + self.reagent.eol_ext)
        except Exception:
            # If eol_ext isn't set as timedelta yet, try treating it as days
            try:
                expected_expiry = dt + self.reagent.eol_ext
            except Exception:
                expected_expiry = dt
        simplified_expected = {"name": "Test Solution", "lot": "012345", "expiry": expected_expiry}

        self.assertIn(simplified_expected, self.reagent.lot_dicts)


class DBSubmissionType(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.submissiontype = SubmissionType.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.submissiontype, SubmissionType)

    def test_get_file_name_template(self):
        self.assertEqual(self.submissiontype.file_name_template, '{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}_{{_completed_date}}')

    def test_get_clientsubmission(self):
        try:
            self.assertIsInstance(self.submissiontype.clientsubmission, list)
        except AssertionError as e:
            logger.error(f"{type(self.submissiontype.clientsubmission)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.submissiontype.clientsubmission[0], ClientSubmission)
        except AssertionError as e:
            logger.error(f"{self.submissiontype.clientsubmission[0]} is not a ClientSubmission object.")
            raise e
        
    def test_set_clientsubmission(self):
        test_insert = ClientSubmission(name="Insert ClientSubmission")
        self.submissiontype.clientsubmission = [test_insert]
        self.assertIn(test_insert, self.submissiontype.clientsubmission)
        test_insert = dict(submitter_plate_id="Dict ClientSubmission")
        self.submissiontype.clientsubmission = [test_insert]
        self.assertIn("Dict ClientSubmission", [item.submitter_plate_id for item in self.submissiontype.clientsubmission])

    def test_get_proceduretype(self):
        try:
            self.assertIsInstance(self.submissiontype.proceduretype, list)
        except AssertionError as e:
            logger.error(f"{type(self.submissiontype.proceduretype)} is not an list object.")
            raise e  
        try:
            self.assertIsInstance(self.submissiontype.proceduretype[0], ProcedureType)
        except AssertionError as e:
            logger.error(f"{self.submissiontype.proceduretype[0]} is not a ProcedureType object.")
            raise e
        
    def test_set_proceduretype(self):
        test_insert = ProcedureType(name="Insert ProcedureType")
        self.submissiontype.proceduretype = [test_insert]
        self.assertIn(test_insert, self.submissiontype.proceduretype)
        test_insert = dict(name="Dict ProcedureType")
        self.submissiontype.proceduretype = [test_insert]
        self.assertIn("Dict ProcedureType", [item.name for item in self.submissiontype.proceduretype])

    def test_get_turnaround_time(self):
        self.assertEqual(self.submissiontype.turnaround_time, timedelta(days=5))

    def test_set_turnaround_time(self):
        self.submissiontype.turnaround_time = 3
        self.assertEqual(self.submissiontype.turnaround_time, timedelta(days=3))
        self.submissiontype.turnaround_time = "4"
        self.assertEqual(self.submissiontype.turnaround_time, timedelta(days=4))
        self.submissiontype.turnaround_time = None
        self.assertEqual(self.submissiontype.turnaround_time, timedelta(days=5))

    def test_get_abbreviation(self):
        self.assertEqual(self.submissiontype.abbreviation, "XX")

    def test_set_abbreviation(self):
        self.submissiontype.abbreviation = "XXXX"
        self.assertEqual(self.submissiontype.abbreviation, "XXXX")
        self.submissiontype.abbreviation = "XXXXenomorph"
        self.assertEqual(self.submissiontype.abbreviation, "XXXX")
        self.submissiontype.abbreviation = 1234
        self.assertEqual(self.submissiontype.abbreviation, "1234")

    def check_aliases(self):
        self.assertIsInstance(SubmissionType.aliases, list)
        self.assertIn("submissiontype", SubmissionType.aliases)
        self.assertIn("submissiontypes", SubmissionType.aliases)


class DBProcedureType(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.proceduretype = ProcedureType.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.proceduretype, ProcedureType)

    def test_get_equipmentrole(self):
        try:
            self.assertIsInstance(self.proceduretype.equipmentrole, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.proceduretype.equipmentrole)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.proceduretype.equipmentrole[0], EquipmentRole)
        except AssertionError as e:
            logger.error(f"{self.proceduretype.equipmentrole[0]} is not a EquipmentRole object.")
            raise e
        
    def test_set_equipmentrole(self):
        test_insert = EquipmentRole(name="Insert EquipmentRole")
        self.proceduretype.equipmentrole = [test_insert]
        self.assertIn(test_insert, self.proceduretype.equipmentrole)
        test_insert = dict(name="Dict EquipmentRole")
        self.proceduretype.equipmentrole = [test_insert]
        self.assertIn("Dict EquipmentRole", [item.name for item in self.proceduretype.equipmentrole])

    def test_get_reagentrole(self):
        try:
            self.assertIsInstance(self.proceduretype.reagentrole, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.proceduretype.reagentrole)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.proceduretype.reagentrole[0], ReagentRole)
        except AssertionError as e:
            logger.error(f"{self.proceduretype.reagentrole[0]} is not a ReagentRole object.")
            raise e
        
    def test_set_reagentrole(self):
        test_insert = ReagentRole(name="Insert ReagentRole")
        self.proceduretype.reagentrole = [test_insert]
        self.assertIn(test_insert, self.proceduretype.reagentrole)
        test_insert = dict(name="Dict ReagentRole")
        self.proceduretype.reagentrole = [test_insert]
        self.assertIn("Dict ReagentRole", [item.name for item in self.proceduretype.reagentrole])

    def test_get_resultstype(self):
        try:
            self.assertIsInstance(self.proceduretype.resultstype, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{type(self.proceduretype.resultstype)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.proceduretype.resultstype[0], ResultsType)
        except AssertionError as e:
            logger.error(f"{self.proceduretype.resultstype[0]} is not a resultstype object.")
            raise e
        
    def test_set_resultstype(self):
        test_insert = ResultsType(name="Insert ResultsType")
        self.proceduretype.resultstype = [test_insert]
        self.assertIn(test_insert, self.proceduretype.resultstype)
        test_insert = dict(name="Dict ResultsType")
        self.proceduretype.resultstype = [test_insert]
        self.assertIn("Dict ResultsType", [item.name for item in self.proceduretype.resultstype])

    
    def test_get_submissiontype(self):
        try:
            self.assertIsInstance(self.proceduretype.submissiontype, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{type(self.proceduretype.submissiontype)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.proceduretype.submissiontype[0], SubmissionType)
        except AssertionError as e:
            logger.error(f"{self.proceduretype.submissiontype[0]} is not a submissiontype object.")
            raise e
        
    def test_set_submissiontype(self):
        test_insert = SubmissionType(name="Insert SubmissionType")
        self.proceduretype.submissiontype = [test_insert]
        self.assertIn(test_insert, self.proceduretype.submissiontype)
        test_insert = dict(name="Dict SubmissionType")
        self.proceduretype.submissiontype = [test_insert]
        self.assertIn("Dict SubmissionType", [item.name for item in self.proceduretype.submissiontype])

    def test_get_procedure(self):
        try:
            self.assertIsInstance(self.proceduretype.procedure, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{type(self.proceduretype.procedure)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.proceduretype.procedure[0], Procedure)
        except AssertionError as e:
            logger.error(f"{self.proceduretype.procedure[0]} is not a Procedure object.")
            raise e
        
    def test_set_procedure(self):
        test_insert = Procedure(name="Insert Procedure")
        self.proceduretype.procedure = [test_insert]
        self.assertIn(test_insert, self.proceduretype.procedure)
        test_insert = dict(name="Dict Procedure")
        self.proceduretype.procedure = [test_insert]
        self.assertIn("Dict Procedure", [item.name for item in self.proceduretype.procedure])

    def test_construct_dummy_procedure(self):
        run = Run.query()[0]
        pyd = self.proceduretype.construct_dummy_procedure(run=run)
        self.assertIsInstance(pyd, PydProcedure)

    def test_ranked_plate(self):
        self.assertIsInstance(self.proceduretype.ranked_plate, dict)
        self.assertEqual(len(self.proceduretype.ranked_plate.keys()), 96)
        self.assertEqual(max([value[0] for k, value in self.proceduretype.ranked_plate.items()]), 8)
        self.assertEqual(max([value[1] for k, value in self.proceduretype.ranked_plate.items()]), 12)

    def test_total_wells(self):
        self.assertEqual(self.proceduretype.total_wells, 96)

    def test_allowed_result_method(self):
        self.assertIsInstance(self.proceduretype.allowed_result_methods, list)
        self.assertEqual(self.proceduretype.allowed_result_methods[0]['name'], "Test ResultsType")

    def test_to_html(self):
        self.assertIsInstance(self.proceduretype.to_html(), str)
    

class DBProcedure(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.procedure = Procedure.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.procedure, Procedure)

    def test_get_reagentlot(self):
        try:
            self.assertIsInstance(self.procedure.reagentlot, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.procedure.reagentlot)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.procedure.reagentlot[0], ReagentLot)
        except AssertionError as e:
            logger.error(f"{self.procedure.reagentlot[0]} is not a ReagentLot object.")
            raise e
        
    def test_set_reagentlot(self):
        test_insert = ReagentLot(name="Insert ReagentLot")
        self.procedure.reagentlot = [test_insert]
        self.assertIn(test_insert, self.procedure.reagentlot)
        test_insert = dict(lot="Dict ReagentLot")
        self.procedure.reagentlot = [test_insert]
        self.assertIn("Dict ReagentLot", [item.lot for item in self.procedure.reagentlot])

    def test_get_equipment(self):
        try:
            self.assertIsInstance(self.procedure.equipment, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.procedure.equipment)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.procedure.equipment[0], Equipment)
        except AssertionError as e:
            logger.error(f"{self.procedure.equipment[0]} is not a Equipment object.")
            raise e
        
    def test_set_equipment(self):
        test_insert = Equipment(name="Insert Equipment")
        self.procedure.equipment = [test_insert]
        self.assertIn(test_insert, self.procedure.equipment)
        test_insert = dict(name="Dict Equipment")
        self.procedure.equipment = [test_insert]
        self.assertIn("Dict Equipment", [item.name for item in self.procedure.equipment])

    def test_get_sample(self):
        try:
            self.assertIsInstance(self.procedure.sample, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.procedure.sample)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.procedure.sample[0], Sample)
        except AssertionError as e:
            logger.error(f"{self.procedure.sample[0]} is not a Sample object.")
            raise e
        
    def test_set_sample(self):
        test_insert = Sample(sample_id="Insert Sample", _misc_info={"rank":3})
        self.procedure.sample = [test_insert]
        self.assertIn(test_insert, self.procedure.sample)
        self.assertEqual(self.procedure.proceduresampleassociation[0].procedure_rank, 3)
        test_insert = dict(sample_id="Dict Sample")
        self.procedure.sample = [test_insert]
        self.assertIn("Dict Sample", [item.name for item in self.procedure.sample])
        self.assertEqual(self.procedure.proceduresampleassociation[0].procedure_rank, 1)

    def test_get_started_date(self):
        try:
            self.assertIsInstance(self.procedure.started_date, datetime)
        except AssertionError as e:
            logger.error(f"{type(self.procedure.started_date)} is not an datetime object.")
            raise e  
        dt = datetime.combine(date.today() - timedelta(days=1), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
        self.assertEqual(self.procedure.started_date, dt)
        
    def test_set_started_date(self):
        test_insert = "2026-02-02"
        dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
        self.procedure.started_date = test_insert
        self.assertEqual(self.procedure.started_date, dt)

    def test_get_completed_date(self):
        try:
            self.assertIsInstance(self.procedure.completed_date, datetime)
        except AssertionError as e:
            logger.error(f"{type(self.procedure.completed_date)} is not an datetime object.")
            raise e  
        dt = datetime.combine(date.today(), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
        self.assertEqual(self.procedure.completed_date, dt)
        
    def test_set_completed_date(self):
        test_insert = "2026-02-02"
        dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
        self.procedure.completed_date = test_insert
        self.assertEqual(self.procedure.completed_date, dt)

    def test_get_proceduretype(self):
        try:
            self.assertIsInstance(self.procedure.proceduretype, ProcedureType)
        except AssertionError as e:
            logger.error(f"{self.procedure.proceduretype[0]} is not a ProcedureType object.")
            raise e
        
    def test_set_proceduretype(self):
        test_insert = ProcedureType(name="Insert ProcedureType")
        self.procedure.proceduretype = test_insert
        self.assertEqual(test_insert, self.procedure.proceduretype)
        test_insert = dict(name="Dict ProcedureType")
        self.procedure.proceduretype = test_insert
        self.assertEqual("Dict ProcedureType", self.procedure.proceduretype.name)

    def test_get_run(self):
        try:
            self.assertIsInstance(self.procedure.run, Run)
        except AssertionError as e:
            logger.error(f"{self.procedure.run[0]} is not a Run object.")
            raise e
        
    def test_set_run(self):
        clientsub = self.procedure.run.clientsubmission
        test_insert = Run(rsl_plate_number="Insert Run", clientsubmission=clientsub)
        self.procedure.run = test_insert
        self.assertEqual(test_insert, self.procedure.run)
        test_insert = dict(rsl_plate_number="Dict Run", clientsubmission=clientsub)
        self.procedure.run = test_insert
        self.assertEqual("Dict Run", self.procedure.run.rsl_plate_number)

    # TODO: Results and RepeatOF

    def test_custom_context_events(self):
        self.assertCountEqual(self.procedure.custom_context_events.keys(), 
                              ["Add Results", "Add Equipment", "Edit", "Add Comment", "Show Details", "Delete"])
        
    def test_get_default_info(self):
        self.assertCountEqual(self.procedure.get_default_info("form_ignore"), ['reagents', 'ctx', 'id', 'cost', 'extraction_info', 'signed_by', 'comment',
                                                                               'namer', 'submission_object', 'tips', 'contact_phone', 'custom', 'cost_centre',
                                                                               'completed_date', 'control', 'origin_plate', 'filepath', 'sample', 'csv',
                                                                               'comment', 'equipment'])
        self.assertCountEqual(self.procedure.get_default_info("singles"), ['id'])
        self.assertCountEqual(self.procedure.get_default_info("details_ignore"), ['excluded', 'reagents', 'sample', 'extraction_info', 'comment', 'barcode',
                                                                                  'platemap', 'export_map', 'equipment', 'tips', 'custom', 'reagentlot', 'reagent_lot',
                                                                                  'results', 'proceduresampleassociation', 'sample', 'procedurereagentlotassociation',
                                                                                  'procedureequipmentassociation', 'proceduretipsassociation', 'reagent', 'equipment',
                                                                                  'tips', 'control'])
        self.assertCountEqual(self.procedure.get_default_info("form_recover"), ['filepath', 'sample', 'csv', 'comment', 'equipment'])

    def test_get_submissiontype(self):
        self.assertEqual(self.procedure.submissiontype.name, "Default SubmissionType")

    def test_set_cost(self):
        self.assertEqual(self.procedure.cost, 0.0)
        self.procedure.set_cost()
        self.assertIsNotNone(self.procedure.cost)
        self.assertEqual(self.procedure.cost, 1.25)


class DBEquipmentRole(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.equipmentrole = EquipmentRole.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.equipmentrole, EquipmentRole)

    def test_get_equipment(self):
        try:
            self.assertIsInstance(self.equipmentrole.equipment, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.equipmentrole.equipment)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.equipmentrole.equipment[0], Equipment)
        except AssertionError as e:
            logger.error(f"{self.equipmentrole.equipment[0]} is not a Equipment object.")
            raise e
        
    def test_set_equipment(self):
        test_insert = Equipment(name="Insert Equipment")
        self.equipmentrole.equipment = [test_insert]
        self.assertIn(test_insert, self.equipmentrole.equipment)
        test_insert = dict(name="Dict Equipment")
        self.equipmentrole.equipment = [test_insert]
        self.assertIn("Dict Equipment", [item.name for item in self.equipmentrole.equipment])

    def test_get_proceduretype(self):
        try:
            self.assertIsInstance(self.equipmentrole.proceduretype, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.equipmentrole.proceduretype)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.equipmentrole.proceduretype[0], ProcedureType)
        except AssertionError as e:
            logger.error(f"{self.equipmentrole.proceduretype[0]} is not a ProcedureType object.")
            raise e
        
    def test_set_proceduretype(self):
        test_insert = ProcedureType(name="Insert ProcedureType")
        self.equipmentrole.proceduretype = [test_insert]
        self.assertIn(test_insert, self.equipmentrole.proceduretype)
        test_insert = dict(name="Dict ProcedureType")
        self.equipmentrole.proceduretype = [test_insert]
        self.assertIn("Dict ProcedureType", [item.name for item in self.equipmentrole.proceduretype])


class DBEquipment(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.equipment = Equipment.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.equipment, Equipment)

    def test_get_procedure(self):
        try:
            self.assertIsInstance(self.equipment.procedure, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.equipment.procedure)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.equipment.procedure[0], Procedure)
        except AssertionError as e:
            logger.error(f"{self.equipment.procedure[0]} is not a Procedure object.")
            raise e
        
    def test_set_procedure(self):
        test_insert = Procedure(name="Insert Procedure")
        self.equipment.procedure = [test_insert]
        self.assertIn(test_insert, self.equipment.procedure)
        test_insert = dict(name="Dict Procedure")
        self.equipment.procedure = [test_insert]
        self.assertIn("Dict Procedure", [item.name for item in self.equipment.procedure])

    def test_get_equipmentrole(self):
        try:
            self.assertIsInstance(self.equipment.equipmentrole, _AssociationList)
        except AssertionError as e:
            logger.error(f"{type(self.equipment.equipmentrole)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.equipment.equipmentrole[0], EquipmentRole)
        except AssertionError as e:
            logger.error(f"{self.equipment.equipmentrole[0]} is not a EquipmentRole object.")
            raise e
        
    def test_set_equipmentrole(self):
        test_insert = EquipmentRole(name="Insert EquipmentRole")
        self.equipment.equipmentrole = [test_insert]
        self.assertIn(test_insert, self.equipment.equipmentrole)
        test_insert = dict(name="Dict EquipmentRole")
        self.equipment.equipmentrole = [test_insert]
        self.assertIn("Dict EquipmentRole", [item.name for item in self.equipment.equipmentrole])

    def test_nickname(self):
        self.assertEqual(self.equipment.nickname, "Testerino")
        self.equipment.nickname = ""
        self.assertEqual(self.equipment.nickname, self.equipment.name)   


class DBProcess(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.process = Process.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.process, Process)

    def test_get_processversion(self):
        try:
            self.assertIsInstance(self.process.processversion, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{type(self.process.processversion)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.process.processversion[0], ProcessVersion)
        except AssertionError as e:
            logger.error(f"{self.process.processversion[0]} is not a ProcessVersion object.")
            raise e

    def test_set_processversion(self):
        test_insert = ProcessVersion(name="Insert ProcessVersion")
        self.process.processversion = [test_insert]
        self.assertIn(test_insert, self.process.processversion)
        test_insert = dict(version=1.0,
                        date_verified=date.today(),
                        project="NA",
                        active=True)
        self.process.processversion = [test_insert]
        self.assertIn("NA", [item.project for item in self.process.processversion])

    def test_get_equipmentroleequipmentassociation(self):
        try:
            self.assertIsInstance(self.process.equipmentroleequipmentassociation, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{type(self.process.equipmentroleequipmentassociation)} is not an instrumentedlist object.")
            raise e  
        try:
            self.assertIsInstance(self.process.equipmentroleequipmentassociation[0], EquipmentRoleEquipmentAssociation)
        except AssertionError as e:
            logger.error(f"{self.process.equipmentroleequipmentassociation[0]} is not a EquipmentRoleEquipmentAssociation object.")
            raise e
        
    def test_set_equipmentroleequipmentassociation(self):
        test_insert = EquipmentRoleEquipmentAssociation(equipment=Equipment(name="Insert Equipment"), equipmentrole=EquipmentRole(name="Insert EquipmentRole"))
        self.process.equipmentroleequipmentassociation = [test_insert]
        self.assertIn(test_insert, self.process.equipmentroleequipmentassociation)
        
    def test_get_tips(self):
        try:
            self.assertIsInstance(self.process.tips, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{type(self.process.tips)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.process.tips[0], Tips)
        except AssertionError as e:
            logger.error(f"{self.process.tips[0]} is not a Tips object.")
            raise e

    def test_set_tips(self):
        test_insert = Tips(name="Insert Tips")
        self.process.tips = [test_insert]
        self.assertIn(test_insert, self.process.tips)
        test_insert = dict(manufacturer="Sir Tipsalot",
                        capacity=100,
                        ref="YYYY")
        self.process.tips = [test_insert]
        self.assertIn("Sir Tipsalot-YYYY(100)", [item.name for item in self.process.tips])


class DBProcessVersion(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.processversion = ProcessVersion.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.processversion, ProcessVersion)

    def test_get_process(self):
        
        try:
            self.assertIsInstance(self.processversion.process, Process)
        except AssertionError as e:
            logger.error(f"{self.processversion.process} is not a Process object.")
            raise e
        
    def test_set_process(self):
        test_insert = Process(name="Insert Process")
        self.processversion.process = test_insert
        self.assertEqual(test_insert, self.processversion.process)
        test_insert = dict(name="Dict Process")
        self.processversion.process = test_insert
        self.assertEqual("Dict Process", self.processversion.process.name)

    def test_get_name(self):
        self.assertEqual("Test Process-v1.0", self.processversion.name)

    def test_set_active(self):
        self.processversion.active = 0
        self.assertFalse(self.processversion.active)
        self.processversion.active = "on"
        self.assertTrue(self.processversion.active)


class DBTips(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.tips = Tips.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.tips, Tips)

    def test_get_process(self):
        try:
            self.assertIsInstance(self.tips.process, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{self.tips.process} is not an InstrumentedList object.")
        try:
            self.assertIsInstance(self.tips.process[0], Process)
        except AssertionError as e:
            logger.error(f"{self.tips.process[0]} is not a Process object.")
            raise e
        
    def test_set_process(self):
        test_insert = Process(name="Insert Process")
        self.tips.process = [test_insert]
        self.assertIn(test_insert, self.tips.process)
        test_insert = dict(name="Dict Process")
        self.tips.process = [test_insert]
        self.assertIn("Dict Process", [item.name for item in self.tips.process])

    def test_get_tipslot(self):
        try:
            self.assertIsInstance(self.tips.tipslot, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{self.tips.tipslot} is not an InstrumentedList object.")
        try:
            self.assertIsInstance(self.tips.tipslot[0], TipsLot)
        except AssertionError as e:
            logger.error(f"{self.tips.tipslot[0]} is not a Tipslot object.")
            raise e
        
    def test_set_tipslot(self):
        test_insert = TipsLot(lot="XXXXX")
        self.tips.tipslot = [test_insert]
        self.assertIn(test_insert, self.tips.tipslot)
        test_insert = dict(lot="XXXXX",
                        expiry=date(year=date.today().year + 1, month=date.today().month, day=date.today().day),
                        active=True)
        self.tips.tipslot = [test_insert]
        self.assertIn("ACME Tips - XXXX - XXXXX", [item.name for item in self.tips.tipslot])

    def test_get_name(self):
        self.assertEqual(self.tips.name, 'ACME Tips-XXXX(1000)')


class DBTipsLot(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.tipslot = TipsLot.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.tipslot, TipsLot)

    def test_get_expiry(self):
        try:
            self.assertIsInstance(self.tipslot.expiry, datetime)
        except AssertionError as e:
            logger.error(f"{type(self.tipslot.expiry)} is not a date object.")
            raise e  
        expected = datetime.combine(
            date(year=date.today().year + 1, month=date.today().month, day=date.today().day),
            datetime.max.time()).replace(tzinfo=tz("America/Winnipeg"))
        self.assertEqual(self.tipslot.expiry, expected)

    def test_set_expiry(self):
        test_insert = "2026-02-02"
        dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
        self.tipslot.expiry = test_insert
        self.assertEqual(self.tipslot.expiry, dt)

    def test_get_procedureequipmenttipslotassociation(self):
        try:
            self.assertIsInstance(self.tipslot.procedureequipmenttipslotassociation, InstrumentedList)
        except AssertionError as e:
            logger.error(f"{self.tipslot.procedureequipmenttipslotassociation} is not an InstrumentedList object.")
            raise e  
        try:
            self.assertIsInstance(self.tipslot.procedureequipmenttipslotassociation[0], ProcedureEquipmentTipslotAssociation)
        except AssertionError as e:
            logger.error(f"{self.tipslot.procedureequipmenttipslotassociation[0]} is not a ProcedureEquipmentTipsLotAssociation object.")
            raise e
        
    def test_set_procedureequipmenttipslotassociation(self):
        test_insert = ProcedureEquipmentTipslotAssociation(procedure=Procedure(name="Insert Procedure"), equipment=Equipment(name="Insert Equipment"), tipslot=self.tipslot)
        self.tipslot.procedureequipmenttipslotassociation = [test_insert]
        self.assertIn(test_insert, self.tipslot.procedureequipmenttipslotassociation)

    def test_get_capacity(self):
        self.assertEqual(self.tipslot.capacity, "1000uL")

    def test_get_name(self):
        self.assertEqual(self.tipslot.name, "ACME Tips - XXXX - 098765")

    def test_set_active(self):
        self.tipslot.active = 0
        self.assertFalse(self.tipslot.active)
        self.tipslot.active = "on"
        self.assertTrue(self.tipslot.active)


class DBResultsType(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.resultstype = ResultsType.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.resultstype, ResultsType)

    

    def test_get_proceduretype(self):
        try:
            self.assertIsInstance(self.resultstype.proceduretype, list)
        except AssertionError as e:
            logger.error(f"{type(self.resultstype.proceduretype)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.resultstype.proceduretype[0], ProcedureType)
        except AssertionError as e:
            logger.error(f"{self.resultstype.proceduretype[0]} is not a ProcedureType object.")
            raise e
        
    def test_set_proceduretype(self):
        test_insert = ProcedureType(name="Insert ProcedureType")
        self.resultstype.proceduretype = [test_insert]
        self.assertIn(test_insert, self.resultstype.proceduretype)
        test_insert = dict(name="Dict ProcedureType")
        self.resultstype.proceduretype = [test_insert]
        self.assertIn("Dict ProcedureType", [item.name for item in self.resultstype.proceduretype])

    def test_get_results(self):
        try:
            self.assertIsInstance(self.resultstype.results, list)
        except AssertionError as e:
            logger.error(f"{type(self.resultstype.results)} is not an associationlist object.")
            raise e  
        try:
            self.assertIsInstance(self.resultstype.results[0], Results)
        except AssertionError as e:
            logger.error(f"{self.resultstype.results[0]} is not a Results object.")
            raise e

    def test_set_results(self):
        test_insert = Results(result=dict(test="Insert Results", value=1234))
        self.resultstype.results = [test_insert]
        self.assertIn(test_insert, self.resultstype.results)
        

class DBResults(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.results = Results.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.results, Results)

    def test_get_resultstype(self):
        try:
            self.assertIsInstance(self.results.resultstype, ResultsType)
        except AssertionError as e:
            logger.error(f"{self.results.resultstype} is not a ResultsType object.")
            raise e
        
    def test_set_resultstype(self):
        test_insert = ResultsType(name="Insert ResultsType")
        self.results.resultstype = test_insert
        self.assertEqual(test_insert, self.results.resultstype)
        test_insert = dict(name="Dict ResultsType")
        self.results.resultstype = test_insert
        self.assertEqual("Dict ResultsType", self.results.resultstype.name)

    def test_get_procedure(self):
        try:
            self.assertIsInstance(self.results.procedure, Procedure)
        except AssertionError as e:
            logger.error(f"{self.results.procedure} is not a Procedure object.")
            raise e
        
    def test_set_procedure(self):
        test_insert = Procedure(name="Insert Procedure")
        self.results.procedure = test_insert
        self.assertEqual(test_insert, self.results.procedure)
        test_insert = dict(name="Dict Procedure")
        self.results.procedure = test_insert
        self.assertEqual("Dict Procedure", self.results.procedure.name)

    def test_get_name(self):
        self.assertEqual(self.results.name, 'Unknown Run-Unknown ProcedureType->Test Sample (rank=1)-Test ResultsType')

    def test_get_date_analyzed(self):
        try:
            self.assertIsInstance(self.results.date_analyzed, datetime)
        except AssertionError as e:
            logger.error(f"{type(self.results.date_analyzed)} is not a datetime object.")
            raise e  
        dt = datetime.now().replace(tzinfo=tz("America/Winnipeg"))
        self.assertEqual(self.results.date_analyzed.date(), dt.date())
        self.assertEqual(self.results.date_analyzed.hour, dt.hour)
        self.assertEqual(self.results.date_analyzed.minute, dt.minute)

    def test_set_date_analyzed(self):
        test_insert = "2026-02-02"
        dt = datetime.combine(date(2026, 2, 2), time(hour=0, minute=0)).replace(tzinfo=tz("America/Winnipeg"))
        self.results.date_analyzed = test_insert
        self.assertEqual(self.results.date_analyzed, dt)

    def test_get_sampleprocedureassociation(self):
        try:
            self.assertIsInstance(self.results.sampleprocedureassociation, ProcedureSampleAssociation)
        except AssertionError as e:
            logger.error(f"{self.results.sampleprocedureassociation} is not a Proceduresampleassociation object.")
            raise e
        
    def test_set_sampleprocedureassociation(self):
        test_insert = ProcedureSampleAssociation(procedure=Procedure(name="Insert Procedure"), sample=Sample(sample_id="Insert Sample"))
        self.results.sampleprocedureassociation = test_insert
        self.assertEqual(test_insert, self.results.sampleprocedureassociation)

    def test_get_sample_id(self):
        self.assertEqual(self.results.sample_id, "Test Sample")

if __name__ == "__main__":
    main()