"""
All client organization related models.

This module contains SQLAlchemy models for managing client organizations and their contacts.
It provides the ClientLab and Contact classes which handle relationships between
organizations, their contacts, and submitted samples.

Classes:
    ClientLab: Represents a client laboratory organization
    Contact: Represents a contact person associated with client labs
"""
from __future__ import annotations
import logging
from sqlalchemy import Column, String, INTEGER, ForeignKey, Table
from sqlalchemy.orm import relationship, Query
from sqlalchemy.ext.hybrid import hybrid_property
from . import BaseClass
from tools import check_authorization, setup_lookup
from typing import List

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
    Represents a client laboratory organization.

    This class manages client lab information including name, cost center,
    associated contacts, and submitted samples. It provides methods for
    querying and managing client lab data.

    :ivar id: Primary key identifier for the client lab
    :vartype id: int
    :ivar name: Name of the client laboratory
    :vartype name: str
    :ivar cost_centre: Cost center code used by the organization for payment
    :vartype cost_centre: str
    :ivar _clientsubmission: Relationship to ClientSubmission objects
    :vartype _clientsubmission: list[ClientSubmission]
    :ivar _contact: Relationship to Contact objects via many-to-many association
    :vartype _contact: list[Contact]
    :ivar discount: Relationship to Discount objects
    :vartype discount: list[Discount]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: clientlab name
    _clientsubmission = relationship("ClientSubmission", back_populates="_clientlab")  #: submission this clientlab has submitted
    cost_centre = Column(String(32))  #: cost centre used by org for payment
    _contact = relationship("Contact", back_populates="_clientlab",
                           secondary=clientlab_contact)  #: contact involved with this org
    discount = relationship("Discount", back_populates="_clientlab")

    def __init__(self, *args, **kwargs):
        """
        Initialize a ClientLab instance.

        Resolves shorthand inputs (strings/dicts) for clientsubmission and contact
        into actual model instances before setting attributes. This allows callers
        to pass names and have the associations properly wired.

        :param clientsubmission: Client submission data (string name, dict, or PydClientSubmission)
        :type clientsubmission: str | dict | PydClientSubmission | None
        :param contact: Contact data (string name, dict, or PydContact)
        :type contact: str | dict | PydContact | None
        :param args: Positional arguments passed to parent class
        :param kwargs: Keyword arguments passed to parent class
        """
        clientsubmission = kwargs.pop('clientsubmission', None)
        contact = kwargs.pop('contact', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve clientsubmission
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'clientsubmission': clientsubmission})
                except Exception:
                    pass
        # Resolve contact
        if contact is not None:
            try:
                self.contact = contact
            except Exception:
                try:
                    self._misc_info.update({'contact': contact})
                except Exception:
                    pass

    ##### Properties #####
    
    @hybrid_property
    def clientsubmission(self):
        """
        Get the list of client submissions associated with this client lab.

        :return: List of ClientSubmission objects
        :rtype: list[ClientSubmission]
        """
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
        """
        Set client submissions for this client lab.

        Accepts various input formats and resolves them to ClientSubmission instances.

        :param value: Client submission data to associate (string, dict, PydClientSubmission, or ClientSubmission)
        :type value: str | dict | PydClientSubmission | ClientSubmission | list | None
        :raises ValueError: If value cannot be resolved to a valid ClientSubmission
        """
        from backend.validators.pydant import PydClientSubmission
        from backend.db.models import ClientSubmission
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = ClientSubmission.query(name=item, limit=1)
                case dict():
                    output = ClientSubmission.query_or_create(**item)
                case PydClientSubmission():
                    output = item.to_sql(update=False)
                case ClientSubmission():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for clientsubmission")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ClientSubmission):
                self._clientsubmission.append(output)
            else:
                logger.error(f"Could not add {type(output)} to _clientsubmission")

    @hybrid_property
    def contact(self):
        """
        Get the list of contacts associated with this client lab.

        :return: List of Contact objects
        :rtype: list[Contact]
        """
        return self._contact

    @contact.setter
    def contact(self, value):
        """
        Set contacts for this client lab.

        Accepts various input formats and resolves them to Contact instances.

        :param value: Contact data to associate (string, dict, PydContact, or Contact)
        :type value: str | dict | PydContact | Contact | list | None
        :raises ValueError: If value cannot be resolved to a valid Contact
        """
        from backend.validators.pydant import PydContact
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Contact.query(name=item, limit=1)
                case dict():
                    output = Contact.query_or_create(**item)
                case PydContact():
                    output = item.to_sql(update=False)
                case Contact():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for contact")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Contact):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Can't add {type(output)} to _contact")
        self._contact = list_

    ##### Query Function #####
    
    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              limit: int = 0,
              **kwargs) -> ClientLab | List[ClientLab]:
        """
        Lookup client labs in the database by various parameters.

        :param id: ID integer of the client lab
        :type id: int | None
        :param name: Name of the client lab (partial match)
        :type name: str | None
        :param limit: Maximum number of results to return (0 = all)
        :type limit: int
        :param kwargs: Additional keyword arguments
        :return: Single ClientLab if id/name specified, otherwise list of ClientLab objects
        :rtype: ClientLab | List[ClientLab]
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
        """
        Save the client lab to the database with authorization check.

        Calls the parent class save method after performing authorization validation.
        """
        super().save()
        


class Contact(BaseClass):
    """
    Represents a contact person associated with client laboratories.

    This class manages contact information including name, email, phone number,
    and relationships to client labs and submissions. It provides methods for
    querying and managing contact data.

    :ivar id: Primary key identifier for the contact
    :vartype id: int
    :ivar name: Full name of the contact person
    :vartype name: str
    :ivar email: Email address of the contact
    :vartype name: str
    :ivar tel: Telephone number of the contact
    :vartype tel: str
    :ivar _clientlab: Relationship to ClientLab objects via many-to-many association
    :vartype _clientlab: list[ClientLab]
    :ivar _clientsubmission: Relationship to ClientSubmission objects
    :vartype _clientsubmission: list[ClientSubmission]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: contact name
    email = Column(String(64))  #: contact email
    tel = Column(String(16))  #: contact phone number
    _clientlab = relationship("ClientLab", back_populates="_contact", uselist=True,
                             secondary=clientlab_contact)  #: relationship to joined clientlab
    _clientsubmission = relationship("ClientSubmission", back_populates="_contact")  #: procedure this contact has submitted

    def __init__(self, *args, **kwargs):
        """
        Initialize a Contact instance.

        Resolves shorthand inputs (strings/dicts) for clientsubmission and clientlab
        into actual model instances before setting attributes. This allows callers
        to pass names and have the associations properly wired.

        :param clientsubmission: Client submission data (string name, dict, or PydClientSubmission)
        :type clientsubmission: str | dict | PydClientSubmission | None
        :param clientlab: Client lab data (string name, dict, or PydClientLab)
        :type clientlab: str | dict | PydClientLab | None
        :param args: Positional arguments passed to parent class
        :param kwargs: Keyword arguments passed to parent class
        """
        clientsubmission = kwargs.pop('clientsubmission', None)
        clientlab = kwargs.pop('clientlab', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'clientsubmission': clientsubmission})
                except Exception:
                    pass
        # Resolve reagentrole
        if clientlab is not None:
            try:
                self.clientlab = clientlab
            except Exception:
                try:
                    self._misc_info.update({'clientlab': clientlab})
                except Exception:
                    pass


    ##### Properties #####
    
    @hybrid_property
    def clientlab(self):
        """
        Get the list of client labs associated with this contact.

        :return: List of ClientLab objects
        :rtype: list[ClientLab]
        """
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value):
        """
        Set client labs for this contact.

        Accepts various input formats and resolves them to ClientLab instances.

        :param value: Client lab data to associate (string, dict, PydClientLab, or ClientLab)
        :type value: str | dict | PydClientLab | ClientLab | list | None
        :raises ValueError: If value cannot be resolved to a valid ClientLab
        """
        from backend.validators.pydant import PydClientLab
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ClientLab.query(name=item, limit=1)
                case dict():
                    output = ClientLab.query_or_create(**item)
                case PydClientLab():
                    output = item.to_sql(update=False)
                    if isinstance(output, tuple):
                        output = output[0]
                case ClientLab():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for clientlab")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ClientLab):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to _clientlab")
        self._clientlab = list_

    @hybrid_property
    def clientsubmission(self):
        """
        Get the list of client submissions associated with this contact.

        :return: List of ClientSubmission objects
        :rtype: list[ClientSubmission]
        """
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
        """
        Set client submissions for this contact.

        Accepts various input formats and resolves them to ClientSubmission instances.

        :param value: Client submission data to associate (string, dict, PydClientSubmission, or ClientSubmission)
        :type value: str | dict | PydClientSubmission | ClientSubmission | list | None
        :raises ValueError: If value cannot be resolved to a valid ClientSubmission
        """
        from backend.validators.pydant import PydClientSubmission
        from backend.db.models import ClientSubmission
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = ClientSubmission.query(name=item, limit=1)
                case dict():
                    output = ClientSubmission.query_or_create(**item)
                case PydClientSubmission():
                    output = item.to_sql(update=False)
                case ClientSubmission():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for clientsubmission")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ClientSubmission):
                self._clientsubmission.append(output)
            else:
                logger.error(f"Could not add {type(output)} to _clientsubmission")

    ##### Query Function #####

    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              email: str | None = None,
              tel: str | None = None, # Named tel to setup javascript compatibility, but this is the phone number of the contact
              limit: int = 0,
              ) -> Contact | List[Contact]:
        """
        Lookup contacts in the database by various parameters.

        :param id: ID integer of the contact
        :type id: int | None
        :param name: Name of the contact (exact match, title case)
        :type name: str | None
        :param email: Email address of the contact (exact match)
        :type email: str | None
        :param tel: Phone number of the contact (exact match)
        :type tel: str | None
        :param limit: Maximum number of results to return (0 = all)
        :type limit: int
        :return: Single Contact if specific parameters match, otherwise list of Contact objects
        :rtype: Contact | List[Contact]
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
        match tel:
            case str():
                query = query.filter(cls.tel == tel)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)
