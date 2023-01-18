from . import Base
from sqlalchemy import Column, String, TIMESTAMP, JSON, Float, INTEGER, ForeignKey, UniqueConstraint, Table
from sqlalchemy.orm import relationship, validates


orgs_contacts = Table("_orgs_contacts", Base.metadata, Column("org_id", INTEGER, ForeignKey("_organizations.id")), Column("contact_id", INTEGER, ForeignKey("_contacts.id")))


class Organization(Base):

    __tablename__ = "_organizations"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64))
    submissions = relationship("BasicSubmission", back_populates="submitting_lab")
    cost_centre = Column(String())
    contacts = relationship("Contact", back_populates="organization", secondary=orgs_contacts)
    contact_ids = Column(INTEGER, ForeignKey("_contacts.id", ondelete="SET NULL", name="fk_org_contact_id"))

    def __str__(self):
        return self.name.replace("_", " ").title()


class Contact(Base):

    __tablename__ = "_contacts"

    id = id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64))
    email = Column(String(64))
    phone = Column(String(32))
    organization = relationship("Organization", back_populates="contacts", uselist=True)
    # organization_id = Column(INTEGER, ForeignKey("_organizations.id"))

