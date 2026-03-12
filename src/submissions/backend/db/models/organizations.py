"""
All client organization related models.
"""
from __future__ import annotations
import logging
from sqlalchemy import Column, String, INTEGER, ForeignKey, Table
from sqlalchemy.orm import relationship, Query
from sqlalchemy.ext.hybrid import hybrid_property
from . import BaseClass
from tools import check_authorization, setup_lookup
from typing import List, TYPE_CHECKING
# if TYPE_CHECKING:
#     from backend.validators.pydant import PydContact

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
    discount = relationship("Discount", back_populates="_clientlab")

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
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
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
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
        return self._contact

    @contact.setter
    def contact(self, value):
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
    tel = Column(String(16))  #: contact phone number
    _clientlab = relationship("ClientLab", back_populates="_contact", uselist=True,
                             secondary=clientlab_contact)  #: relationship to joined clientlab
    _clientsubmission = relationship("ClientSubmission", back_populates="_contact")  #: procedure this contact has submitted

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
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
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value):
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
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
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
              tel: str | None = None,
              limit: int = 0,
              ) -> Contact | List[Contact]:
        """
        Lookup contact in the database by a number of parameters.

        Args:
            id (int | None, optional): id integer of the contact. Defaults to None.
            name (str | None, optional): Name of the contact. Defaults to None.
            email (str | None, optional): Email of the contact. Defaults to None.
            tel (str | None, optional): Phone number of the contact. Defaults to None.
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
        match tel:
            case str():
                query = query.filter(cls.tel == tel)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)
