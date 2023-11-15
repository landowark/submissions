'''
All kit and reagent related models
'''
from __future__ import annotations
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, func
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date
import logging
from tools import check_authorization, Base, setup_lookup, query_return, Report, Result
from typing import List
from . import Organization

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
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    reagent_types = association_proxy("kit_reagenttype_associations", "reagent_type", creator=lambda RT: KitTypeReagentTypeAssociation(reagent_type=RT))

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
    
    def get_reagents(self, required:bool=False, submission_type:str|None=None) -> list:
        """
        Return ReagentTypes linked to kit through KitTypeReagentTypeAssociation.

        Args:
            required (bool, optional): If true only return required types. Defaults to False.
            submission_type (str | None, optional): Submission type to narrow results. Defaults to None.

        Returns:
            list: List of reagent types
        """        
        if submission_type != None:
            relevant_associations = [item for item in self.kit_reagenttype_associations if submission_type in item.uses.keys()]
        else:
            relevant_associations = [item for item in self.kit_reagenttype_associations]
        if required:
            return [item.reagent_type for item in relevant_associations if item.required == 1]
        else:
            return [item.reagent_type for item in relevant_associations]
    
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

    @check_authorization
    def save(self):
        self.metadata.session.add(self)
        self.metadata.session.commit()

    @classmethod
    @setup_lookup
    def query(cls,
              name:str=None,
              used_for:str|SubmissionType|None=None,
              id:int|None=None,
              limit:int=0
              ) -> KitType|List[KitType]:
        """
        Lookup a list of or single KitType.

        Args:
        ctx (Settings): Settings object passed down from gui
        name (str, optional): Name of desired kit (returns single instance). Defaults to None.
        used_for (str | models.Submissiontype | None, optional): Submission type the kit is used for. Defaults to None.
        id (int | None, optional): Kit id in the database. Defaults to None.
        limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
        models.KitType|List[models.KitType]: KitType(s) of interest.
        """    
        query: Query = cls.metadata.session.query(cls)
        match used_for:
            case str():
                logger.debug(f"Looking up kit type by use: {used_for}")
                query = query.filter(cls.used_for.any(name=used_for))
            case SubmissionType():
                query = query.filter(cls.used_for.contains(used_for))
            case _:
                pass
        match name:
            case str():
                logger.debug(f"Looking up kit type by name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        match id:
            case int():
                logger.debug(f"Looking up kit type by id: {id}")
                query = query.filter(cls.id==id)
                limit = 1
            case str():
                logger.debug(f"Looking up kit type by id: {id}")
                query = query.filter(cls.id==int(id))
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)

