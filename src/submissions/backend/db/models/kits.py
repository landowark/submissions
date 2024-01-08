'''
All kit and reagent related models
'''
from __future__ import annotations
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, BLOB
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date
import logging, re
from tools import check_authorization, setup_lookup, query_return, Report, Result, Settings
from typing import List
from pandas import ExcelFile
from pathlib import Path
from . import Base, BaseClass, Organization
from tools import Settings

logger = logging.getLogger(f'submissions.{__name__}')

reagenttypes_reagents = Table(
                                "_reagenttypes_reagents", 
                                Base.metadata, 
                                Column("reagent_id", INTEGER, ForeignKey("_reagents.id")), 
                                Column("reagenttype_id", INTEGER, ForeignKey("_reagent_types.id")),
                                extend_existing = True
                                )

equipmentroles_equipment = Table(
    "_equipmentroles_equipment",
    Base.metadata,
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_equipment_roles.id")),
    extend_existing=True
)

equipmentroles_processes = Table(
    "_equipmentroles_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_equipment_roles.id")),
    extend_existing=True
)

submissiontypes_processes = Table(
    "_submissiontypes_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_submission_types.id")),
    extend_existing=True
)

class KitType(BaseClass):
    """
    Base of kits used in submission processing
    """    
    __tablename__ = "_kits"
    # __table_args__ = {'extend_existing': True} 

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
    
    def get_reagents(self, required:bool=False, submission_type:str|SubmissionType|None=None) -> List[ReagentType]:
        """
        Return ReagentTypes linked to kit through KitTypeReagentTypeAssociation.

        Args:
            required (bool, optional): If true only return required types. Defaults to False.
            submission_type (str | None, optional): Submission type to narrow results. Defaults to None.

        Returns:
            list: List of reagent types
        """        
        match submission_type:
            case SubmissionType():
                relevant_associations = [item for item in self.kit_reagenttype_associations if item.submission_type==submission_type]
            case str():
                relevant_associations = [item for item in self.kit_reagenttype_associations if item.submission_type.name==submission_type]
            case _:
                relevant_associations = [item for item in self.kit_reagenttype_associations]
        if required:
            return [item.reagent_type for item in relevant_associations if item.required == 1]
        else:
            return [item.reagent_type for item in relevant_associations]
    
    def construct_xl_map_for_use(self, submission_type:str|SubmissionType) -> dict:
        """
        Creates map of locations in excel workbook for a SubmissionType

        Args:
            use (str): Submissiontype.name

        Returns:
            dict: Dictionary containing information locations.
        """        
        map = {}
        match submission_type:
            case str():
                assocs = [item for item in self.kit_reagenttype_associations if item.submission_type.name==submission_type]
                st_assoc = [item for item in self.used_for if submission_type == item.name][0]
            case SubmissionType():
                assocs = [item for item in self.kit_reagenttype_associations if item.submission_type==submission_type]
                st_assoc = submission_type
            case _:
                raise ValueError(f"Wrong variable type: {type(submission_type)} used!")
        # Get all KitTypeReagentTypeAssociation for SubmissionType
        # assocs = [item for item in self.kit_reagenttype_associations if item.submission_type==submission_type]
        for assoc in assocs:
            try:
                map[assoc.reagent_type.name] = assoc.uses
            except TypeError:
                continue
        # Get SubmissionType info map
        try:
            # st_assoc = [item for item in self.used_for if use == item.name][0]
            map['info'] = st_assoc.info_map
        except IndexError as e:
            map['info'] = {}
        return map

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
        name (str, optional): Name of desired kit (returns single instance). Defaults to None.
        used_for (str | models.Submissiontype | None, optional): Submission type the kit is used for. Defaults to None.
        id (int | None, optional): Kit id in the database. Defaults to None.
        limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
        models.KitType|List[models.KitType]: KitType(s) of interest.
        """    
        query: Query = cls.__database_session__.query(cls)
        match used_for:
            case str():
                # logger.debug(f"Looking up kit type by use: {used_for}")
                query = query.filter(cls.used_for.any(name=used_for))
            case SubmissionType():
                query = query.filter(cls.used_for.contains(used_for))
            case _:
                pass
        match name:
            case str():
                # logger.debug(f"Looking up kit type by name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        match id:
            case int():
                # logger.debug(f"Looking up kit type by id: {id}")
                query = query.filter(cls.id==id)
                limit = 1
            case str():
                # logger.debug(f"Looking up kit type by id: {id}")
                query = query.filter(cls.id==int(id))
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)
    
    @check_authorization
    def save(self, ctx:Settings):
        """
        Add this instance to database and commit
        """        
        self.__database_session__.add(self)
        self.__database_session__.commit()

class ReagentType(BaseClass):
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

    def __repr__(self):
        return f"<ReagentType({self.name})>"
    
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
            name (str | None, optional): Reagent type name. Defaults to None.
            kit_type (KitType | str | None, optional): Kit the type of interest belongs to. Defaults to None.
            reagent (Reagent | str | None, optional): Concrete instance of the type of interest. Defaults to None.
            limit (int, optional): maxmimum number of results to return (0 = all). Defaults to 0.

        Raises:
            ValueError: Raised if only kit_type or reagent, not both, given.

        Returns:
            ReagentType|List[ReagentType]: ReagentType or list of ReagentTypes matching filter.
        """        
        query: Query = cls.__database_session__.query(cls)
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
            # logger.debug(f"Looking up reagent type for {type(kit_type)} {kit_type} and {type(reagent)} {reagent}")
            # logger.debug(f"Kit reagent types: {kit_type.reagent_types}")
            result = list(set(kit_type.reagent_types).intersection(reagent.type))
            logger.debug(f"Result: {result}")
            try:
                return result[0]
            except IndexError:
                return None
        match name:
            case str():
                # logger.debug(f"Looking up reagent type by name: {name}")
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)
    
    def to_pydantic(self):
        from backend.validators.pydant import PydReagent
        return PydReagent(lot=None, type=self.name, name=self.name, expiry=date.today())

