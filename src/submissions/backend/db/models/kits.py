'''
All kit and reagent related models
'''
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, CheckConstraint
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.associationproxy import association_proxy

from datetime import date
import logging

logger = logging.getLogger(f'submissions.{__name__}')


# # Table containing reagenttype-kittype relationships
# reagenttypes_kittypes = Table("_reagentstypes_kittypes", Base.metadata, 
#                               Column("reagent_types_id", INTEGER, ForeignKey("_reagent_types.id")), 
#                               Column("kits_id", INTEGER, ForeignKey("_kits.id")),
#                             #   The entry will look like ["Bacteria Culture":{"row":1, "column":4}]
#                               Column("uses", JSON),
#                             #   is the reagent required for that kit?
#                               Column("required", INTEGER)
#                               )


class KitType(Base):
    """
    Base of kits used in submission processing
    """    
    __tablename__ = "_kits"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64), unique=True) #: name of kit
    submissions = relationship("BasicSubmission", back_populates="extraction_kit") #: submissions this kit was used for
    # used_for = Column(JSON) #: list of names of sample types this kit can process
    # used_for = relationship("SubmissionType", back_populates="extraction_kits", uselist=True, secondary=submissiontype_kittypes)
    # cost_per_run = Column(FLOAT(2)) #: dollar amount for each full run of this kit NOTE: depreciated, use the constant and mutable costs instead
    # reagent_types = relationship("ReagentType", back_populates="kits", uselist=True, secondary=reagenttypes_kittypes) #: reagent types this kit contains
    # reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id", ondelete='SET NULL', use_alter=True, name="fk_KT_reagentstype_id")) #: joined reagent type id
    # kit_reagenttype_association = 

    kit_reagenttype_associations = relationship(
        "KitTypeReagentTypeAssociation",
        back_populates="kit_type",
        cascade="all, delete-orphan",
    )

    # association proxy of "user_keyword_associations" collection
    # to "keyword" attribute
    reagent_types = association_proxy("kit_reagenttype_associations", "reagenttype")


    kit_submissiontype_associations = relationship(
        "SubmissionTypeKitTypeAssociation",
        back_populates="kit_type",
        cascade="all, delete-orphan",
    )

    used_for = association_proxy("kit_submissiontype_associations", "submission_type")


    def __repr__(self) -> str:
        return f"<KitType({self.name})>"
    
    def __str__(self) -> str:
        """
        a string representing this object

        Returns:
            str: a string representing this object's name
        """        
        return self.name
    
    def get_reagents(self, required:bool=False) -> list:
        if required:
            return [item.reagent_type for item in self.kit_reagenttype_associations if item.required == 1]
        else:
            return [item.reagent_type for item in self.kit_reagenttype_associations]
    

    def construct_xl_map_for_use(self, use:str) -> dict:
        # map = self.used_for[use]
        map = {}
        assocs = [item for item in self.kit_reagenttype_associations if use in item.uses]
        for assoc in assocs:
            try:
                map[assoc.reagent_type.name] = assoc.uses[use]
            except TypeError:
                continue
        try:
            st_assoc = [item for item in self.used_for if use == item.name][0]
            map['info'] = st_assoc.info_map
        except IndexError as e:
            map['info'] = {}
        return map
    
class KitTypeReagentTypeAssociation(Base):
    """
    table containing reagenttype/kittype associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """    
    __tablename__ = "_reagenttypes_kittypes"
    reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id"), primary_key=True)
    kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True)
    uses = Column(JSON)
    required = Column(INTEGER)
    # reagent_type_name = Column(INTEGER, ForeignKey("_reagent_types.name"))

    kit_type = relationship(KitType, back_populates="kit_reagenttype_associations")

    # reference to the "ReagentType" object
    reagent_type = relationship("ReagentType")

    def __init__(self, kit_type=None, reagent_type=None, uses=None, required=1):
        self.kit_type = kit_type
        self.reagent_type = reagent_type
        self.uses = uses
        self.required = required

    @validates('required')
    def validate_age(self, key, value):
        if not 0 <= value < 2:
            raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
        return value
    
    @validates('reagenttype')
    def validate_reagenttype(self, key, value):
        if not isinstance(value, ReagentType):
            raise ValueError(f'{value} is not a reagenttype')
        return value

class ReagentType(Base):
    """
    Base of reagent type abstract
    """    
    __tablename__ = "_reagent_types"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: name of reagent type
    # kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete="SET NULL", use_alter=True, name="fk_RT_kits_id")) #: id of joined kit type
    # kits = relationship("KitType", back_populates="reagent_types", uselist=True, foreign_keys=[kit_id]) #: kits this reagent is used in
    instances = relationship("Reagent", back_populates="type") #: concrete instances of this reagent type
    eol_ext = Column(Interval()) #: extension of life interval
    # required = Column(INTEGER, server_default="1") #: sqlite boolean to determine if reagent type is essential for the kit
    last_used = Column(String(32)) #: last used lot number of this type of reagent

    @validates('required')
    def validate_age(self, key, value):
        if not 0 <= value < 2:
            raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
        return value

    def __str__(self) -> str:
        """
        string representing this object

        Returns:
            str: string representing this object's name
        """        
        return self.name
    
    def __repr__(self):
        return f"ReagentType({self.name})"

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

    def __repr__(self):
        if self.name != None:
            return f"Reagent({self.name}-{self.lot})"
        else:
            return f"Reagent({self.type.name}-{self.lot})"
        

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
    
    def to_reagent_dict(self) -> dict:
        return {
            "type": self.type.name,
            "lot": self.lot,
            "expiry": self.expiry.strftime("%Y-%m-%d")
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

class SubmissionType(Base):

    __tablename__ = "_submission_types"

    id = Column(INTEGER, primary_key=True) #: primary key
    name = Column(String(128), unique=True) #: name of submission type
    info_map = Column(JSON)
    instances = relationship("BasicSubmission", backref="submission_type")
    
    submissiontype_kit_associations = relationship(
        "SubmissionTypeKitTypeAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan",
    )

    kit_types = association_proxy("kit_submissiontype_associations", "kit_type")

    def __repr__(self) -> str:
        return f"<SubmissionType({self.name})>"
    
class SubmissionTypeKitTypeAssociation(Base):

    __tablename__ = "_submissiontypes_kittypes"
    submission_types_id = Column(INTEGER, ForeignKey("_submission_types.id"), primary_key=True)
    kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True)
    mutable_cost_column = Column(FLOAT(2)) #: dollar amount per 96 well plate that can change with number of columns (reagents, tips, etc)
    mutable_cost_sample = Column(FLOAT(2)) #: dollar amount that can change with number of samples (reagents, tips, etc)
    constant_cost = Column(FLOAT(2)) #: dollar amount per plate that will remain constant (plates, man hours, etc)
    # reagent_type_name = Column(INTEGER, ForeignKey("_reagent_types.name"))

    kit_type = relationship(KitType, back_populates="kit_submissiontype_associations")

    # reference to the "ReagentType" object
    submission_type = relationship(SubmissionType, back_populates="submissiontype_kit_associations")

    def __init__(self, kit_type=None, submission_type=None):
        self.kit_type = kit_type
        self.submission_type = submission_type
        self.mutable_cost_column = 0.00
        self.mutable_cost_sample = 0.00
        self.constant_cost = 0.00