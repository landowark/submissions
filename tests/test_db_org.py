from custom_resources import DatabaseTestCase
from backend.db.models import (
    ClientLab,
    Contact, ClientSubmission
    )
from unittest import main
import logging

logger = logging.getLogger(f"testing.{__name__}")

class DBClientLab(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.clientlab = ClientLab.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.clientlab, ClientLab)

    def test_get_clientsubmission(self):
        try:
            self.assertIsInstance(self.clientlab.clientsubmission, list)
        except AssertionError as e:
            logger.error(f"{self.clientlab.clientsubmission} is not a list object.")
            raise e  
        try:
            self.assertIsInstance(self.clientlab.clientsubmission[0], ClientSubmission)
        except AssertionError as e:
            logger.error(f"{self.clientlab.clientsubmission[0]} is not a ClientSubmission object.")
            raise e
        
    def test_set_clientsubmission(self):
        test_insert = ClientSubmission(submitter_plate_id="Insert Submission")
        self.clientlab.clientsubmission = [test_insert]
        self.assertIn(test_insert, self.clientlab.clientsubmission)
        test_insert = dict(submitter_plate_id="Dict Submission")
        self.clientlab.clientsubmission = [test_insert]
        self.assertIn("Dict Submission", [item.submitter_plate_id for item in self.clientlab.clientsubmission])

    def test_get_contact(self):
        try:
            self.assertIsInstance(self.clientlab.contact, list)
        except AssertionError as e:
            logger.error(f"{self.clientlab.contact} is not a list object.")
            raise e
        try:
            self.assertIsInstance(self.clientlab.contact[0], Contact)
        except AssertionError as e:
            logger.error(f"{self.clientlab.contact[0]} is not a Contact object.")
            raise e
        
    def test_set_contact(self):
        test_insert = Contact(name="Insert Contactington")
        self.clientlab.contact = [test_insert]
        self.assertIn(test_insert, self.clientlab.contact)
        test_insert = dict(name="Dict Contactington")
        self.clientlab.contact = [test_insert]
        self.assertIn("Dict Contactington", [item.name for item in self.clientlab.contact])


class DBContact(DatabaseTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.contact = Contact.query(limit=1)

    def test_query(self):
        self.assertIsInstance(self.contact, Contact)

    def test_get_clientsubmission(self):
        try:
            self.assertIsInstance(self.contact.clientsubmission, list)
        except AssertionError as e:
            logger.error(f"{self.contact.clientsubmission} is not a list object.")
            raise e  
        try:
            self.assertIsInstance(self.contact.clientsubmission[0], ClientSubmission)
        except AssertionError as e:
            logger.error(f"{self.contact.clientsubmission[0]} is not a ClientSubmission object.")
            raise e
        
    def test_set_clientsubmission(self):
        test_insert = ClientSubmission(submitter_plate_id="Insert Submission")
        self.contact.clientsubmission = [test_insert]
        self.assertIn(test_insert, self.contact.clientsubmission)
        test_insert = dict(submitter_plate_id="Dict Submission")
        self.contact.clientsubmission = [test_insert]
        self.assertIn("Dict Submission", [item.submitter_plate_id for item in self.contact.clientsubmission])

    def test_get_clientlab(self):
        try:
            self.assertIsInstance(self.contact.clientlab, list)
        except AssertionError as e:
            logger.error(f"{self.contact.clientlab} is not a list object.")
            raise e
        try:
            self.assertIsInstance(self.contact.clientlab[0], ClientLab)
        except AssertionError as e:
            logger.error(f"{self.contact.clientlab[0]} is not a Contact object.")
            raise e
        
    def test_set_contact(self):
        test_insert = ClientLab(name="Insert ClientLab")
        self.contact.clientlab = [test_insert]
        self.assertIn(test_insert, self.contact.clientlab)
        test_insert = dict(name="Dict ClientLab")
        self.contact.clientlab = [test_insert]
        self.assertIn("Dict ClientLab", [item.name for item in self.contact.clientlab])


if __name__ == "__main__":
    main()