# class KitTypeReagentTypeAssociation(BaseClass):
#     """
#     table containing reagenttype/kittype associations
#     DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
#     """    
#     __tablename__ = "_reagenttypes_kittypes"

#     reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id"), primary_key=True) #: id of associated reagent type
#     kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True) #: id of associated reagent type
#     submission_type_id = (Column(INTEGER), ForeignKey("_submission_types.id"), primary_key=True)
#     uses = Column(JSON) #: map to location on excel sheets of different submission types
#     required = Column(INTEGER) #: whether the reagent type is required for the kit (Boolean 1 or 0)
#     last_used = Column(String(32)) #: last used lot number of this type of reagent

#     kit_type = relationship(KitType, back_populates="kit_reagenttype_associations") #: relationship to associated kit

#     # reference to the "ReagentType" object
#     reagent_type = relationship(ReagentType, back_populates="reagenttype_kit_associations") #: relationship to associated reagent type

#     submission_type = relationship(SubmissionType, back_populates="submissiontype_kit_rt_associations")

#     def __init__(self, kit_type=None, reagent_type=None, uses=None, required=1):
#         # logger.debug(f"Parameters: Kit={kit_type}, RT={reagent_type}, Uses={uses}, Required={required}")
#         self.kit_type = kit_type
#         self.reagent_type = reagent_type
#         self.uses = uses
#         self.required = required

#     def __repr__(self) -> str:
#         return f"<KitTypeReagentTypeAssociation({self.kit_type} & {self.reagent_type})>"

#     @validates('required')
#     def validate_age(self, key, value):
#         """
#         Ensures only 1 & 0 used in 'required'

#         Args:
#             key (str): name of attribute
#             value (_type_): value of attribute

#         Raises:
#             ValueError: Raised if bad value given

#         Returns:
#             _type_: value
#         """        
#         if not 0 <= value < 2:
#             raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
#         return value
    
#     @validates('reagenttype')
#     def validate_reagenttype(self, key, value):
#         """
#         Ensures reagenttype is an actual ReagentType

#         Args:
#             key (str)): name of attribute
#             value (_type_): value of attribute

#         Raises:
#             ValueError: raised if reagenttype is not a ReagentType

#         Returns:
#             _type_: ReagentType
#         """        
#         if not isinstance(value, ReagentType):
#             raise ValueError(f'{value} is not a reagenttype')
#         return value
    
#     @classmethod
#     @setup_lookup
#     def query(cls,
#                 kit_type:KitType|str|None=None,
#                 reagent_type:ReagentType|str|None=None,
#                 limit:int=0
#                 ) -> KitTypeReagentTypeAssociation|List[KitTypeReagentTypeAssociation]:
#         """
#         Lookup junction of ReagentType and KitType

#         Args:
#             kit_type (models.KitType | str | None): KitType of interest.
#             reagent_type (models.ReagentType | str | None): ReagentType of interest.
#             limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

#         Returns:
#             models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]: Junction of interest.
#         """    
#         query: Query = cls.__database_session__.query(cls)
#         match kit_type:
#             case KitType():
#                 query = query.filter(cls.kit_type==kit_type)
#             case str():
#                 query = query.join(KitType).filter(KitType.name==kit_type)
#             case _:
#                 pass
#         match reagent_type:
#             case ReagentType():
#                 query = query.filter(cls.reagent_type==reagent_type)
#             case str():
#                 query = query.join(ReagentType).filter(ReagentType.name==reagent_type)
#             case _:
#                 pass
#         if kit_type != None and reagent_type != None:
#             limit = 1
#         return query_return(query=query, limit=limit)

