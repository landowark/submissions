'''
All kit and reagent related models
'''
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT
from sqlalchemy.orm import relationship
from datetime import date
import logging

logger = logging.getLogger(f'submissions.{__name__}')


# Table containing reagenttype-kittype relationships
reagenttypes_kittypes = Table("_reagentstypes_kittypes", Base.metadata, Column("reagent_types_id", INTEGER, ForeignKey("_reagent_types.id")), Column("kits_id", INTEGER, ForeignKey("_kits.id")))


class KitType(Base):
    """
    Base of kits used in submission processing
    """    
    __tablename__ = "_kits"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64), unique=True) #: name of kit
    submissions = relationship("BasicSubmission", back_populates="extraction_kit") #: submissions this kit was used for
    used_for = Column(JSON) #: list of names of sample types this kit can process
    cost_per_run = Column(FLOAT(2)) #: dollar amount for each full run of this kit NOTE: depreciated, use the constant and mutable costs instead
    # TODO: Change below to 'mutable_cost_column' and 'mutable_cost_sample' before moving to production.
    mutable_cost_column = Column(FLOAT(2)) #: dollar amount per 96 well plate that can change with number of columns (reagents, tips, etc)
    mutable_cost_sample = Column(FLOAT(2)) #: dollar amount that can change with number of samples (reagents, tips, etc)
    constant_cost = Column(FLOAT(2)) #: dollar amount per plate that will remain constant (plates, man hours, etc)
    reagent_types = relationship("ReagentType", back_populates="kits", uselist=True, secondary=reagenttypes_kittypes) #: reagent types this kit contains
    reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id", ondelete='SET NULL', use_alter=True, name="fk_KT_reagentstype_id")) #: joined reagent type id
    
    def __str__(self) -> str:
        """
        a string representing this object

        Returns:
            str: a string representing this object's name
        """        
        return self.name
    

class ReagentType(Base):
    """
    Base of reagent type abstract
    """    
    __tablename__ = "_reagent_types"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: name of reagent type
    kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete="SET NULL", use_alter=True, name="fk_RT_kits_id")) #: id of joined kit type
    kits = relationship("KitType", back_populates="reagent_types", uselist=True, foreign_keys=[kit_id]) #: kits this reagent is used in
    instances = relationship("Reagent", back_populates="type") #: concrete instances of this reagent type
    eol_ext = Column(Interval()) #: extension of life interval

    def __str__(self) -> str:
        """
        string representing this object

        Returns:
            str: string representing this object's name
        """        
        return self.name


class Reagent(Base):
    """
    Concrete reagent instance
    """
    __tablename__ = "_reagents"

    id = Column(INTEGER, primary_key=True) #: primary key
    type = relationship("ReagentType", back_populates="instances") #: joined parent reagent type
    type_id = Column(INTEGER, ForeignKey("_reagent_types.id", ondelete='SET NULL', name="fk_reagent_type_id")) #: id of parent reagent type
    name = Column(String(64)) #: reagent name
    lot = Column(String(64)) #: lot number of reagent
    expiry = Column(TIMESTAMP) #: expiry date - extended by eol_ext of parent programmatically
    submissions = relationship("BasicSubmission", back_populates="reagents", uselist=True) #: submissions this reagent is used in

    def __str__(self) -> str:
        """
        string representing this object

        Returns:
            str: string representing this object's type and lot number
        """    
        return str(self.lot)

    def to_sub_dict(self) -> dict:
        """
        dictionary containing values necessary for gui

        Returns:
            dict: gui friendly dictionary
        """        
        try:
            type = self.type.name.replace("_", " ").title()
        except AttributeError:
            type = "Unknown"
        try:
            place_holder = self.expiry + self.type.eol_ext
            # logger.debug(f"EOL_ext for {self.lot} -- {self.expiry} + {self.type.eol_ext} = {place_holder}")
        except TypeError as e:
            place_holder = date.today()
            logger.debug(f"We got a type error setting {self.lot} expiry: {e}. setting to today for testing")
        except AttributeError as e:
            place_holder = date.today()
            logger.debug(f"We got an attribute error setting {self.lot} expiry: {e}. Setting to today for testing")
        return {
            "type": type,
            "lot": self.lot,
            "expiry": place_holder.strftime("%Y-%m-%d")
        }
    

class Discount(Base):
    """
    Relationship table for client labs for certain kits.
    """
    __tablename__ = "_discounts"

    id = Column(INTEGER, primary_key=True) #: primary key
    kit = relationship("KitType") #: joined parent reagent type
    kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete='SET NULL', name="fk_kit_type_id"))
    client = relationship("Organization") #: joined client lab
    client_id = Column(INTEGER, ForeignKey("_organizations.id", ondelete='SET NULL', name="fk_org_id"))
    name = Column(String(128))
    amount = Column(FLOAT(2))