class ReagentType(Base):
    """
    Base of reagent type abstract
    """    
    __tablename__ = "_reagent_types"

    id = Column(INTEGER, primary_key=True) #: primary key  
    name = Column(String(64)) #: name of reagent type
    instances = relationship("Reagent", back_populates="type", secondary=reagenttypes_reagents) #: concrete instances of this reagent type
    eol_ext = Column(Interval()) #: extension of life interval
    
    reagenttype_kit_associations = relationship(
        "KitTypeReagentTypeAssociation",
        back_populates="reagent_type",
        cascade="all, delete-orphan",
    )

    # association proxy of "user_keyword_associations" collection
    # to "keyword" attribute
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    kit_types = association_proxy("reagenttype_kit_associations", "kit_type", creator=lambda kit: KitTypeReagentTypeAssociation(kit_type=kit))

    def __str__(self) -> str:
        """
        string representing this object

        Returns:
            str: string representing this object's name
        """        
        return self.name
    
    def __repr__(self):
        return f"ReagentType({self.name})"
    
    @classmethod
    @setup_lookup
    def query(cls,
                name: str|None=None,
                kit_type: KitType|str|None=None,
                reagent: Reagent|str|None=None,
                limit:int=0,
                ) -> ReagentType|List[ReagentType]:
        """
        Lookup reagent types in the database.

        Args:
            ctx (Settings): Settings object passed down from gui.
            name (str | None, optional): Reagent type name. Defaults to None.
            limit (int, optional): maxmimum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.ReagentType|List[models.ReagentType]: ReagentType or list of ReagentTypes matching filter.
        """
        query: Query = cls.metadata.session.query(cls)
        if (kit_type != None and reagent == None) or (reagent != None and kit_type == None):
            raise ValueError("Cannot filter without both reagent and kit type.")
        elif kit_type == None and reagent == None:
            pass
        else:
            match kit_type:
                case str():
                    kit_type = KitType.query(name=kit_type)
                case _:
                    pass
            match reagent:
                case str():
                    reagent = Reagent.query(lot_number=reagent)
                case _:
                    pass
            assert reagent.type != []
            logger.debug(f"Looking up reagent type for {type(kit_type)} {kit_type} and {type(reagent)} {reagent}")
            logger.debug(f"Kit reagent types: {kit_type.reagent_types}")
            # logger.debug(f"Reagent reagent types: {reagent._sa_instance_state}")
            result = list(set(kit_type.reagent_types).intersection(reagent.type))
            logger.debug(f"Result: {result}")
            try:
                return result[0]
            except IndexError:
                return None
        match name:
            case str():
                logger.debug(f"Looking up reagent type by name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)
    
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
    last_used = Column(String(32)) #: last used lot number of this type of reagent

    kit_type = relationship(KitType, back_populates="kit_reagenttype_associations")

    # reference to the "ReagentType" object
    reagent_type = relationship(ReagentType, back_populates="reagenttype_kit_associations")

    def __init__(self, kit_type=None, reagent_type=None, uses=None, required=1):
        logger.debug(f"Parameters: Kit={kit_type}, RT={reagent_type}, Uses={uses}, Required={required}")
        self.kit_type = kit_type
        self.reagent_type = reagent_type
        self.uses = uses
        self.required = required

    def __repr__(self) -> str:
        return f"<KitTypeReagentTypeAssociation({self.kit_type} & {self.reagent_type})>"

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
    
    @classmethod
    @setup_lookup
    def query(cls,
                kit_type:KitType|str|None,
                reagent_type:ReagentType|str|None,
                limit:int=0
                ) -> KitTypeReagentTypeAssociation|List[KitTypeReagentTypeAssociation]:
        """
        Lookup junction of ReagentType and KitType

        Args:
            ctx (Settings): Settings object passed down from gui.
            kit_type (models.KitType | str | None): KitType of interest.
            reagent_type (models.ReagentType | str | None): ReagentType of interest.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]: Junction of interest.
        """    
        query: Query = cls.metadata.session.query(cls)
        match kit_type:
            case KitType():
                query = query.filter(cls.kit_type==kit_type)
            case str():
                query = query.join(KitType).filter(KitType.name==kit_type)
            case _:
                pass
        match reagent_type:
            case ReagentType():
                query = query.filter(cls.reagent_type==reagent_type)
            case str():
                query = query.join(ReagentType).filter(ReagentType.name==reagent_type)
            case _:
                pass
        if kit_type != None and reagent_type != None:
            limit = 1
        return query_return(query=query, limit=limit)

    def save(self) -> Report:
        report = Report()
        self.metadata.session.add(self)
        self.metadata.session.commit()
        return report

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
            return f"<Reagent({self.name}-{self.lot})>"
        else:
            return f"<Reagent({self.type.name}-{self.lot})>"
        
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

        Args:
            extraction_kit (KitType, optional): KitType to use to get reagent type. Defaults to None.

        Returns:
            dict: _description_
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
    
    def to_reagent_dict(self, extraction_kit:KitType|str=None) -> dict:
        """
        Returns basic reagent dictionary.

        Args:
            extraction_kit (KitType, optional): KitType to use to get reagent type. Defaults to None.

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
        try:
            expiry = self.expiry.strftime("%Y-%m-%d")
        except:
            expiry = date.today()
        return {
            "name":self.name,
            "type": rtype,
            "lot": self.lot,
            "expiry": self.expiry.strftime("%Y-%m-%d")
        }
    
    def save(self):
        self.metadata.session.add(self)
        self.metadata.session.commit()

    @classmethod
    @setup_lookup
    def query(cls, reagent_type:str|ReagentType|None=None,
                        lot_number:str|None=None,
                        limit:int=0
                        ) -> Reagent|List[Reagent]:
        """
        Lookup a list of reagents from the database.

        Args:
            ctx (Settings): Settings object passed down from gui
            reagent_type (str | models.ReagentType | None, optional): Reagent type. Defaults to None.
            lot_number (str | None, optional): Reagent lot number. Defaults to None.
            limit (int, optional): limit of results returned. Defaults to 0.

        Returns:
            models.Reagent | List[models.Reagent]: reagent or list of reagents matching filter.
        """    
        query: Query = cls.metadata.session.query(cls)
        match reagent_type:
            case str():
                logger.debug(f"Looking up reagents by reagent type: {reagent_type}")
                query = query.join(cls.type, aliased=True).filter(ReagentType.name==reagent_type)
            case ReagentType():
                logger.debug(f"Looking up reagents by reagent type: {reagent_type}")
                query = query.filter(cls.type.contains(reagent_type))
            case _:
                pass
        match lot_number:
            case str():
                logger.debug(f"Looking up reagent by lot number: {lot_number}")
                query = query.filter(cls.lot==lot_number)
                # In this case limit number returned.
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)

    def update_last_used(self, kit:KitType):
        report = Report()
        logger.debug(f"Attempting update of reagent type at intersection of ({self}), ({kit})")
        rt = ReagentType.query(kit_type=kit, reagent=self, limit=1)
        if rt != None:
            logger.debug(f"got reagenttype {rt}")
            assoc = KitTypeReagentTypeAssociation.query(kit_type=kit, reagent_type=rt)
            if assoc != None:
                if assoc.last_used != self.lot:
                    logger.debug(f"Updating {assoc} last used to {self.lot}")
                    assoc.last_used = self.lot
                    result = assoc.save()
                    return(report.add_result(result))
        return report.add_result(Result(msg=f"Updating last used {rt} was not performed.", status="Information"))

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

    def __repr__(self) -> str:
        return f"<Discount({self.name})>"
    
    @classmethod
    @setup_lookup
    def query(cls,
                organization:Organization|str|int|None=None,
                kit_type:KitType|str|int|None=None,
                ) -> Discount|List[Discount]:
        """
        Lookup discount objects (union of kit and organization)

        Args:
            ctx (Settings): Settings object passed down from the gui.
            organization (models.Organization | str | int): Organization receiving discount.
            kit_type (models.KitType | str | int): Kit discount received on.

        Raises:
            ValueError: Invalid Organization
            ValueError: Invalid kit.

        Returns:
            models.Discount|List[models.Discount]: Discount(s) of interest.
        """    
        query: Query = cls.metadata.session.query(cls)
        match organization:
            case Organization():
                logger.debug(f"Looking up discount with organization: {organization}")
                query = query.filter(cls.client==Organization)
            case str():
                logger.debug(f"Looking up discount with organization: {organization}")
                query = query.join(Organization).filter(Organization.name==organization)
            case int():
                logger.debug(f"Looking up discount with organization id: {organization}")
                query = query.join(Organization).filter(Organization.id==organization)
            case _:
                # raise ValueError(f"Invalid value for organization: {organization}")
                pass
        match kit_type:
            case KitType():
                logger.debug(f"Looking up discount with kit type: {kit_type}")
                query = query.filter(cls.kit==kit_type)
            case str():
                logger.debug(f"Looking up discount with kit type: {kit_type}")
                query = query.join(KitType).filter(KitType.name==kit_type)
            case int():
                logger.debug(f"Looking up discount with kit type id: {organization}")
                query = query.join(KitType).filter(KitType.id==kit_type)
            case _:
                # raise ValueError(f"Invalid value for kit type: {kit_type}")
                pass
        return query.all()

class SubmissionType(Base):
    """
    Abstract of types of submissions.
    """    
    __tablename__ = "_submission_types"

    id = Column(INTEGER, primary_key=True) #: primary key
    name = Column(String(128), unique=True) #: name of submission type
    info_map = Column(JSON) #: Where basic information is found in the excel workbook corresponding to this type.
    instances = relationship("BasicSubmission", backref="submission_type")
    # regex = Column(String(512))
    
    submissiontype_kit_associations = relationship(
        "SubmissionTypeKitTypeAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan",
    )

    kit_types = association_proxy("submissiontype_kit_associations", "kit_type")

    def __repr__(self) -> str:
        return f"<SubmissionType({self.name})>"
    
    @classmethod
    @setup_lookup
    def query(cls, 
              name:str|None=None,
              key:str|None=None,
              limit:int=0
              ) -> SubmissionType|List[SubmissionType]:
        """
        Lookup submission type in the database by a number of parameters

        Args:
            ctx (Settings): Settings object passed down from gui
            name (str | None, optional): Name of submission type. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.SubmissionType|List[models.SubmissionType]: SubmissionType(s) of interest.
        """    
        query: Query = cls.metadata.session.query(cls)
        match name:
            case str():
                logger.debug(f"Looking up submission type by name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        match key:
            case str():
                query = query.filter(cls.info_map.op('->')(key)!=None)
            case _:
                pass
        return query_return(query=query, limit=limit)
    
    def save(self):
        self.metadata.session.add(self)
        self.metadata.session.commit()
        return None
  
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

    # reference to the "SubmissionType" object
    submission_type = relationship(SubmissionType, back_populates="submissiontype_kit_associations")

    def __init__(self, kit_type=None, submission_type=None):
        self.kit_type = kit_type
        self.submission_type = submission_type
        self.mutable_cost_column = 0.00
        self.mutable_cost_sample = 0.00
        self.constant_cost = 0.00

    def __repr__(self) -> str:
        return f"<SubmissionTypeKitTypeAssociation({self.submission_type.name})>"
    
    def set_attrib(self, name, value):
        self.__setattr__(name, value)

    @classmethod
    @setup_lookup
    def query(cls,
                submission_type:SubmissionType|str|int|None=None,
                kit_type:KitType|str|int|None=None,
                limit:int=0
            ):
        query: Query = cls.metadata.session.query(cls)
        match submission_type:
            case SubmissionType():
                logger.debug(f"Looking up {cls.__name__} by SubmissionType {submission_type}")
                query = query.filter(cls.submission_type==submission_type)
            case str():
                logger.debug(f"Looking up {cls.__name__} by name {submission_type}")
                query = query.join(SubmissionType).filter(SubmissionType.name==submission_type)
            case int():
                logger.debug(f"Looking up {cls.__name__} by id {submission_type}")
                query = query.join(SubmissionType).filter(SubmissionType.id==submission_type)
        match kit_type:
            case KitType():
                logger.debug(f"Looking up {cls.__name__} by KitType {kit_type}")
                query = query.filter(cls.kit_type==kit_type)
            case str():
                logger.debug(f"Looking up {cls.__name__} by name {kit_type}")
                query = query.join(KitType).filter(KitType.name==kit_type)
            case int():
                logger.debug(f"Looking up {cls.__name__} by id {kit_type}")
                query = query.join(KitType).filter(KitType.id==kit_type)
        limit = query.count()
        return query_return(query=query, limit=limit)