#     def save(self) -> Report:
#         """
#         Adds this instance to the database and commits.

#         Returns:
#             Report: Result of save action
#         """        
#         report = Report()
#         self.__database_session__.add(self)
#         self.__database_session__.commit()
#         return report

class Reagent(BaseClass):
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
    # submissions = relationship("BasicSubmission", back_populates="reagents", uselist=True) #: submissions this reagent is used in

    reagent_submission_associations = relationship(
        "SubmissionReagentAssociation",
        back_populates="reagent",
        cascade="all, delete-orphan",
    ) #: Relation to SubmissionSampleAssociation
    # association proxy of "user_keyword_associations" collection
    # to "keyword" attribute
    submissions = association_proxy("reagent_submission_associations", "submission") #: Association proxy to SubmissionSampleAssociation.samples


    def __repr__(self):
        if self.name != None:
            return f"<Reagent({self.name}-{self.lot})>"
        else:
            return f"<Reagent({self.type.name}-{self.lot})>"
                
    def to_sub_dict(self, extraction_kit:KitType=None) -> dict:
        """
        dictionary containing values necessary for gui

        Args:
            extraction_kit (KitType, optional): KitType to use to get reagent type. Defaults to None.

        Returns:
            dict: representation of the reagent's attributes
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
            rtype = reagent_role.name.replace("_", " ")
        except AttributeError:
            rtype = "Unknown"
        # Calculate expiry with EOL from ReagentType
        try:
            place_holder = self.expiry + reagent_role.eol_ext
        except (TypeError, AttributeError) as e:
            place_holder = date.today()
            logger.debug(f"We got a type error setting {self.lot} expiry: {e}. setting to today for testing")
        return dict(
            name=self.name,
            type=rtype,
            lot=self.lot,
            expiry=place_holder.strftime("%Y-%m-%d")
        )
    
    def update_last_used(self, kit:KitType) -> Report:
        """
        Updates last used reagent lot for ReagentType/KitType

        Args:
            kit (KitType): Kit this instance is used in.

        Returns:
            Report: Result of operation
        """        
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
                    report.add_result(result)
                    return report
        report.add_result(Result(msg=f"Updating last used {rt} was not performed.", status="Information"))
        return report
        
    @classmethod
    @setup_lookup
    def query(cls, 
                reagent_type:str|ReagentType|None=None,
                lot_number:str|None=None,
                limit:int=0
                ) -> Reagent|List[Reagent]:
        """
        Lookup a list of reagents from the database.

        Args:
            reagent_type (str | models.ReagentType | None, optional): Reagent type. Defaults to None.
            lot_number (str | None, optional): Reagent lot number. Defaults to None.
            limit (int, optional): limit of results returned. Defaults to 0.

        Returns:
            models.Reagent | List[models.Reagent]: reagent or list of reagents matching filter.
        """    
        # super().query(session)
        query: Query = cls.__database_session__.query(cls)
        match reagent_type:
            case str():
                # logger.debug(f"Looking up reagents by reagent type: {reagent_type}")
                query = query.join(cls.type).filter(ReagentType.name==reagent_type)
            case ReagentType():
                # logger.debug(f"Looking up reagents by reagent type: {reagent_type}")
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

    def save(self):
        """
        Add this instance to the database and commit
        """        
        self.__database_session__.add(self)
        self.__database_session__.commit()
    
class Discount(BaseClass):
    """
    Relationship table for client labs for certain kits.
    """
    __tablename__ = "_discounts"

    id = Column(INTEGER, primary_key=True) #: primary key
    kit = relationship("KitType") #: joined parent reagent type
    kit_id = Column(INTEGER, ForeignKey("_kits.id", ondelete='SET NULL', name="fk_kit_type_id")) #: id of joined kit
    client = relationship("Organization") #: joined client lab
    client_id = Column(INTEGER, ForeignKey("_organizations.id", ondelete='SET NULL', name="fk_org_id")) #: id of joined client
    name = Column(String(128)) #: Short description 
    amount = Column(FLOAT(2)) #: Dollar amount of discount

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
            organization (models.Organization | str | int): Organization receiving discount.
            kit_type (models.KitType | str | int): Kit discount received on.

        Raises:
            ValueError: Invalid Organization
            ValueError: Invalid kit.

        Returns:
            models.Discount|List[models.Discount]: Discount(s) of interest.
        """    
        query: Query = cls.__database_session__.query(cls)
        match organization:
            case Organization():
                # logger.debug(f"Looking up discount with organization: {organization}")
                query = query.filter(cls.client==Organization)
            case str():
                # logger.debug(f"Looking up discount with organization: {organization}")
                query = query.join(Organization).filter(Organization.name==organization)
            case int():
                # logger.debug(f"Looking up discount with organization id: {organization}")
                query = query.join(Organization).filter(Organization.id==organization)
            case _:
                # raise ValueError(f"Invalid value for organization: {organization}")
                pass
        match kit_type:
            case KitType():
                # logger.debug(f"Looking up discount with kit type: {kit_type}")
                query = query.filter(cls.kit==kit_type)
            case str():
                # logger.debug(f"Looking up discount with kit type: {kit_type}")
                query = query.join(KitType).filter(KitType.name==kit_type)
            case int():
                # logger.debug(f"Looking up discount with kit type id: {organization}")
                query = query.join(KitType).filter(KitType.id==kit_type)
            case _:
                # raise ValueError(f"Invalid value for kit type: {kit_type}")
                pass
        return query.all()
    
