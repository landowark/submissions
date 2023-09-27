'''
All client organization related models.
'''
from . import Base
from sqlalchemy import Column, String, INTEGER, ForeignKey, Table
from sqlalchemy.orm import relationship

# table containing organization/contact relationship
orgs_contacts = Table("_orgs_contacts", Base.metadata, Column("org_id", INTEGER, ForeignKey("_organizations.id")), Column("contact_id", INTEGER, ForeignKey("_contacts.id")))


class Organization(Base):
    """
    Base of organization
    """
    __tablename__ = "_organizations"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: organization name
    submissions = relationship("BasicSubmission", back_populates="submitting_lab") #: submissions this organization has submitted
    cost_centre = Column(String()) #: cost centre used by org for payment
    contacts = relationship("Contact", back_populates="organization", secondary=orgs_contacts) #: contacts involved with this org

    def __str__(self) -> str:
        """
        String representing organization

        Returns:
            str: string representing organization name
        """        
        return self.name.replace("_", " ").title()
    
    def __repr__(self) -> str:
        return f"<Organization({self.name})>"


class Contact(Base):
    """
    Base of Contact
    """
    __tablename__ = "_contacts"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: contact name
    email = Column(String(64)) #: contact email
    phone = Column(String(32)) #: contact phone number
    organization = relationship("Organization", back_populates="contacts", uselist=True, secondary=orgs_contacts) #: relationship to joined organization

    def __repr__(self) -> str:
        return f"<Contact({self.name})>"

