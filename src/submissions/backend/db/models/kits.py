'''
All kit and reagent related models
'''
from . import Base
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.associationproxy import association_proxy

from datetime import date
import logging

logger = logging.getLogger(f'submissions.{__name__}')


reagenttypes_reagents = Table("_reagenttypes_reagents", Base.metadata, Column("reagent_id", INTEGER, ForeignKey("_reagents.id")), Column("reagenttype_id", INTEGER, ForeignKey("_reagent_types.id")))


class KitType(Base):
    """
    Base of kits used in submission processing
    """    
    __tablename__ = "_kits"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64), unique=True) #: name of kit
    submissions = relationship("BasicSubmission", back_populates="extraction_kit") #: submissions this kit was used for
    
    kit_reagenttype_associations = relationship(
        "KitTypeReagentTypeAssociation",
        back_populates="kit_type",
        cascade="all, delete-orphan",
    )

    # association proxy of "user_keyword_associations" collection
    # to "keyword" attribute
    reagent_types = association_proxy("kit_reagenttype_associations", "reagent_type")

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
        """
        Return ReagentTypes linked to kit through KitTypeReagentTypeAssociation.

        Args:
            required (bool, optional): If true only return required types. Defaults to False.

        Returns:
            list: List of ReagentTypes
        """        
        if required:
            return [item.reagent_type for item in self.kit_reagenttype_associations if item.required == 1]
        else:
            return [item.reagent_type for item in self.kit_reagenttype_associations]
    

    def construct_xl_map_for_use(self, use:str) -> dict:
        """
        Creates map of locations in excel workbook for a SubmissionType

        Args:
            use (str): Submissiontype.name

        Returns:
            dict: Dictionary containing information locations.
        """        
        map = {}
        # Get all KitTypeReagentTypeAssociation for SubmissionType
        assocs = [item for item in self.kit_reagenttype_associations if use in item.uses]
        for assoc in assocs:
            try:
                map[assoc.reagent_type.name] = assoc.uses[use]
            except TypeError:
                continue
        # Get SubmissionType info map
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
    instances = relationship("Reagent", back_populates="type", secondary=reagenttypes_reagents) #: concrete instances of this reagent type
    eol_ext = Column(Interval()) #: extension of life interval
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
    type = relationship("ReagentType", back_populates="instances", secondary=reagenttypes_reagents) #: joined parent reagent type
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

    def to_sub_dict(self, extraction_kit:KitType=None) -> dict:
        """
        dictionary containing values necessary for gui

        Returns:
            dict: gui friendly dictionary
        """        
        if extraction_kit != None:
            # Get the intersection of this reagent's ReagentType and all ReagentTypes in KitType
            try:
                reagent_role = list(set(self.type).intersection(extraction_kit.reagent_types))[0]
            # Most will be able to fall back to first ReagentType in itself because most will only have 1.
            except:
                reagent_role = self.type[0]
        else:
            reagent_role = self.type[0]
        try:
            rtype = reagent_role.name.replace("_", " ").title()
        except AttributeError:
            rtype = "Unknown"
        # Calculate expiry with EOL from ReagentType
        try:
            place_holder = self.expiry + reagent_role.eol_ext
        except TypeError as e:
            place_holder = date.today()
            logger.debug(f"We got a type error setting {self.lot} expiry: {e}. setting to today for testing")
        except AttributeError as e:
            place_holder = date.today()
            logger.debug(f"We got an attribute error setting {self.lot} expiry: {e}. Setting to today for testing")
        return {
            "type": rtype,
            "lot": self.lot,
            "expiry": place_holder.strftime("%Y-%m-%d")
        }
    
    def to_reagent_dict(self, extraction_kit:KitType=None) -> dict:
        """
        Returns basic reagent dictionary.

        Returns:
            dict: Basic reagent dictionary of 'type', 'lot', 'expiry' 
        """        
        if extraction_kit != None:
            # Get the intersection of this reagent's ReagentType and all ReagentTypes in KitType
            try:
                reagent_role = list(set(self.type).intersection(extraction_kit.reagent_types))[0]
            # Most will be able to fall back to first ReagentType in itself because most will only have 1.
            except:
                reagent_role = self.type[0]
        else:
            reagent_role = self.type[0]
        try:
            rtype = reagent_role.name
        except AttributeError:
            rtype = "Unknown"
        return {
            "type": rtype,
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
    """
    Abstract of types of submissions.
    """    
    __tablename__ = "_submission_types"

    id = Column(INTEGER, primary_key=True) #: primary key
    name = Column(String(128), unique=True) #: name of submission type
    info_map = Column(JSON) #: Where basic information is found in the excel workbook corresponding to this type.
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
    """
    Abstract of relationship between kits and their submission type.
    """    
    __tablename__ = "_submissiontypes_kittypes"
    submission_types_id = Column(INTEGER, ForeignKey("_submission_types.id"), primary_key=True)
    kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True)
    mutable_cost_column = Column(FLOAT(2)) #: dollar amount per 96 well plate that can change with number of columns (reagents, tips, etc)
    mutable_cost_sample = Column(FLOAT(2)) #: dollar amount that can change with number of samples (reagents, tips, etc)
    constant_cost = Column(FLOAT(2)) #: dollar amount per plate that will remain constant (plates, man hours, etc)

    kit_type = relationship(KitType, back_populates="kit_submissiontype_associations")

    # reference to the "ReagentType" object
    submission_type = relationship(SubmissionType, back_populates="submissiontype_kit_associations")

    def __init__(self, kit_type=None, submission_type=None):
        self.kit_type = kit_type
        self.submission_type = submission_type
        self.mutable_cost_column = 0.00
        self.mutable_cost_sample = 0.00
        self.constant_cost = 0.00

    def __repr__(self) -> str:
        return f"<SubmissionTypeKitTypeAssociation({self.submission_type.name})"