class SubmissionType(BaseClass):
    """
    Abstract of types of submissions.
    """    
    __tablename__ = "_submission_types"

    id = Column(INTEGER, primary_key=True) #: primary key
    name = Column(String(128), unique=True) #: name of submission type
    info_map = Column(JSON) #: Where basic information is found in the excel workbook corresponding to this type.
    instances = relationship("BasicSubmission", backref="submission_type") #: Concrete instances of this type.
    # regex = Column(String(512))
    template_file = Column(BLOB) #: Blank form for this type stored as binary.
    processes = relationship("Process", back_populates="submission_types", secondary=submissiontypes_processes)
    
    submissiontype_kit_associations = relationship(
        "SubmissionTypeKitTypeAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan",
    ) #: Association of kittypes

    kit_types = association_proxy("submissiontype_kit_associations", "kit_type") #: Proxy of kittype association

    submissiontype_equipmentrole_associations = relationship(
        "SubmissionTypeEquipmentRoleAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan"
    )

    equipment = association_proxy("submissiontype_equipmentrole_associations", "equipment_role")

    submissiontype_kit_rt_associations = relationship(
        "KitTypeReagentTypeAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SubmissionType({self.name})>"
    
    def get_template_file_sheets(self) -> List[str]:
        """
        Gets names of sheet in the stored blank form.

        Returns:
            List[str]: List of sheet names
        """                                
        return ExcelFile(self.template_file).sheet_names

    def set_template_file(self, ctx:Settings, filepath:Path|str):
        if isinstance(filepath, str):
            filepath = Path(filepath)
        with open (filepath, "rb") as f:
            data = f.read()
        self.template_file = data
        self.save(ctx=ctx)        

    def construct_equipment_map(self):
        output = []
        for item in self.submissiontype_equipmentrole_associations:
            map = item.uses
            map['role'] = item.equipment_role.name
            output.append(map)
        return output
        # return [item.uses for item in self.submissiontype_equipmentrole_associations]

    def get_equipment(self) -> List['PydEquipmentRole']:
        return [item.to_pydantic(submission_type=self) for item in self.equipment]
    
    def get_processes_for_role(self, equipment_role:str|EquipmentRole):
        match equipment_role:
            case str():
                relevant = [item.get_all_processes() for item in self.submissiontype_equipmentrole_associations if item.equipment_role.name==equipment_role]
            case EquipmentRole():
                relevant = [item.get_all_processes() for item in self.submissiontype_equipmentrole_associations if item.equipment_role==equipment_role]
            case _:
                raise TypeError(f"Type {type(equipment_role)} is not allowed")
        return list(set([item for items in relevant for item in items if item != None ]))

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
            key (str | None, optional): A key present in the info-map to lookup. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.SubmissionType|List[models.SubmissionType]: SubmissionType(s) of interest.
        """    
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                # logger.debug(f"Looking up submission type by name: {name}")
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
    
    @check_authorization
    def save(self, ctx:Settings):
        """
        Adds this instances to the database and commits.
        """        
        self.__database_session__.add(self)
        self.__database_session__.commit()
  
class SubmissionTypeKitTypeAssociation(BaseClass):
    """
    Abstract of relationship between kits and their submission type.
    """    
    __tablename__ = "_submissiontypes_kittypes"

    submission_types_id = Column(INTEGER, ForeignKey("_submission_types.id"), primary_key=True) #: id of joined submission type
    kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True) #: id of joined kit
    mutable_cost_column = Column(FLOAT(2)) #: dollar amount per 96 well plate that can change with number of columns (reagents, tips, etc)
    mutable_cost_sample = Column(FLOAT(2)) #: dollar amount that can change with number of samples (reagents, tips, etc)
    constant_cost = Column(FLOAT(2)) #: dollar amount per plate that will remain constant (plates, man hours, etc)

    kit_type = relationship(KitType, back_populates="kit_submissiontype_associations") #: joined kittype

    # reference to the "SubmissionType" object
    submission_type = relationship(SubmissionType, back_populates="submissiontype_kit_associations") #: joined submission type

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
            ) -> SubmissionTypeKitTypeAssociation|List[SubmissionTypeKitTypeAssociation]:
        """
        Lookup SubmissionTypeKitTypeAssociations of interest.

        Args:
            submission_type (SubmissionType | str | int | None, optional): Identifier of submission type. Defaults to None.
            kit_type (KitType | str | int | None, optional): Identifier of kit type. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            SubmissionTypeKitTypeAssociation|List[SubmissionTypeKitTypeAssociation]: SubmissionTypeKitTypeAssociation(s) of interest
        """        
        query: Query = cls.__database_session__.query(cls)
        match submission_type:
            case SubmissionType():
                # logger.debug(f"Looking up {cls.__name__} by SubmissionType {submission_type}")
                query = query.filter(cls.submission_type==submission_type)
            case str():
                # logger.debug(f"Looking up {cls.__name__} by name {submission_type}")
                query = query.join(SubmissionType).filter(SubmissionType.name==submission_type)
            case int():
                # logger.debug(f"Looking up {cls.__name__} by id {submission_type}")
                query = query.join(SubmissionType).filter(SubmissionType.id==submission_type)
        match kit_type:
            case KitType():
                # logger.debug(f"Looking up {cls.__name__} by KitType {kit_type}")
                query = query.filter(cls.kit_type==kit_type)
            case str():
                # logger.debug(f"Looking up {cls.__name__} by name {kit_type}")
                query = query.join(KitType).filter(KitType.name==kit_type)
            case int():
                # logger.debug(f"Looking up {cls.__name__} by id {kit_type}")
                query = query.join(KitType).filter(KitType.id==kit_type)
        limit = query.count()
        return query_return(query=query, limit=limit)

class KitTypeReagentTypeAssociation(BaseClass):
    """
    table containing reagenttype/kittype associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """    
    __tablename__ = "_reagenttypes_kittypes"

    reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id"), primary_key=True) #: id of associated reagent type
    kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True) #: id of associated reagent type
    submission_type_id = Column(INTEGER, ForeignKey("_submission_types.id"), primary_key=True)
    uses = Column(JSON) #: map to location on excel sheets of different submission types
    required = Column(INTEGER) #: whether the reagent type is required for the kit (Boolean 1 or 0)
    last_used = Column(String(32)) #: last used lot number of this type of reagent

    kit_type = relationship(KitType, back_populates="kit_reagenttype_associations") #: relationship to associated kit

    # reference to the "ReagentType" object
    reagent_type = relationship(ReagentType, back_populates="reagenttype_kit_associations") #: relationship to associated reagent type

    submission_type = relationship(SubmissionType, back_populates="submissiontype_kit_rt_associations")

    def __init__(self, kit_type=None, reagent_type=None, uses=None, required=1):
        # logger.debug(f"Parameters: Kit={kit_type}, RT={reagent_type}, Uses={uses}, Required={required}")
        self.kit_type = kit_type
        self.reagent_type = reagent_type
        self.uses = uses
        self.required = required

    def __repr__(self) -> str:
        return f"<KitTypeReagentTypeAssociation({self.kit_type} & {self.reagent_type})>"

    @validates('required')
    def validate_age(self, key, value):
        """
        Ensures only 1 & 0 used in 'required'

        Args:
            key (str): name of attribute
            value (_type_): value of attribute

        Raises:
            ValueError: Raised if bad value given

        Returns:
            _type_: value
        """        
        if not 0 <= value < 2:
            raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
        return value
    
    @validates('reagenttype')
    def validate_reagenttype(self, key, value):
        """
        Ensures reagenttype is an actual ReagentType

        Args:
            key (str)): name of attribute
            value (_type_): value of attribute

        Raises:
            ValueError: raised if reagenttype is not a ReagentType

        Returns:
            _type_: ReagentType
        """        
        if not isinstance(value, ReagentType):
            raise ValueError(f'{value} is not a reagenttype')
        return value
    
    @classmethod
    @setup_lookup
    def query(cls,
                kit_type:KitType|str|None=None,
                reagent_type:ReagentType|str|None=None,
                limit:int=0
                ) -> KitTypeReagentTypeAssociation|List[KitTypeReagentTypeAssociation]:
        """
        Lookup junction of ReagentType and KitType

        Args:
            kit_type (models.KitType | str | None): KitType of interest.
            reagent_type (models.ReagentType | str | None): ReagentType of interest.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]: Junction of interest.
        """    
        query: Query = cls.__database_session__.query(cls)
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
        """
        Adds this instance to the database and commits.

        Returns:
            Report: Result of save action
        """        
        report = Report()
        self.__database_session__.add(self)
        self.__database_session__.commit()
        return report


class SubmissionReagentAssociation(BaseClass):

    __tablename__ = "_reagents_submissions"

    reagent_id = Column(INTEGER, ForeignKey("_reagents.id"), primary_key=True) #: id of associated sample
    submission_id = Column(INTEGER, ForeignKey("_submissions.id"), primary_key=True)
    comments = Column(String(1024))

    submission = relationship("BasicSubmission", back_populates="submission_reagent_associations") #: associated submission

    reagent = relationship(Reagent, back_populates="reagent_submission_associations")

    def __repr__(self):
        return f"<{self.submission.rsl_plate_num}&{self.reagent.lot}>"

    def __init__(self, reagent=None, submission=None):
        self.reagent = reagent
        self.submission = submission
        self.comments = ""

    @classmethod
    @setup_lookup
    def query(cls, 
              submission:"BasicSubmission"|str|int|None=None, 
              reagent:Reagent|str|None=None,
              limit:int=0) -> SubmissionReagentAssociation|List[SubmissionReagentAssociation]:
        """
        Lookup SubmissionReagentAssociations of interest.

        Args:
            submission (BasicSubmission&quot; | str | int | None, optional): Identifier of joined submission. Defaults to None.
            reagent (Reagent | str | None, optional): Identifier of joined reagent. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            SubmissionReagentAssociation|List[SubmissionReagentAssociation]: SubmissionReagentAssociation(s) of interest
        """        
        from . import BasicSubmission
        query: Query = cls.__database_session__.query(cls)
        match reagent:
            case Reagent():
                query = query.filter(cls.reagent==reagent)
            case str():
                # logger.debug(f"Filtering query with reagent: {reagent}")
                reagent = Reagent.query(lot_number=reagent)
                query = query.filter(cls.reagent==reagent)
                # logger.debug([item.reagent.lot for item in query.all()])
                # query = query.join(Reagent).filter(Reagent.lot==reagent)
            case _:
                pass
        # logger.debug(f"Result of query after reagent: {query.all()}")
        match submission:
            case BasicSubmission():
                query = query.filter(cls.submission==submission)
            case str():
                query = query.join(BasicSubmission).filter(BasicSubmission.rsl_plate_num==submission)
            case int():
                query = query.join(BasicSubmission).filter(BasicSubmission.id==submission)
            case _:
                pass
        # logger.debug(f"Result of query after submission: {query.all()}")
        # limit = query.count()
        return query_return(query=query, limit=limit)

    def to_sub_dict(self, extraction_kit):
        output = self.reagent.to_sub_dict(extraction_kit)
        output['comments'] = self.comments
        return output

class Equipment(BaseClass):

    # Currently abstract until ready to implement
    # __abstract__ = True

    __tablename__ = "_equipment"

    id = Column(INTEGER, primary_key=True)
    name = Column(String(64))
    nickname = Column(String(64))
    asset_number = Column(String(16))
    roles = relationship("EquipmentRole", back_populates="instances", secondary=equipmentroles_equipment)

    equipment_submission_associations = relationship(
        "SubmissionEquipmentAssociation",
        back_populates="equipment",
        cascade="all, delete-orphan",
    )

    submissions = association_proxy("equipment_submission_associations", "submission")

    def __repr__(self):
        return f"<Equipment({self.name})>"
    
    def get_processes(self, submission_type:SubmissionType):
        processes = [assoc.process for assoc in self.equipment_submission_associations if assoc.submission.submission_type_name==submission_type.name]
        if len(processes) == 0:
            processes = ['']
        return processes

    @classmethod
    @setup_lookup
    def query(cls, 
              name:str|None=None,
              nickname:str|None=None,
              asset_number:str|None=None,
              limit:int=0
              ) -> Equipment|List[Equipment]:
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        match nickname:
            case str():
                query = query.filter(cls.nickname==nickname)
                limit = 1
            case _:
                pass
        match asset_number:
            case str():
                query = query.filter(cls.asset_number==asset_number)
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)
    
    def to_pydantic(self, submission_type:SubmissionType):
        from backend.validators.pydant import PydEquipment
        # return PydEquipment(process=self.get_processes(submission_type=submission_type), role=None, **self.__dict__)
        return PydEquipment(process=None, role=None, **self.__dict__)

    def save(self):
        self.__database_session__.add(self)
        self.__database_session__.commit()

    @classmethod
    def get_regex(cls) -> re.Pattern:
        return re.compile(r"""
                          (?P<PHAC>50\d{5}$)|
                          (?P<HC>HC-\d{6}$)|
                          (?P<Beckman>[^\d][A-Z0-9]{6}$)|
                          (?P<Axygen>[A-Z]{3}-\d{2}-[A-Z]-[A-Z]$)|
                          (?P<Labcon>\d{4}-\d{3}-\d{3}-\d$)""", 
                          re.VERBOSE)

class EquipmentRole(BaseClass):

    __tablename__ = "_equipment_roles"

    id = Column(INTEGER, primary_key=True)
    name = Column(String(32))
    instances = relationship("Equipment", back_populates="roles", secondary=equipmentroles_equipment)
    processes = relationship("Process", back_populates="equipment_roles", secondary=equipmentroles_processes)

    equipmentrole_submissiontype_associations = relationship(
        "SubmissionTypeEquipmentRoleAssociation",
        back_populates="equipment_role",
        cascade="all, delete-orphan",
    )

    submission_types = association_proxy("equipmentrole_submission_associations", "submission_type")

    def __repr__(self):
        return f"<EquipmentRole({self.name})>"

    def to_pydantic(self, submission_type:SubmissionType):
        from backend.validators.pydant import PydEquipmentRole
        equipment = [item.to_pydantic(submission_type=submission_type) for item in self.instances]
        pyd_dict = self.__dict__
        pyd_dict['processes'] = self.get_processes(submission_type=submission_type)
        return PydEquipmentRole(equipment=equipment, **pyd_dict)
    
    @classmethod
    @setup_lookup
    def query(cls, name:str|None=None, id:int|None=None, limit:int=0) -> EquipmentRole|List[EquipmentRole]:
        query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id==id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)
    
    def get_processes(self, submission_type:str|SubmissionType|None) -> List[Process]:
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if submission_type != None:                                                
            output = [process.name for process in self.processes if submission_type in process.submission_types]
        else:
            output = [process.name for process in self.processes]
        if len(output) == 0:
            return ['']
        else:
            return output
        
    def save(self):
        try:
            self.__database_session__.add(self)
            self.__database_session__.commit()
        except:
            self.__database_session__.rollback()

class SubmissionEquipmentAssociation(BaseClass):

    # Currently abstract until ready to implement
    # __abstract__ = True

    __tablename__ = "_equipment_submissions"

    equipment_id = Column(INTEGER, ForeignKey("_equipment.id"), primary_key=True) #: id of associated equipment
    submission_id = Column(INTEGER, ForeignKey("_submissions.id"), primary_key=True) #: id of associated submission
    role = Column(String(64), primary_key=True) #: name of the role the equipment fills
    # process = Column(String(64)) #: name of the process run on this equipment
    process_id = Column(INTEGER, ForeignKey("_process.id",ondelete="SET NULL", name="SEA_Process_id"))
    start_time = Column(TIMESTAMP)
    end_time = Column(TIMESTAMP)
    comments = Column(String(1024))
    
    submission = relationship("BasicSubmission", back_populates="submission_equipment_associations") #: associated submission

    equipment = relationship(Equipment, back_populates="equipment_submission_associations") #: associated submission

    def __init__(self, submission, equipment):
        self.submission = submission
        self.equipment = equipment

    def to_sub_dict(self) -> dict:
        output = dict(name=self.equipment.name, asset_number=self.equipment.asset_number, comment=self.comments, process=self.process.name, role=self.role, nickname=self.equipment.nickname)
        return output
    
    def save(self):
        self.__database_session__.add(self)
        self.__database_session__.commit()

class SubmissionTypeEquipmentRoleAssociation(BaseClass):

    # __abstract__ = True

    __tablename__ = "_submissiontype_equipmentrole"

    equipmentrole_id = Column(INTEGER, ForeignKey("_equipment_roles.id"), primary_key=True) #: id of associated equipment
    submissiontype_id = Column(INTEGER, ForeignKey("_submission_types.id"), primary_key=True) #: id of associated submission
    uses = Column(JSON) #: locations of equipment on the submission type excel sheet.
    static = Column(INTEGER, default=1) #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?

    submission_type = relationship(SubmissionType, back_populates="submissiontype_equipmentrole_associations") #: associated submission

    equipment_role = relationship(EquipmentRole, back_populates="equipmentrole_submissiontype_associations") #: associated equipment

    @validates('static')
    def validate_age(self, key, value):
        """
        Ensures only 1 & 0 used in 'static'

        Args:
            key (str): name of attribute
            value (_type_): value of attribute

        Raises:
            ValueError: Raised if bad value given

        Returns:
            _type_: value
        """        
        if not 0 <= value < 2:
            raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
        return value
    
    def get_all_processes(self):
        processes = [equipment.get_processes(self.submission_type) for equipment in self.equipment_role.instances]
        processes = [item for items in processes for item in items if item != None ]
        return processes

    @check_authorization
    def save(self, ctx:Settings):
        self.__database_session__.add(self)
        self.__database_session__.commit()

class Process(BaseClass):

    __tablename__ = "_process"

    id = Column(INTEGER, primary_key=True)
    name = Column(String(64))
    submission_types = relationship("SubmissionType", back_populates='processes', secondary=submissiontypes_processes)
    equipment_roles = relationship("EquipmentRole", back_populates='processes', secondary=equipmentroles_processes)
    submissions = relationship("SubmissionEquipmentAssociation", backref='process')

    def __repr__(self):
        return f"<Process({self.name})"
    
    @classmethod
    @setup_lookup
    def query(cls, name:str|None, limit:int=0):
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name==name)
                limit = 1
            case _:
                pass
        return query_return(query=query, limit=limit)

    def save(self):
        try:
            self.__database_session__.add(self)
            self.__database_session__.commit()
        except:
            self.__database_session__.rollback()

# class KitTypeReagentTypeAssociation(BaseClass):
#     """
#     table containing reagenttype/kittype associations
#     DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
#     """    
#     __tablename__ = "_reagenttypes_kittypes"

