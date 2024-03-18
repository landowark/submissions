'''
All client organization related models.
'''
from __future__ import annotations
from sqlalchemy import Column, String, INTEGER, ForeignKey, Table
from sqlalchemy.orm import relationship, Query
from . import Base, BaseClass
from tools import check_authorization, setup_lookup
from typing import List
import logging

logger = logging.getLogger(f"submissions.{__name__}")

# table containing organization/contact relationship
orgs_contacts = Table(
                        "_orgs_contacts", 
                        Base.metadata, 
                        Column("org_id", INTEGER, ForeignKey("_organization.id")), 
                        Column("contact_id", INTEGER, ForeignKey("_contact.id")), 
                        # __table_args__ = {'extend_existing': True} 
                        extend_existing = True
                    )

class Organization(BaseClass):
    """
    Base of organization
    """
    
    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: organization name
    submissions = relationship("BasicSubmission", back_populates="submitting_lab") #: submissions this organization has submitted
    cost_centre = Column(String()) #: cost centre used by org for payment
    contacts = relationship("Contact", back_populates="organization", secondary=orgs_contacts) #: contacts involved with this org

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this Organization
        """        
        return f"<Organization({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
                id:int|None=None, 
                name:str|None=None,
                limit:int=0,
                ) -> Organization|List[Organization]:
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
                query = query.filter(cls.id==id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                # logger.debug(f"Looking up organization with name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        return cls.query_return(query=query, limit=limit)
    
    @check_authorization
    def save(self):
        super().save()

class Contact(BaseClass):
    """
    Base of Contact
    """
    
    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: contact name
    email = Column(String(64)) #: contact email
    phone = Column(String(32)) #: contact phone number
    organization = relationship("Organization", back_populates="contacts", uselist=True, secondary=orgs_contacts) #: relationship to joined organization

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this Contact
        """        
        return f"<Contact({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls, 
                name:str|None=None,
                email:str|None=None,
                phone:str|None=None,
                limit:int=0,
                ) -> Contact|List[Contact]:
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
        # super().query(session)
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                # logger.debug(f"Looking up contact with name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        match email:
            case str():
                # logger.debug(f"Looking up contact with email: {name}")
                query = query.filter(cls.email==email)
                limit = 1
            case _:
                pass
        match phone:
            case str():
                # logger.debug(f"Looking up contact with phone: {name}")
                query = query.filter(cls.phone==phone)
                limit = 1
            case _:
                pass
        return cls.query_return(query=query, limit=limit)
    