"""
All client organization related models.
"""
from __future__ import annotations
import logging
from sqlalchemy import Column, String, INTEGER, ForeignKey, Table
from sqlalchemy.orm import relationship, Query, declared_attr
from . import BaseClass, ClientSubmission
from tools import check_authorization, setup_lookup
from typing import List, TYPE_CHECKING
if TYPE_CHECKING:
    from backend.validators.pydant import PydContact

logger = logging.getLogger(f"submissions.{__name__}")

# NOTE: table containing clientlab/contact relationship
clientlab_contact = Table(
    "_clientlab_contact",
    BaseClass.__base__.metadata,
    Column("clientlab_id", INTEGER, ForeignKey("_clientlab.id")),
    Column("contact_id", INTEGER, ForeignKey("_contact.id")),
    extend_existing=True
)


class ClientLab(BaseClass):
    """
    Base of clientlab
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: clientlab name
    _clientsubmission = relationship("ClientSubmission", back_populates="_clientlab")  #: submission this clientlab has submitted
    cost_centre = Column(String(32))  #: cost centre used by org for payment
    _contact = relationship("Contact", back_populates="_clientlab",
                           secondary=clientlab_contact)  #: contact involved with this org

    ##### Properties #####
    
    @hybrid_property
    def clientsubmission(self):
        return self._clientsubmssion

    @clientsubmission.setter
    def clientsubmission(self, value):
        from backend.validators.pydant import PydClientSubmission
        if not isinstance(value, list):
            value = [value]
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._clientsubmission"
            match item:
                case str():
                    output = ClientSubmission.query(name=item, limit=1)
                case dict():
                    output = ClientSubmission.query_or_create(**item)
                case PydClientSubmission():
                    output = item.to_pydantic()
                case ClientSubmission():
                    output = item
                case _:
                    logger.error(error_msg)
                    continue
            if isinstance(output, ClientSubmission):
                self._clientsubmission.append(output)
            else:
                logger.error(error_msg)

    @hybrid_property
    def contact(self):
        return self._contact

    @contact.setter
    def contact(self, value):
        from backend.validators.pydant import PydContact
        if not isinstance(value, list):
            value = [value]
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._contact"
            match item:
                case str():
                    output = Contact.query(name=item, limit=1)
                case dict():
                    output = Contact.query_or_create(**item)
                case PydContact():
                    output = item.to_pydantic()
                case Contact():
                    output = item
                case _:
                    logger.error(f"Can't add item {item} to {self.name}._contact")
                    continue
            if isinstance(output, Contact):
                self._contact.append(output)
            else:
                logger.error(f"Can't add item {item} to {self.name}._contact")

    ##### Query Function #####
    
    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              limit: int = 0,
              ) -> ClientLab | List[ClientLab]:
        """
        Lookup clientlabs in the database by a number of parameters.

        Args:
            id (int | None, optional): id integer of the clientlab. Defaults to None.
            name (str | None, optional): Name of the clientlab. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            ClientLab|List[ClientLab]:
        """
        query: Query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name.startswith(name))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @check_authorization
    def save(self):
        super().save()


class Contact(BaseClass):
    """
    Base of Contact
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: contact name
    email = Column(String(64))  #: contact email
    phone = Column(String(16))  #: contact phone number
    _clientlab = relationship("ClientLab", back_populates="_contact", uselist=True,
                             secondary=clientlab_contact)  #: relationship to joined clientlab
    _clientsubmission = relationship("ClientSubmission", back_populates="_contact")  #: procedure this contact has submitted

    @hybrid_property
    def clientlab(self):
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value):
        from backend.validators.pydant import PydClientLab
        if not isinstance(value, list):
            value = [value]
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._clientlab"
            match item:
                case str():
                    output = ClientLab.query(name=item, limit=1)
                case dict():
                    output = ClientLab.query_or_create(**item)
                case PydClientLab():
                    output = item.to_pydantic()
                case ClientLab():
                    output = item
                case _:
                    logger.error(error_msg)
                    continue
            if isinstance(output, ClientLab):
                self._contact.append(output)
            else:
                logger.error(error_msg)

    @hybrid_property
    def clientsubmission(self):
        return self._clientsubmssion

    @clientsubmission.setter
    def clientsubmission(self, value):
        from backend.validators.pydant import PydClientSubmission
        if not isinstance(value, list):
            value = [value]
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._clientsubmission"
            match item:
                case str():
                    output = ClientSubmission.query(name=item, limit=1)
                case dict():
                    output = ClientSubmission.query_or_create(**item)
                case PydClientSubmission():
                    output = item.to_pydantic()
                case ClientSubmission():
                    output = item
                case _:
                    logger.error(error_msg)
                    continue
            if isinstance(output, ClientSubmission):
                self._clientsubmission.append(output)
            else:
                logger.error(error_msg)

    # @classproperty
    @classmethod
    @declared_attr
    def searchables(cls):
        return []

    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              email: str | None = None,
              phone: str | None = None,
              limit: int = 0,
              ) -> Contact | List[Contact]:
        """
        Lookup contact in the database by a number of parameters.

        Args:
            id (int | None, optional): id integer of the contact. Defaults to None.
            name (str | None, optional): Name of the contact. Defaults to None.
            email (str | None, optional): Email of the contact. Defaults to None.
            phone (str | None, optional): Phone number of the contact. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            Contact|List[Contact]: Contact(s) of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name.title())
                limit = 1
            case _:
                pass
        match email:
            case str():
                query = query.filter(cls.email == email)
                limit = 1
            case _:
                pass
        match phone:
            case str():
                query = query.filter(cls.phone == phone)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def to_pydantic(self) -> PydContact:
        from backend.validators import PydContact
        return PydContact(name=self.name, email=self.email, phone=self.phone)