#     reagent_types_id = Column(INTEGER, ForeignKey("_reagent_types.id"), primary_key=True) #: id of associated reagent type
#     kits_id = Column(INTEGER, ForeignKey("_kits.id"), primary_key=True) #: id of associated reagent type
#     uses = Column(JSON) #: map to location on excel sheets of different submission types
#     required = Column(INTEGER) #: whether the reagent type is required for the kit (Boolean 1 or 0)
#     last_used = Column(String(32)) #: last used lot number of this type of reagent

#     kit_type = relationship(KitType, back_populates="kit_reagenttype_associations") #: relationship to associated kit

#     # reference to the "ReagentType" object
#     reagent_type = relationship(ReagentType, back_populates="reagenttype_kit_associations") #: relationship to associated reagent type

#     def __init__(self, kit_type=None, reagent_type=None, uses=None, required=1):
#         # logger.debug(f"Parameters: Kit={kit_type}, RT={reagent_type}, Uses={uses}, Required={required}")
#         self.kit_type = kit_type
#         self.reagent_type = reagent_type
#         self.uses = uses
#         self.required = required

#     def __repr__(self) -> str:
#         return f"<KitTypeReagentTypeAssociation({self.kit_type} & {self.reagent_type})>"

#     @validates('required')
#     def validate_age(self, key, value):
#         """
#         Ensures only 1 & 0 used in 'required'

