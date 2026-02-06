from custom_resources import DatabaseTestCase
from backend.db.models import (
    ProcedureTypeReagentRoleAssociation,
    ReagentRoleReagentAssociation,
    ProcedureType,
    ReagentRole
)
from sqlalchemy.orm import Session
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.ext.associationproxy import _AssociationList

from unittest import main
import logging


logger = logging.getLogger(f"testing.{__name__}")


class DBProcedureTypeReagentRoleAssociation(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.proceduretypereagentroleassociation = ProcedureTypeReagentRoleAssociation.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.proceduretypereagentroleassociation, ProcedureTypeReagentRoleAssociation)

    def test_get_proceduretype(self):
        try:
            self.assertIsInstance(self.proceduretypereagentroleassociation.proceduretype, ProcedureType)
        except AssertionError as e:
            logger.error(f"{self.proceduretypereagentroleassociation.proceduretype} is not a ProcedureType object.")
            raise e
        
    def test_set_proceduretype(self):
        test_insert = ProcedureType(name="Insert ProcedureType")
        self.proceduretypereagentroleassociation.proceduretype = test_insert
        self.assertEqual(self.proceduretypereagentroleassociation.proceduretype, test_insert)
        test_insert = dict(name="Dict ProcedureType")
        self.proceduretypereagentroleassociation.proceduretype = test_insert
        self.assertEqual("Dict ProcedureType", self.proceduretypereagentroleassociation.proceduretype.name)

    def test_get_reagentrole(self):
        try:
            self.assertIsInstance(self.proceduretypereagentroleassociation.reagentrole, ReagentRole)
        except AssertionError as e:
            logger.error(f"{self.proceduretypereagentroleassociation.reagentrole} is not a ReagentRole object.")
            raise e
        
    def test_set_reagentrole(self):
        test_insert = ReagentRole(name="Insert ReagentRole")
        self.proceduretypereagentroleassociation.reagentrole = test_insert
        self.assertEqual(self.proceduretypereagentroleassociation.reagentrole, test_insert)
        test_insert = dict(name="Dict ReagentRole")
        self.proceduretypereagentroleassociation.reagentrole = test_insert
        self.assertEqual("Dict ReagentRole", self.proceduretypereagentroleassociation.reagentrole.name)

    def test_get_all_relevant_reagents(self):
        reagents = self.proceduretypereagentroleassociation.get_all_relevant_reagents()
        self.assertIsInstance(reagents, _AssociationList)
        for reagent in reagents:
            self.assertIsInstance(reagent, ReagentRoleReagentAssociation)
        


class DBReagentRoleReagentAssociation(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.reagentrolereagentassociation = ReagentRoleReagentAssociation.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.reagentrolereagentassociation, ReagentRoleReagentAssociation)

if __name__ == '__main__':
    main()