'''
All client organization related models.
'''
from __future__ import annotations
import json, yaml, logging
from pathlib import Path
from pprint import pformat
from sqlalchemy import Column, String, INTEGER, ForeignKey, Table
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, Query
from . import Base, BaseClass
from tools import check_authorization, setup_lookup, yaml_regex_creator
from typing import List, Tuple

logger = logging.getLogger(f"submissions.{__name__}")

# table containing organization/contact relationship
orgs_contacts = Table(
    "_orgs_contacts",
    Base.metadata,
    Column("org_id", INTEGER, ForeignKey("_organization.id")),
    Column("contact_id", INTEGER, ForeignKey("_contact.id")),
    extend_existing=True
)


class Organization(BaseClass):
    """
    Base of organization
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: organization name
    submissions = relationship("BasicSubmission",
                               back_populates="submitting_lab")  #: submissions this organization has submitted
    cost_centre = Column(String())  #: cost centre used by org for payment
    contacts = relationship("Contact", back_populates="organization",
                            secondary=orgs_contacts)  #: contacts involved with this org

    @hybrid_property
    def contact(self):
        return self.contacts

    # def __repr__(self) -> str:
    #     return f"<Organization({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              limit: int = 0,
              ) -> Organization | List[Organization]:
        """
        Lookup organizations in the database by a number of parameters.

        Args:
            name (str | None, optional): Name of the organization. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            Organization|List[Organization]: 
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

    @classmethod
    @check_authorization
    def import_from_yml(cls, filepath: Path | str):
        """
        An ambitious project to create a Organization from a yml file

        Args:
            filepath (Path): Filepath of the yml.

        Returns:

        """
        yaml.add_constructor("!regex", yaml_regex_creator)
        if isinstance(filepath, str):
            filepath = Path(filepath)
        if not filepath.exists():
            logging.critical(f"Given file could not be found.")
            return None
        with open(filepath, "r") as f:
            if filepath.suffix == ".json":
                import_dict = json.load(fp=f)
            elif filepath.suffix == ".yml":
                import_dict = yaml.load(stream=f, Loader=yaml.Loader)
            else:
                raise Exception(f"Filetype {filepath.suffix} not supported.")
        data = import_dict['orgs']
        for org in data:
            organ = Organization.query(name=org['name'])
            if organ is None:
                organ = Organization(name=org['name'])
                try:
                    organ.cost_centre = org['cost_centre']
                except KeyError:
                    organ.cost_centre = "xxx"
            for contact in org['contacts']:
                cont = Contact.query(name=contact['name'])
                if cont is None:
                    cont = Contact()
                for k, v in contact.items():
                    cont.__setattr__(k, v)
                organ.contacts.append(cont)
            organ.save()

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniOrganization
        if self.cost_centre:
            cost_centre = self.cost_centre
        else:
            cost_centre = "NA"
        if self.name:
            name = self.name
        else:
            name = "NA"
        return OmniOrganization(instance_object=self,
                                name=name, cost_centre=cost_centre,
                                contact=[item.to_omni() for item in self.contacts])


class Contact(BaseClass):
    """
    Base of Contact
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: contact name
    email = Column(String(64))  #: contact email
    phone = Column(String(32))  #: contact phone number
    organization = relationship("Organization", back_populates="contacts", uselist=True,
                                secondary=orgs_contacts)  #: relationship to joined organization
    submissions = relationship("BasicSubmission", back_populates="contact")  #: submissions this contact has submitted

    # def __repr__(self) -> str:
    #     return f"<Contact({self.name})>"

    @classproperty
    def searchables(cls):
        return []

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[Contact, bool]:
        new = False
        disallowed = []
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            setattr(instance, k, v)
        logger.info(f"Instance from contact query or create: {instance}")
        return instance, new

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
        Lookup contacts in the database by a number of parameters.

        Args:
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

    def to_pydantic(self) -> "PydContact":
        from backend.validators import PydContact
        return PydContact(name=self.name, email=self.email, phone=self.phone)

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniContact
        if self.email:
            email = self.email
        else:
            email = "NA"
        if self.name:
            name = self.name
        else:
            name = "NA"
        if self.phone:
            phone = self.phone
        else:
            phone = "NA"
        return OmniContact(instance_object=self,
                                name=name, email=email,
                                phone=phone)