#         Args:
#             key (str): name of attribute
#             value (_type_): value of attribute

#         Raises:
#             ValueError: Raised if bad value given

#         Returns:
#             _type_: value
#         """        
#         if not 0 <= value < 2:
#             raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
#         return value
    
#     @validates('reagenttype')
#     def validate_reagenttype(self, key, value):
#         """
#         Ensures reagenttype is an actual ReagentType

#         Args:
#             key (str)): name of attribute
#             value (_type_): value of attribute

#         Raises:
#             ValueError: raised if reagenttype is not a ReagentType

#         Returns:
#             _type_: ReagentType
#         """        
#         if not isinstance(value, ReagentType):
#             raise ValueError(f'{value} is not a reagenttype')
#         return value
    
#     @classmethod
#     @setup_lookup
#     def query(cls,
#                 kit_type:KitType|str|None=None,
#                 reagent_type:ReagentType|str|None=None,
#                 limit:int=0
#                 ) -> KitTypeReagentTypeAssociation|List[KitTypeReagentTypeAssociation]:
#         """
#         Lookup junction of ReagentType and KitType

#         Args:
#             kit_type (models.KitType | str | None): KitType of interest.
#             reagent_type (models.ReagentType | str | None): ReagentType of interest.
#             limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

#         Returns:
#             models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]: Junction of interest.
#         """    
#         query: Query = cls.__database_session__.query(cls)
#         match kit_type:
#             case KitType():
#                 query = query.filter(cls.kit_type==kit_type)
#             case str():
#                 query = query.join(KitType).filter(KitType.name==kit_type)
#             case _:
#                 pass
#         match reagent_type:
#             case ReagentType():
#                 query = query.filter(cls.reagent_type==reagent_type)
#             case str():
#                 query = query.join(ReagentType).filter(ReagentType.name==reagent_type)
#             case _:
#                 pass
#         if kit_type != None and reagent_type != None:
#             limit = 1
#         return query_return(query=query, limit=limit)

#     def save(self) -> Report:
#         """
#         Adds this instance to the database and commits.

#         Returns:
#             Report: Result of save action
#         """        
#         report = Report()
#         self.__database_session__.add(self)
#         self.__database_session__.commit()
#         return report
