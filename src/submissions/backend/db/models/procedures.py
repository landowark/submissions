"""
All reagent, procedure, equipment, and process models.

This module defines the SQLAlchemy models used for procedure management, reagent tracking, equipment assignment,
process versions, tips, and related associations. It includes rich association tables and custom property handling
for flexible input types.
"""
from __future__ import annotations
from pprint import pformat
from jinja2 import Template
import zipfile, logging, re, numpy as np, json
from pydantic import BaseModel
from sqlalchemy import Column, ForeignKeyConstraint, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, and_, cast, func, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, Query
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date, datetime, timedelta
from dateutil.parser import parse as dateparse, ParserError
from frontend.widgets.submission_details import SubmissionComment
from tools import check_authorization, setup_lookup, flatten_list, timezone
from typing import Iterator, List, Any, Tuple, TYPE_CHECKING
from . import BaseClass, ClientLab, LogMixin
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
if TYPE_CHECKING:
    from backend.db.models.submissions import Run
    from backend.validators.pydant import PydProcedure, PydProcedureEquipmentAssociation

logger = logging.getLogger(f'submissions.{__name__}')


proceduretype_resulttype = Table(
    "_proceduretype_resulttype",
    BaseClass.__base__.metadata,
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    Column("resultstype_id", INTEGER, ForeignKey("_resultstype.id")),
    extend_existing=True
)

# Define the association table instance first
equipmentroleequipmentassociation_process = Table(
    "_equipmentrolequipmentassociation_process",
    BaseClass.metadata,
    # Define the columns that will link the two parent tables
    Column("equipmentrole_id", INTEGER),
    Column("equipment_id", INTEGER),
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    
    # Define the composite Primary Key for the association table itself
    # This prevents duplicate associations
    # Use the column names defined just above
    
    # Define the composite foreign key constraint referring to the parent table
    ForeignKeyConstraint(
        ["equipmentrole_id", "equipment_id"],
        ["_equipmentroleequipmentassociation.equipmentrole_id", 
         "_equipmentroleequipmentassociation.equipment_id"]
    ),
    # Combine all columns into the association table's PRIMARY KEY
    # This ensures a given role+equipment+process combination is unique
    Column("pk_constraint", INTEGER, primary_key=True) # SQLite often needs an implicit PK 
)

process_tips = Table(
    "_process_tips",
    BaseClass.__base__.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)

submissiontype_proceduretype = Table(
    "_submissiontype_proceduretype",
    BaseClass.__base__.metadata,
    Column("submissiontype_id", INTEGER, ForeignKey("_submissiontype.id")),
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    extend_existing=True
)


class ReagentRole(BaseClass):
    """
    Represents the relationship between reagents and the roles they play in a procedure.

    :ivar id: Primary key identifier for the reagent role
    :vartype id: int
    :ivar name: Unique role name
    :vartype name: str
    :ivar reagentroleproceduretypeassociation: Associations to procedure types
    :vartype reagentroleproceduretypeassociation: list[ProcedureTypeReagentRoleAssociation]
    :ivar _proceduretype: Association proxy to related procedure types
    :vartype _proceduretype: list[ProcedureType]
    :ivar reagentrolereagentassociation: Associations to reagents
    :vartype reagentrolereagentassociation: list[ReagentRoleReagentAssociation]
    :ivar _reagent: Association proxy to related reagents
    :vartype _reagent: list[Reagent]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), nullable=False, unique=True)  #: name of reagentrole reagent plays
    
    reagentroleproceduretypeassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation

    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    _proceduretype = association_proxy("reagentroleproceduretypeassociation", "_proceduretype",
                                       creator=lambda proceduretype: ProcedureTypeReagentRoleAssociation(proceduretype=proceduretype))  #: Association proxy to 

    reagentrolereagentassociation = relationship(
        "ReagentRoleReagentAssociation",
        back_populates="_reagentrole",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation

    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    _reagent = association_proxy("reagentrolereagentassociation", "_reagent",
                                 creator=lambda reagent: ReagentRoleReagentAssociation(reagent=reagent))  #: Association proxy to 

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        reagent = kwargs.pop('reagent', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if reagent is not None:
            try:
                self.reagent = reagent
            except Exception:
                logger.error(f"Couldn't set reagent to {reagent} for {self.__class__.__qualname__} with name {self.name}")
        
    @hybrid_property
    def proceduretype(self) -> List[ProcedureType]:
        return self._proceduretype
    
    @proceduretype.setter
    def proceduretype(self, value):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.reagentroleproceduretypeassociation if assoc.proceduretype.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.proceduretype.name for eq in self.reagentroleproceduretypeassociation]}")
                        output = ProcedureTypeReagentRoleAssociation(proceduretype=item, reagentrole=self)
                case dict():
                    output = ProcedureTypeReagentRoleAssociation(proceduretype=item, reagentrole=self, **{k: v for k, v in item.items() if k not in ['proceduretype']})
                case ProcedureType():
                    output = ProcedureTypeReagentRoleAssociation(proceduretype=item, reagentrole=self)
                case ProcedureTypeReagentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._proceduretype")
                    continue
            if isinstance(output, ProcedureTypeReagentRoleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {item} to {self.__class__.__qualname__}._proceduretype")
        self.reagentroleproceduretypeassociation = list_

    @hybrid_property
    def reagent(self) -> List[Reagent]:
        return self._reagent
    
    @reagent.setter
    def reagent(self, value):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.reagentrolereagentassociation if assoc.reagent.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.reagent.name for eq in self.reagentrolereagentassociation]}")
                        output = ReagentRoleReagentAssociation(reagent=item, reagentrole=self)
                case dict():
                    output = ReagentRoleReagentAssociation(reagent=item, reagentrole=self, **{k: v for k, v in item.items() if k not in ['reagent', "reagentrole"]})
                case ReagentRoleReagentAssociation():
                    output = item
                case Reagent():
                    output = ReagentRoleReagentAssociation(reagent=item, reagentrole=self)
                case _:
                    logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._reagent")
                    continue
            if isinstance(output, ReagentRoleReagentAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._reagent")
        self.reagentrolereagentassociation = list_

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              proceduretype: ProcedureType | str | None = None,
              reagent: Reagent | str | None = None,
              id: int | None = None,
              limit: int = 0,
              **kwargs
              ) -> ReagentRole | List[ReagentRole]:
        """
        Lookup reagent types in the database.

        :param id: Id of the object. Defaults to None.
        :type id: int | None
        :param name: Reagent type name. Defaults to None.
        :type name: str | None
        :param proceduretype: Procedure the type of interest belongs to. Defaults to None.
        :type proceduretype: ProcedureType | str | None
        :param reagent: Concrete instance of the type of interest. Defaults to None.
        :type reagent: Reagent | str | None
        :param limit: maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int

        :raises ValueError: Raised if only proceduretype or reagent is provided incorrectly.
        :return: ReagentRole or list of ReagentRoles matching filter.
        :rtype: ReagentRole | List[ReagentRole]
        """
        query: Query = cls.__database_session__.query(cls)
        match proceduretype:
            case str():
                proceduretype = ProcedureType.query(name=proceduretype)
                query = query.filter(cls._proceduretype==proceduretype)
            case ProcedureType():
                query = query.filter(cls._proceduretype==proceduretype)
            case _:
                pass
        match reagent:
            case str():
                reagent = Reagent.query(lot=reagent)
                query = query.filter(cls._reagent==reagent)
            case Reagent():
                query = query.filter(cls._reagent==reagent)
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        """
        super().save()

    def get_reagents(self, proceduretype: str | ProcedureType | None = None):
        """
        Return reagent details for this role, optionally prioritising a specific procedure type.

        :param proceduretype: Procedure type to prioritise. Defaults to None.
        :type proceduretype: str | ProcedureType | None
        :return: List of reagent pydantic objects for this role.
        :rtype: list
        """
        if not proceduretype:
            return [reagent.to_pydantic() for reagent in self.reagent]
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        assoc = next((item for item in self.reagentroleproceduretypeassociation if item.proceduretype == proceduretype), None)
        reagents = [reagent for reagent in self.reagent]
        if assoc:
            last_used = assoc.last_used
            if last_used:
                reagents.insert(0, reagents.pop(reagents.index(last_used)))
        return [reagent.to_pydantic() for reagent in reagents]

    
class Reagent(BaseClass, LogMixin):
    """
    Represents a concrete reagent inventory item.

    :ivar id: Primary key identifier for the reagent
    :vartype id: int
    :ivar _eol_ext: Extended life interval for expiry
    :vartype _eol_ext: Interval|timedelta
    :ivar name: Unique reagent name
    :vartype name: str
    :ivar manufacturer: Manufacturer of the reagent
    :vartype manufacturer: str
    :ivar ref: Vendor reference code
    :vartype ref: str
    :ivar cost_per_ml: Cost in currency per millilitre
    :vartype cost_per_ml: float
    :ivar _reagentlot: Related reagent lots
    :vartype _reagentlot: list[ReagentLot]
    :ivar reagentreagentroleassociation: Reagent-role associations
    :vartype reagentreagentroleassociation: list[ReagentRoleReagentAssociation]
    :ivar _reagentrole: Association proxy to reagent roles
    :vartype _reagentrole: list[ReagentRole]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    _eol_ext = Column(Interval())  #: extension of life interval
    name = Column(String(64), nullable=False, unique=True)  #: reagent name
    manufacturer = Column(String(32))
    ref = Column(String(16))
    cost_per_ml = Column(FLOAT(2))  #: amount a millilitre of reagent costs

    _reagentlot = relationship("ReagentLot", back_populates="_reagent", cascade="all, delete-orphan")  #: joined parent reagent type

    reagentreagentroleassociation = relationship(
        "ReagentRoleReagentAssociation",
        back_populates="_reagent",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    
    _reagentrole = association_proxy("reagentreagentroleassociation", "_reagentrole",
                                     creator=lambda reagentrole: ReagentRoleReagentAssociation(reagentrole=reagentrole))  #: Association proxy to KitTypeReagentTypeAssociation

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        reagentrole = kwargs.pop('reagentrole', None)
        reagentlot = kwargs.pop('reagentlot', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'reagentrole': reagentrole})
                except Exception:
                    pass
        # Resolve reagentrole
        if reagentlot is not None:
            try:
                self.reagentlot = reagentlot
            except Exception:
                try:
                    self._misc_info.update({'reagentlot': reagentlot})
                except Exception:
                    pass

    @hybrid_property
    def reagentrole(self):
        return self._reagentrole
    
    @reagentrole.setter
    def reagentrole(self, value):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.reagentreagentroleassociation if assoc.reagentrole.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.reagentrole.name for eq in self.reagentreagentroleassociation]}")
                        output = ReagentRoleReagentAssociation(reagentrole=item, reagent=self)
                case dict():
                    output = ReagentRoleReagentAssociation(reagentrole=item, reagent=self, **{k: v for k, v in item.items() if k not in ['reagentrole', 'reagent']})
                case ReagentRoleReagentAssociation():
                    output = item
                case ReagentRole():
                    output = ReagentRoleReagentAssociation(reagentrole=item, reagent=self)
                case _:
                    logger.error(f"Unmatched value {item} for {self}._reagentrole")
                    continue
            if isinstance(output, ReagentRoleReagentAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._reagentrole")
        self.reagentreagentroleassociation = list_

    @hybrid_property
    def eol_ext(self):
        return self._eol_ext

    @eol_ext.setter
    def eol_ext(self, value):
        if isinstance(value, int):
            value = timedelta(days=value)
        elif isinstance(value, timedelta):
            pass
        else:
            raise TypeError(f"Unsupported variable type {type(value)} for eol_ext: {value} must be an integer for number of days.")
        self._eol_ext = value
    
    @hybrid_property
    def reagentlot(self):
        return self._reagentlot
    
    @reagentlot.setter
    def reagentlot(self, value):
        from backend.validators.pydant import PydReagentLot
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    # If the string contains " - ", assume it's a name and not a lot number. 
                    # This is admittedly a bit hacky, but it allows for more flexible input while still supporting simple lot number queries.
                    if " - " in item:
                        output = ReagentLot.query(name=item, limit=1)
                    else:
                        output = ReagentLot.query(lot=item, limit=1)
                case dict():
                    output = ReagentLot.query_or_create(**item)
                case PydReagentLot():
                    output = item.to_sql(update=False)
                case ReagentLot():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for _reagentlot")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ReagentLot):
                list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._reagentlot")
        self._reagentlot = list_

    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              reagentrole: str | ReagentRole | None = None,
              lot: str | None = None,
              name: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> Reagent | List[Reagent]:
        """
        Lookup a list of reagents from the database.

        :param id: reagent id number
        :type id: int | None, optional
        :param reagentrole: Reagent type. Defaults to None.
        :type reagentrole: str | models.ReagentType | None, optional
        :param lot: Reagent lot number. Defaults to None.
        :type lot: str | None, optional
        :param name: Reagent name. Defaults to None.
        :type name: str | None, optional
        :param limit: limit of results returned. Defaults to 0.
        :type limit: int, optional 
        :return: models.Reagent | List[models.Reagent]: reagent or list of reagents matching filter.
        """        
        query: Query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match reagentrole:
            case str():
                query = query.join(cls._reagentrole).filter(ReagentRole.name == reagentrole)
            case ReagentRole():
                query = query.filter(cls._reagentrole.contains(reagentrole))
            case _:
                pass
        match name:
            case str():
                # NOTE: Not limited due to multiple reagents having same name.
                query = query.filter(cls.name == name)
            case _:
                pass
        match lot:
            case str():
                query = query.filter(cls.lot == lot)
                # NOTE: In this case limit number returned.
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)

    
class ReagentLot(BaseClass):
    """
    Tracks a specific reagent lot and its expiry information.

    :ivar id: Primary key for reagent lot
    :vartype id: int
    :ivar lot: Unique lot number
    :vartype lot: str
    :ivar _expiry: Expiry timestamp for this lot
    :vartype _expiry: datetime|None
    :ivar _active: Active status flag stored as integer
    :vartype _active: int
    :ivar reagent_id: Foreign key to the parent reagent
    :vartype reagent_id: int
    :ivar _reagent: Related parent reagent
    :vartype _reagent: Reagent
    :ivar reagentlotprocedureassociation: Procedure associations for this reagent lot
    :vartype reagentlotprocedureassociation: list[ProcedureReagentLotAssociation]
    :ivar _procedure: Association proxy to Procedure objects
    :vartype _procedure: list[Procedure]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    lot = Column(String(64), nullable=False)  #: lot number of reagent
    _expiry = Column(TIMESTAMP)  #: expiry date - extended by eol_ext of parent programmatically
    _active = Column(INTEGER, default=1)
    reagent_id = Column(INTEGER, ForeignKey("_reagent.id", ondelete='SET NULL',
                                            name="fk_REGLOT_reagent_id"))  #: id of parent reagent type
    _reagent = relationship("Reagent", back_populates="_reagentlot")  #: joined parent reagent type

    reagentlotprocedureassociation = relationship(
        "ProcedureReagentLotAssociation",
        back_populates="_reagentlot",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    _procedure = association_proxy("reagentlotprocedureassociation", "procedure",
                                   creator=lambda procedure: ProcedureReagentLotAssociation(procedure=procedure))  #: Association proxy to ClientSubmissionSampleAssociation

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        reagent = kwargs.pop('reagent', None)
        procedure = kwargs.pop('procedure', None)
        expiry = kwargs.pop('expiry', None)
        active = kwargs.pop('active', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve reagent
        if reagent is not None:
            try:
                self.reagent = reagent
            except Exception:
                logger.error(f"Couldn't set reagent to {reagent} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        else:
            self._procedure = []
        if expiry is not None:
            try:
                self.expiry = expiry
            except Exception:
                logger.error(f"Couldn't set expiry to {expiry} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if active is not None:
            try:
                self.active = active
            except Exception:
                logger.error(f"Couldn't set active to {active} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def procedure(self) -> List[Procedure]:
        return self._procedure
    
    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.reagentlotprocedureassociation if assoc.procedure.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.procedure.name for eq in self.reagentlotprocedureassociation]}")
                        output = ProcedureReagentLotAssociation(procedure=item, reagentlot=self)
                case Procedure():
                    output = ProcedureReagentLotAssociation(procedure=item, reagentlot=self)
                case PydProcedure():
                    output = ProcedureReagentLotAssociation(procedure=item, reagentlot=self, **{k: v for k, v in item.improved_dict.items() if k != 'name'})
                case dict():
                    output = ProcedureReagentLotAssociation(procedure=item, reagentlot=self, **{k: v for k, v in item.items() if k not in ['procedure', 'reagentlot']})
                case ProcedureReagentLotAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}.procedure")
                    continue
            if isinstance(output, ProcedureReagentLotAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._procedure")
        self.procedurereagentlotassociation = list_

    @hybrid_property
    def expiry(self) -> datetime:
        return self._expiry if self._expiry else datetime(year=2099, month=12, day=31, hour=23, minute=59, second=59, tzinfo=timezone)

    @expiry.setter
    def expiry(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime() | date():
                output = value
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}.expiry")
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}.expiry")
        output = datetime.combine(output, datetime.max.time())
        value = output.replace(tzinfo=timezone)
        self._expiry = value
    
    @hybrid_property
    def reagent(self):
        return self._reagent
        
    @reagent.setter
    def reagent(self, value):
        from backend.validators.pydant import PydReagent
        match value:
            case str():
                output = Reagent.query(name=value, limit=1)
            case dict():
                output = Reagent.query_or_create(**value)
            case PydReagent():
                output = value.to_sql(update=False)
            case Reagent():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}.reagent")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Reagent):
            self._reagent = output
        else:
            logger.error(f"Could set {self.__class__.__qualname__}._reagent to {value}.")
        
    @hybrid_property
    def active(self):
        return bool(self._active)

    @active.setter
    def active(self, value):
        match value:
            case int():
                output = value
            case bool():
                output = int(value)
            case str():
                if value.lower() in ["false", "0", "no", "off"]:
                    output = 0
                elif value.lower() in ["true", "1", "yes", "on"]:
                    output = 1
                else:
                    raise ValueError(f"Cannot convert string {value} to boolean for {self.lot}.active")
            case _:
                raise TypeError(f"Unsupported type: {type(value)} for {self.lot}.active")
        self._active = output
    
    @hybrid_property
    def name(self):
        try:
            reagent = self.reagent.name
        except AttributeError:
            reagent = "Unassigned Reagent"
        return f"{reagent} - {self.lot}"

    @name.expression
    def name(cls):
        regeant_subquery = (
            select(Reagent.name)
            .where(Reagent.id==cls.reagent_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return regeant_subquery + " - " + cls.lot

    @classmethod
    def query(cls,
              lot: str | None = None,
              name: str | None = None,
              reagent: str | Reagent | None = None,
              limit: int = 0,
              **kwargs) -> ReagentLot | List[ReagentLot]:
        """
        Lookup reagent lots by lot number, reagent name, or display name.

        :param lot: Lot number of this reagent instance. Defaults to None.
        :type lot: str | None
        :param name: Display name of this reagent lot. Defaults to None.
        :type name: str | None
        :param reagent: Parent reagent or reagent name. Defaults to None.
        :type reagent: Reagent | str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: ReagentLot or list of ReagentLots matching filter.
        :rtype: ReagentLot | List[ReagentLot]
        """
        query: Query = cls.__database_session__.query(cls)
        match lot:
            case str():
                query = query.filter(cls.lot == lot)
                limit = 1
            case _:
                pass
        match reagent:
            case str():
                query = query.join(Reagent).filter(Reagent.name==reagent)
            case Reagent():
                query = query.filter(cls._reagent==reagent)
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @property
    def details_dict(self) -> dict:
        output = super().details_dict
        for key in ("reagentlotprocedureassociation", "procedure", "procedures"):
            output.pop(key, None)
        # output['excluded'] += ["reagentlotprocedureassociation", "procedures"]
        output['reagent'] = output['reagent']
        return output


class Discount(BaseClass):
    """
    Represents a discount applied to a procedure type for a client lab.

    :ivar id: Primary key identifier for the discount
    :vartype id: int
    :ivar _proceduretype: Related procedure type
    :vartype _proceduretype: ProcedureType
    :ivar proceduretype_id: Foreign key to procedure type
    :vartype proceduretype_id: int
    :ivar _clientlab: Related client lab
    :vartype _clientlab: ClientLab
    :ivar clientlab_id: Foreign key to client lab
    :vartype clientlab_id: int
    :ivar description: Discount description
    :vartype description: str
    :ivar amount: Discount amount
    :vartype amount: float
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    _proceduretype = relationship("ProcedureType")  #: joined parent proceduretype
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete='SET NULL',
                                                  name="fk_DIS_procedure_type_id"))  #: id of joined proceduretype
    _clientlab = relationship("ClientLab")  #: joined client lab
    clientlab_id = Column(INTEGER, ForeignKey("_clientlab.id", ondelete='SET NULL',
                                     name="fk_DIS_org_id"))  #: id of joined client
    description = Column(String(128))  #: Short description
    amount = Column(FLOAT(2))  #: Dollar amount of discount

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        clientlab = kwargs.pop('clientlab', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with description {self.description}")
                
        # Resolve reagentrole
        if clientlab is not None:
            try:
                self.clientlab = clientlab
            except Exception:
                logger.error(f"Couldn't set clientlab to {clientlab} for {self.__class__.__qualname__} with description {self.description}")

    @hybrid_property
    def name(self):
        try:
            clientlab = self.clientlab.name
        except AttributeError:
            clientlab = "Unassigned ClientLab"
        try:
            proceduretype = self.proceduretype.name
        except AttributeError:
            proceduretype = "Unassigned ProcedureType"
        return f"{clientlab}-{proceduretype}-{str(self.amount)}"
    
    @name.expression
    def name(cls):
        clientlab_subquery = (
            select(ClientLab.name)
            .where(ClientLab.id==cls.clientlab_id)
            .correlate(cls)
            .scalar_subquery()
        )
        proceduretype_subquery = (
            select(ProcedureType.name)
            .where(ProcedureType.id==cls.proceduretype_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return clientlab_subquery + "-" + proceduretype_subquery + "-" + cast(cls.amount, String)

    @hybrid_property
    def clientlab(self) -> ClientLab:
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value):
        from backend.validators.pydant import PydClientLab
        match value:
            case str():
                output = ClientLab.query(name=value, limit=1)
            case dict():
                output = ClientLab.query_or_create(**value)
            case PydClientLab():
                output = value.to_sql(update=False)
            case ClientLab():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .clientlab")
                # continue
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ClientLab):
            self._clientlab = output
        else:
            logger.error(f"Couldn't set _clientlab to {type(output)}")
    
    @hybrid_property
    def proceduretype(self) -> ProcedureType:
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        match value:
            case str():
                output = ProcedureType.query(name=value, limit=1)
            case dict():
                output = ProcedureType.query_or_create(**value)
            case PydProcedureType():
                output = value.to_sql(update=False)
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .proceduretype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Couldn't set _proceduretype to {type(output)}")

    @classmethod
    @setup_lookup
    def query(cls,
              clientlab: ClientLab | str | int | None = None,
              proceduretype: ProcedureType | str | int | None = None,
              ) -> Discount | List[Discount]:
        """
        Lookup discount objects by client lab and procedure type.

        :param clientlab: ClientLab receiving discount.
        :type clientlab: ClientLab | str | int | None
        :param proceduretype: Procedure type receiving discount.
        :type proceduretype: ProcedureType | str | int | None
        :return: Discount or list of Discounts matching criteria.
        :rtype: Discount | List[Discount]
        """
        query: Query = cls.__database_session__.query(cls)
        match clientlab:
            case ClientLab():
                query = query.filter(cls._clientlab == clientlab)
            case str():
                query = query.join(ClientLab).filter(ClientLab.name == clientlab)
            case int():
                query = query.join(ClientLab).filter(ClientLab.id == clientlab)
            case _:
                pass
        match proceduretype:
            case ProcedureType():
                query = query.filter(cls._proceduretype == proceduretype)
            case str():
                query = query.join(ProcedureType).filter(ProcedureType.name == proceduretype)
            case int():
                query = query.join(ProcedureType).filter(ProcedureType.id == proceduretype)
            case _:
                pass
        return cls.execute_query(query=query)

    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        """
        super().save()


class SubmissionType(BaseClass):
    """
    Represents a submission type and its default metadata.

    :ivar id: Primary key identifier for the submission type
    :vartype id: int
    :ivar name: Unique submission type name
    :vartype name: str
    :ivar defaults: Default JSON metadata for this type
    :vartype defaults: dict
    :ivar _file_name_template: Jinja2 filename template
    :vartype _file_name_template: str
    :ivar regex: Regex used to identify filenames of this submission type
    :vartype regex: str
    :ivar _turnaround_time: Turnaround interval for this type
    :vartype _turnaround_time: Interval|timedelta
    :ivar _abbreviation: Short abbreviation
    :vartype _abbreviation: str
    :ivar _clientsubmission: Related client submissions
    :vartype _clientsubmission: list[ClientSubmission]
    :ivar _proceduretype: Related procedure types
    :vartype _proceduretype: list[ProcedureType]
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(128), nullable=False, unique=True)  #: name of procedure type
    defaults = Column(JSON)  #: Basic information about this procedure type
    _file_name_template = Column(String(256))  #: Jinja2 template for naming files of this submission type
    regex = Column(String(1024)) #: Raw regex for finding filenames of this submission type
    _turnaround_time = Column((Interval()))
    _abbreviation = Column(String(4))
    _clientsubmission = relationship("ClientSubmission",
                                    back_populates="_submissiontype", cascade="all, delete-orphan")  #: Instances of this submission type
    _proceduretype = relationship("ProcedureType", back_populates="_submissiontype",
                                 secondary=submissiontype_proceduretype)  #: Procedures associated with this submission type

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        clientsubmission = kwargs.pop('clientsubmission', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve clientsubmission
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                logger.error(f"Couldn't set clientsubmission to {clientsubmission} for {self.__class__.__qualname__} with name {self.name}")
    
    @hybrid_property
    def file_name_template(self):
        return self._file_name_template or "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}{% if _completed_date %}_{{ _completed_date.strftime('%Y%m%d %H%M%S') }}{% endif %}"
    
    @file_name_template.setter
    def file_name_template(self, value):
        self._file_name_template = value or "{{rsl_plate_number}}{% if _clientsubmission %}_{{_clientsubmission.submitter_plate_id}}{% endif %}{% if _completed_date %}_{{ _completed_date.strftime('%Y-%m-%d %H:%M:%S') }}{% endif %}"

    @hybrid_property
    def clientsubmission(self):
        return self._clientsubmission

    @clientsubmission.setter
    def clientsubmission(self, value):
        from backend.validators.pydant import PydClientSubmission
        from backend.db.models.submissions import ClientSubmission
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]
        list_ = []
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
                    logger.error(f"Unmatched value: {item} for {self.__class__.__qualname__}.clientsubmission")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ClientSubmission):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._clientsubmission")
        self._clientsubmission = list_

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ProcedureType.query(name=item, limit=1)
                case dict():
                    output = ProcedureType.query_or_create(**item)
                case PydProcedureType():
                    output = item.to_sql()
                case ProcedureType():
                    output = item
                case _:
                    logger.error(f"Unmatched value: {item} for {self.__class__.__qualname__}.proceduretype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcedureType):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._proceduretype")
        self._proceduretype = list_
    
    @hybrid_property
    def turnaround_time(self):
        return self._turnaround_time or timedelta(days=5)
        
    @turnaround_time.setter
    def turnaround_time(self, value):
        match value:
            case int() | str():
                output = timedelta(days=int(value))
            case timedelta():
                output = value
            case _:
                logger.warning(f"Unmatched value {value} for {self.__class__.__qualname__}.turnaround_time")
                output = timedelta(days=5)
        if isinstance(output, timedelta):
            self._turnaround_time = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}.turnaround_time to {type(output)}")

    @hybrid_property
    def abbreviation(self):
        return self._abbreviation
    
    @abbreviation.setter
    def abbreviation(self, value):
        if not isinstance(value, str):
            value = str(value)
        self._abbreviation = value[0:4]

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              key: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> SubmissionType | List[SubmissionType]:
        """
        Lookup submission types by name or key.

        :param name: Name of submission type. Defaults to None.
        :type name: str | None
        :param key: A key present in the info-map to lookup. Defaults to None.
        :type key: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: SubmissionType or list of SubmissionType objects matching filter.
        :rtype: SubmissionType | List[SubmissionType]
        """
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match key:
            case str():
                query = query.filter(cls.info_map.op('->')(key) is not None)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @check_authorization
    def save(self):
        """
        Adds this control to the database and commits.
        """
        super().save()

    @classproperty
    def regexes(cls) -> re.Pattern:
        """
        Construct a catchall regular expression for all submission type regexes.

        :return: compiled regular expression covering all submission types.
        :rtype: re.Pattern
        """
        res = [st.regex for st in cls.query() if st.regex]
        rstring = rf'{"|".join(res)}'
        regex = re.compile(rstring, flags=re.IGNORECASE | re.VERBOSE)
        return regex
    
    @classmethod
    def get_regex(cls, submission_type: SubmissionType | str | dict | None = None) -> re.Pattern | None:
        """
        Get a compiled regex for a submission type or submission type list.

        :param submission_type: procedure type of interest. Defaults to None.
        :type submission_type: SubmissionType | str | dict | None
        :return: compiled regular expression for the submission type, or None.
        :rtype: re.Pattern | None
        """
        if isinstance(submission_type, dict):
            submission_type = submission_type.get('value', None)
        if not isinstance(submission_type, SubmissionType):
            submission_type = cls.query(name=submission_type)
        if isinstance(submission_type, list):
            if len(submission_type) > 1:
                regex = "|".join([item.regex for item in submission_type])
            else:
                regex = submission_type[0].regex
        else:
            try:
                regex = submission_type.regex
            except AttributeError as e:
                logger.error(f"Couldn't get submission type for {submission_type.name}")
                regex = None
        if regex is not None:
            try:
                regex = re.compile(rf"{regex}", flags=re.IGNORECASE | re.VERBOSE)
            except re.error as e:
                regex = None
        return regex
    
    @property
    def template(self) -> Template:
        return Template(str(self.file_name_template))

    @classmethod
    def find_by_resultstype(cls, resultstype: ResultsType | str) -> list[SubmissionType]:
        """
        Find submission types associated with a given results type.

        :param resultstype: ResultsType or name of results type to find associated submission types for.
        :type resultstype: ResultsType | str
        :return: List of SubmissionType objects associated with the given results type.
        :rtype: list[SubmissionType]
        """
        if not resultstype:
            logger.error("No results type provided for find_by_resultstype")
            return []
        if isinstance(resultstype, str):
            resultstype = ResultsType.query(name=resultstype, limit=1)
        if isinstance(resultstype, list):
            if len(resultstype) > 1:
                logger.warning(f"Multiple results types found for {resultstype}. Using first match.")
            resultstype = resultstype[0]
        if not isinstance(resultstype, ResultsType):
            logger.error(f"Could not find results type for {resultstype}")
            return []
        submissiontypes = cls.__database_session__.query(cls).join(cls._proceduretype).join(ProcedureType._resultstype).filter(ResultsType.id == resultstype.id).all()
        return submissiontypes


class ProcedureType(BaseClass):
    """
    Represents a category of procedure and its permitted reagents, equipment, results, and submission types.

    :ivar id: Primary key identifier for the procedure type
    :vartype id: int
    :ivar name: Unique procedure type name
    :vartype name: str
    :ivar plate_columns: Number of plate columns
    :vartype plate_columns: int
    :ivar plate_rows: Number of plate rows
    :vartype plate_rows: int
    :ivar plate_cost: Cost per procedure plate
    :vartype plate_cost: float
    :ivar _procedure: Related Procedure instances
    :vartype _procedure: list[Procedure]
    :ivar _submissiontype: Related SubmissionType objects
    :vartype _submissiontype: list[SubmissionType]
    :ivar _resultstype: Related ResultsType objects
    :vartype _resultstype: list[ResultsType]
    :ivar _discount: Related Discount objects
    :vartype _discount: list[Discount]
    :ivar proceduretypeequipmentroleassociation: Equipment role associations
    :vartype proceduretypeequipmentroleassociation: list[ProcedureTypeEquipmentRoleAssociation]
    :ivar _equipmentrole: Association proxy to EquipmentRole
    :vartype _equipmentrole: list[EquipmentRole]
    :ivar proceduretypereagentroleassociation: Reagent role associations
    :vartype proceduretypereagentroleassociation: list[ProcedureTypeReagentRoleAssociation]
    :ivar _reagentrole: Association proxy to ReagentRole
    :vartype _reagentrole: list[ReagentRole]
    """
    id = Column(INTEGER, primary_key=True)
    name = Column(String(64), nullable=False, unique=True)
    plate_columns = Column(INTEGER, default=0)
    plate_rows = Column(INTEGER, default=0)
    plate_cost = Column(FLOAT(2), default=0.00)

    _procedure = relationship("Procedure",
                             back_populates="_proceduretype", cascade="all, delete-orphan")  #: Concrete control of this type.

    _submissiontype = relationship("SubmissionType", back_populates="_proceduretype",
                                  secondary=submissiontype_proceduretype)  #: run this kittype was used for

    _resultstype = relationship("ResultsType", back_populates="_proceduretype",
                                  secondary=proceduretype_resulttype)  #: run this kittype was used for
    
    _discount = relationship("Discount", back_populates="_proceduretype")

    proceduretypeequipmentroleassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="_proceduretype",
        cascade="all, delete-orphan"
    )  #: Association of equipmentroles

    _equipmentrole = association_proxy("proceduretypeequipmentroleassociation", "_equipmentrole",
                                       creator=lambda equipmentrole: ProcedureTypeEquipmentRoleAssociation(equipmentrole=equipmentrole))  #: Proxy of equipmentrole associations

    proceduretypereagentroleassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        back_populates="_proceduretype",
        cascade="all, delete-orphan"
    )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes

    _reagentrole = association_proxy("proceduretypereagentroleassociation", "_reagentrole",
                                     creator=lambda reagentrole: ProcedureTypeReagentRoleAssociation(reagentrole=reagentrole))  #: Proxy of reagentrole associations

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        procedure = kwargs.pop('procedure', None)
        submissiontype = kwargs.pop('submissiontype', None)
        resultstype = kwargs.pop('resultstype', None)
        equipmentrole = kwargs.pop('equipmentrole', None)
        reagentrole = kwargs.pop('reagentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve submissiontype
        if submissiontype is not None:
            try:
                self.submissiontype = submissiontype
            except Exception:
                logger.error(f"Couldn't set submissiontype to {submissiontype} for {self.__class__.__qualname__} with name {self.name}")
        else:
            self.submissiontype = ["Default SubmissionType"]
        if resultstype is not None:
            try:
                self.resultstype = resultstype
            except Exception:
                logger.error(f"Couldn't set resultstype to {resultstype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipmentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                logger.error(f"Couldn't set equipmentrole to {equipmentrole} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                logger.error(f"Couldn't set reagentrole to {reagentrole} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def equipmentrole(self):
        return self._equipmentrole
    
    @equipmentrole.setter
    def equipmentrole(self, value):
        from backend.validators.pydant import PydEquipmentRole
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.proceduretypeequipmentroleassociation if assoc.equipmentrole.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.equipmentrole.name for eq in self.proceduretypeequipmentroleassociation]}")
                        output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self)
                case EquipmentRole():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self, **{k: v for k, v in item.details_dict.items() if k not in ['equipmentrole', 'proceduretype', 'name']})
                case PydEquipmentRole():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self, **{k: v for k, v in item.improved_dict.items() if k not in ['equipmentrole', 'proceduretype', 'name']})
                case dict():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item, proceduretype=self, **{k: v for k, v in item.items() if k not in ['equipmentrole', 'proceduretype', 'name']})
                case ProcedureTypeEquipmentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipmentrole")
                    continue
            if isinstance(output, ProcedureTypeEquipmentRoleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Couldn't add {output} to {self.__class__.__qualname__}._equipmentrole")
        self.proceduretypeequipmentroleassociation = list_
            
    @hybrid_property
    def reagentrole(self):
        return self._reagentrole    
    
    @reagentrole.setter
    def reagentrole(self, value):
        from backend.validators.pydant import PydReagentRole
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.proceduretypereagentroleassociation if assoc.reagentrole.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.reagent.name for eq in self.proceduretypereagentroleassociation]}")
                        output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self)
                case ReagentRole():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self, **{k: v for k, v in item.details_dict.items() if k not in ['name', 'proceduretype']})
                case PydReagentRole():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self, **{k: v for k, v in item.improved_dict.items() if k not in ['name', 'proceduretype']})
                case dict():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item, proceduretype=self, **{k: v for k, v in item.items() if k not in ['name', 'proceduretype']})
                case ProcedureTypeReagentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {type(item)} for {self.__class__.__qualname__}._reagentrole")
                    continue
            if isinstance(output, ProcedureTypeReagentRoleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Couldn't add {item} to {self.__class__.__qualname__}._reagentrole")
        self.proceduretypereagentroleassociation = list_

    @hybrid_property
    def resultstype(self):
        return self._resultstype

    @resultstype.setter
    def resultstype(self, value):
        from backend.validators.pydant import PydResultsType
        if value is None:
            return
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ResultsType.query(name=item, limit=1)
                case dict():
                    output = ResultsType.query_or_create(**item)
                case PydResultsType():
                    output = item.to_sql(update=False)
                case ResultsType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}.resultstype.")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ResultsType):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._resultstype")
        self._resultstype = list_
    
    @hybrid_property
    def submissiontype(self):
        return self._submissiontype

    @submissiontype.setter
    def submissiontype(self, value):
        from backend.validators.pydant import PydSubmissionType
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = SubmissionType.query(name=item, limit=1)
                case dict():
                    output = SubmissionType.query_or_create(**item)
                case PydSubmissionType():
                    output = item.to_sql(update=False)
                case SubmissionType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._submissiontype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, SubmissionType):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._submissiontype")
        # NOTE: Ensure this has access to "Default SubmissionType"
        check_subtypes = [st.name for st in list_]
        if "Default SubmissionType" not in check_subtypes:
            list_.append(SubmissionType.query(name="Default SubmissionType", limit=1))
        self._submissiontype = list_
        
    @hybrid_property
    def procedure(self):
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Procedure.query(name=item, limit=1)
                case dict():
                    output = Procedure.query_or_create(**item)
                case PydProcedure():
                    output = item.to_sql(update=False)
                case Procedure():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._procedure")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Procedure):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}.procedure")
        self._procedure = list_

    @hybrid_property
    def discount(self):
        return self._discount

    @discount.setter
    def discount(self, value):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case dict():
                    output = Discount.query_or_create(**item)
                case Discount():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._discount")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Discount):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._discount")
        self._discount = list_

    @classmethod
    @setup_lookup
    def query(cls, id: int | None = None, name: str | None = None, limit: int = 0,
              **kwargs) -> Procedure | List[
        Procedure]:
        """
        Lookup procedure types by id or name.

        :param id: Procedure type id. Defaults to None.
        :type id: int | None
        :param name: Procedure type name or prefix. Defaults to None.
        :type name: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: ProcedureType or list of ProcedureTypes matching filter.
        :rtype: ProcedureType | List[ProcedureType]
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
                # NOTE: Updated to startswith to enable search using truncated excel tab names.
                # Possible problem: Another procedure starts with same string.
                query = query.filter(cls.name.istartswith(name))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def construct_dummy_procedure(self, run: Run | None = None) -> PydProcedure:
        """
        Build a PydProcedure with empty sample data for this procedure type.

        :param run: Optional Run to attach to the dummy procedure.
        :type run: Run | None
        :return: Constructed PydProcedure instance.
        :rtype: PydProcedure
        """
        from backend.validators.pydant import PydProcedure
        if run:
            samples = run.constuct_sample_dicts_for_proceduretype(proceduretype=self)
            run = run.to_pydantic()
        else:
            samples = []
        output = dict(
            proceduretype=self,
            repeat=False,
            run=run,
            sample=samples
        )
        return PydProcedure(**output)
    
    @property
    def ranked_plate(self):
        """
        Create a ranked plate mapping from plate coordinates.

        :return: dictionary mapping rank to (row, column) coordinates.
        :rtype: dict[int, tuple[int, int]]
        """
        # NOTE: rows/columns
        matrix = np.array([[0 for yyy in range(1, self.plate_rows + 1)] for xxx in range(1, self.plate_columns + 1)])
        return {iii: (item[0][1] + 1, item[0][0] + 1) for iii, item in enumerate(np.ndenumerate(matrix), start=1)}

    @property
    def total_wells(self) -> int:
        return self.plate_rows * self.plate_columns

    @property
    def allowed_result_methods(self) -> List[dict]:
        """
        Return metadata dictionaries for all result methods allowed by this procedure type.

        :return: List of result method details dictionaries.
        :rtype: list[dict]
        """
        return [item.details_dict for item in self.resultstype]
    
    @property
    def preprocessing_methods(self) -> Iterator[tuple[str, callable, ResultsType]]:
        """
        Yield preprocessing controls for each allowed result method.

        :return: Generator yielding tuples of (label, function, ResultsType).
        :rtype: Iterator[tuple[str, callable, ResultsType]]
        """
        from backend.excel.writers import results_settings
        for method in self.allowed_result_methods:
            settings_name = f"{method['name'].replace(' ', '')}Settings"
            results_type = next((item for item in self.resultstype if item.name == method['name']), None)
            if not results_type:
                continue
            try:
                func = getattr(results_settings, settings_name, None)
            except AttributeError:
                continue
            if not func:
                continue
            if func:
                yield func.label, func, results_type
            

class Procedure(BaseClass):
    """
    Represents an executed procedure within a run.

    :ivar id: Primary key identifier for the procedure
    :vartype id: int
    :ivar repeat_of_id: Foreign key to a repeated procedure
    :vartype repeat_of_id: int
    :ivar _cost: Calculated cost for the procedure
    :vartype _cost: float
    :ivar _repeat_of: Reference to the repeated procedure
    :vartype _repeat_of: Procedure|None
    :ivar _started_date: Procedure start timestamp
    :vartype _started_date: datetime|None
    :ivar _completed_date: Procedure completion timestamp
    :vartype _completed_date: datetime|None
    :ivar technician: Technician name
    :vartype technician: str
    :ivar _results: Associated results records
    :vartype _results: list[Results]
    :ivar proceduretype_id: Foreign key to the procedure type
    :vartype proceduretype_id: int
    :ivar _proceduretype: Related ProcedureType object
    :vartype _proceduretype: ProcedureType|None
    :ivar run_id: Foreign key to the parent run
    :vartype run_id: int
    :ivar _run: Related Run object
    :vartype _run: Run|None
    :ivar proceduresampleassociation: Sample associations for this procedure
    :vartype proceduresampleassociation: list[ProcedureSampleAssociation]
    :ivar _sample: Association proxy to sample objects
    :vartype _sample: list[Sample]
    :ivar procedurereagentlotassociation: Reagent lot associations for this procedure
    :vartype procedurereagentlotassociation: list[ProcedureReagentLotAssociation]
    :ivar _reagentlot: Association proxy to reagent lots
    :vartype _reagentlot: list[ReagentLot]
    :ivar procedureequipmentassociation: Equipment associations for this procedure
    :vartype procedureequipmentassociation: list[ProcedureEquipmentAssociation]
    :ivar _equipment: Association proxy to equipment objects
    :vartype _equipment: list[Equipment]
    """
    id = Column(INTEGER, primary_key=True)  #: Primary key
    repeat_of_id = Column(INTEGER, ForeignKey("_procedure.id", name="fk_repeat_id"))
    _cost = Column(FLOAT(2), default=0.00)
    _repeat_of = relationship("Procedure", remote_side=[id])
    _started_date = Column(TIMESTAMP)
    _completed_date = Column(TIMESTAMP)
    technician = Column(String(64))  #: name of processing tech(s)
    _results = relationship("Results", back_populates="_procedure", uselist=True, cascade="all, delete-orphan")  #: Results from this procedure
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete="SET NULL",
                                                  name="fk_PRO_proceduretype_id"))  #: client lab id from _organizations))
    _proceduretype = relationship("ProcedureType", back_populates="_procedure")  #: ProcedureType of this procedure
    run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="CASCADE",
                                        name="fk_PRO_basicrun_id"), nullable=False)  #: id of parent run, set to CASCADE on delete to remove procedures if run is deleted
    _run = relationship("Run", back_populates="_procedure")  #: Run this procedure is part of
    _comment = Column(JSON)  #: user notes

    proceduresampleassociation = relationship(
        "ProcedureSampleAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan",
    )

    _sample = association_proxy("proceduresampleassociation", "_sample",
                                creator=lambda sample: ProcedureSampleAssociation(sample=sample))  #: Association proxy to Sample

    procedurereagentlotassociation = relationship(
        "ProcedureReagentLotAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan",
    )  #: Relation to ProcedureReagentAssociation

    _reagentlot = association_proxy("procedurereagentlotassociation", "_reagentlot",
                                    creator=lambda reagentlot: ProcedureReagentLotAssociation(reagentlot=reagentlot))  #: Association proxy to ReagentLot

    procedureequipmentassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan"
    )  #: Relation to Equipment

    _equipment = association_proxy("procedureequipmentassociation", "_equipment")  #: Association proxy to RunEquipmentAssociation.equipment

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        repeat_of = kwargs.pop('repeat_of', None)
        started_date = kwargs.pop('started_date', datetime.now())
        completed_date = kwargs.pop('completed_date', None)
        proceduretype = kwargs.pop('proceduretype', None)
        results = kwargs.pop('results', None)
        run = kwargs.pop('run', None)
        sample = kwargs.pop('sample', None)
        reagentlot = kwargs.pop('reagentlot', None)
        equipment = kwargs.pop('equipment', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve repeat_of
        if repeat_of is not None:
            try:
                self.repeat_of = repeat_of
            except Exception:
                logger.error(f"Couldn't set repeat_of to {repeat_of} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve started_date
        if started_date is not None:
            try:
                self.started_date = started_date
            except Exception:
                logger.error(f"Couldn't set started_date to {started_date} for {self.__class__.__qualname__} with name {self.name}")
        if completed_date is not None:
            try:
                self.completed_date = completed_date
            except Exception:
                # fallback: store in misc_info if setter fails
                logger.error(f"Couldn't set completed_date to {completed_date} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve results
        if results is not None:
            try:
                self.results = results
            except Exception:
                logger.error(f"Couldn't set results to {results} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve run
        if run is not None:
            try:
                self.run = run
            except Exception:
                logger.error(f"Couldn't set run to {run} for {self.__class__.__qualname__} with name {self.name}")
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                logger.error(f"Couldn't set sample to {sample} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentlot
        if reagentlot is not None:
            try:
                self.reagentlot = reagentlot
            except Exception:
                logger.error(f"Couldn't set reagentlot to {reagentlot} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipment
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                logger.error(f"Couldn't set equipment to {equipment} for {self.__class__.__qualname__} with name {self.name}")
        self._comment = [] if self._comment is None else self._comment

    @hybrid_property
    def name(self) -> str:
        try:
            run = self.run.name
        except AttributeError:
            run = "Unknown Run"
        try:
            proceduretype = self.proceduretype.name
        except AttributeError:
            proceduretype = "Unknown ProcedureType"
        try:
            started_date = self.started_date.strftime("%Y-%m-%d %H:%M:%S")
        except AttributeError:
            started_date = "NA"
        return f"{run} - {proceduretype} - {started_date}"  
    
    @name.expression
    def name(cls):
        from backend.db.models import Run
        # Create an alias to avoid the recursive property lookup
        run_subquery = (
            select(Run.name)
            .where(Run.id==cls.run_id)
            .scalar_subquery()
        )
        proceduretype_subquery = (
            select(ProcedureType.name)
            .where(ProcedureType.id==cls.proceduretype_id)
            .scalar_subquery()
        )
        # Use func.concat or comma-separated args in func.concat to force the || operator
        return func.coalesce(run_subquery, "Unknown Run") + \
            " - " + \
            func.coalesce(proceduretype_subquery, "Unknown ProcedureType") + \
            " - " + \
            func.coalesce(func.strftime("%Y-%m-%d %H:%M:%S", cls._started_date), "NA")

    @hybrid_property
    def reagentlot(self):
        return self._reagentlot
    
    @reagentlot.setter
    def reagentlot(self, value):
        from backend.validators.pydant import PydProcedureReagentLotAssociation
        if not isinstance(value, list):
            value = [value]
        built = []  # Clear existing associations to prevent duplicates when resetting reagent lots
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.procedurereagentlotassociation if assoc.reagentlot.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.reagentlot.name for eq in self.procedurereagentlotassociation]}")
                        output = ProcedureReagentLotAssociation(reagentlot=item, procedure=self)
                case PydProcedureReagentLotAssociation():
                    # If the child Pydantic object has a reference to the parent, 
                    # update its internal reference to match the current live sql_instance first.
                    output = item.to_sql()
                case dict():
                    output = ProcedureReagentLotAssociation(reagentlot=item, procedure=self, **{k: v for k, v in item.items() if k not in ['reagentlot', 'procedure']})
                case ReagentLot():
                    output = ProcedureReagentLotAssociation(reagentlot=item, procedure=self)
                case ProcedureReagentLotAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._reagentlot")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            
            if isinstance(output, ProcedureReagentLotAssociation):
                if not self.already_in_collection(output, built):
                    built.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._reagentlot")
        self.procedurereagentlotassociation = built    
        

    @hybrid_property
    def equipment(self):
        return self._equipment
    
    # @equipment.setter
    # def equipment(self, value):
    #     from backend.validators.pydant import PydEquipment, PydProcedureEquipmentAssociation
    #     if not isinstance(value, list):
    #         value = [value]
    #     self.procedureequipmentassociation = []  # Clear existing associations to prevent duplicates when resetting equipment
    #     for item in value:
    #         match item:
    #             case str():
    #                 try:
    #                     output = next((assoc for assoc in self.procedureequipmentassociation if assoc.equipment.name==item))
    #                 except StopIteration:
    #                     logger.error(f"Couldn't find {item} in {[eq.equipment.name for eq in self.procedureequipmentassociation]}")
    #                     output = ProcedureEquipmentAssociation(equipment=item, procedure=self)
    #             case Equipment():
    #                 output = ProcedureEquipmentAssociation(equipment=item, procedure=self)
    #             case PydEquipment():
    #                 output = ProcedureEquipmentAssociation(equipment=item, procedure=self, **{k: v for k, v in item.improved_dict.items() if k not in ['name', 'procedure', 'equipment']})
    #             case dict():
    #                 output = ProcedureEquipmentAssociation(equipment=item, procedure=self, **{k: v for k, v in item.items() if k not in ['name', 'procedure', "equipment"]})
    #             case ProcedureEquipmentAssociation():
    #                 output = item
    #                 output.procedure = self
    #             case PydProcedureEquipmentAssociation():
    #                 output = item.to_sql()
    #             case _:
    #                 logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipment")
    #                 continue
    #         if isinstance(output, tuple):
    #             output = output[0]
    #         output.procedure = self
    #         if isinstance(output, ProcedureEquipmentAssociation):
    #             if not self.already_in_collection(output, self.procedureequipmentassociation):
    #                 self.procedureequipmentassociation.append(output)
    #         else:
    #             logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._equipment")
        
    @equipment.setter
    def equipment(self, value):
        from backend.validators.pydant import PydEquipment, PydProcedureEquipmentAssociation
        if not isinstance(value, list):
            value = [value]
        built = []                                   # build into a temp list...
        for item in value:
            match item:
                case str():
                    output = ProcedureEquipmentAssociation(equipment=item)
                case Equipment():
                    output = ProcedureEquipmentAssociation(equipment=item)
                case PydEquipment():
                    output = ProcedureEquipmentAssociation(
                        equipment=item,
                        **{k: v for k, v in item.improved_dict.items()
                        if k not in ['name', 'procedure', 'equipment']})
                case dict():
                    output = ProcedureEquipmentAssociation(
                        equipment=item,
                        **{k: v for k, v in item.items()
                        if k not in ['name', 'procedure', 'equipment']})
                case ProcedureEquipmentAssociation():
                    output = item
                case PydProcedureEquipmentAssociation():
                    output = item.to_sql()
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipment")
                    continue
            if isinstance(output, tuple):            # tolerate any legacy tuple return
                output = output[0]
            if isinstance(output, ProcedureEquipmentAssociation):
                if not self.already_in_collection(output, built):
                    built.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._equipment")
        # ...then one atomic assignment. This replaces contents, sets each member's
        # back-ref to self via back_populates, and only runs if the whole list built
        # without raising. No clear-first window, and no double-add.
        self.procedureequipmentassociation = built

    @hybrid_property
    def sample(self):
        return self._sample
    
    @sample.setter
    def sample(self, value):
        from .submissions import ProcedureSampleAssociation, Sample
        from backend.validators.pydant import PydSample, PydProcedureSampleAssociation
        if not isinstance(value, list):
            value = [value]
        self.proceduresampleassociation = []  # Clear existing associations to prevent duplicates when resetting samples
        for iii, item in enumerate(value, start=1):
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.proceduresampleassociation if assoc.sample.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.sample.name for eq in self.proceduresampleassociation]}")
                        output = ProcedureSampleAssociation(sample=item, procedure=self, rank=iii)
                case PydProcedureSampleAssociation():
                    output = item.to_sql()
                case Sample():
                    output = ProcedureSampleAssociation(sample=item, procedure=self, rank=item._misc_info.get("rank", iii))
                case PydSample():
                    output = ProcedureSampleAssociation(sample=item, procedure=self, rank=getattr(item, "rank", iii), **{k: v for k, v in item.improved_dict.items() if k not in ['name', 'rank', 'sample', 'procedure']})
                case dict():
                    output = ProcedureSampleAssociation(sample=item, procedure=self, rank=item.get("rank", iii), **{k: v for k, v in item.items() if k not in ['name', 'rank', 'sample', 'procedure']})
                case ProcedureSampleAssociation():
                    output = item
                    output.procedure_rank = iii
                case _:
                    logger.error(f"Unmatched value {item} for {item.__class__.__qualname__}._sample")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            output.procedure = self
            if isinstance(output, ProcedureSampleAssociation):
                try:
                    check = output.sample.sample_id.lower().startswith(("blank", "na", "none", ""))
                except AttributeError as e:
                    logger.error(f"Couldn't get sample_id due to {e}")
                    check = True
                if check:
                    continue
                # Check for existing association by comparing all primary key values
                logger.debug(f"Checking {output} using {output.get_primary_keys()}")
                if not self.already_in_collection(output, self.proceduresampleassociation):
                    self.proceduresampleassociation.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._sample")
        
    @hybrid_property
    def started_date(self):
        return self._started_date if self._started_date else None

    @started_date.setter
    def started_date(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}._started_date")
        value = output.replace(tzinfo=timezone)
        self._started_date = value

    @hybrid_property
    def completed_date(self):
        return self._completed_date if self._completed_date else None

    @completed_date.setter
    def completed_date(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}._completed_date")
        value = output.replace(tzinfo=timezone)
        self._completed_date = value

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        match value:
            case str():
                output = ProcedureType.query(name=value, limit=1)
            case dict():
                output = ProcedureType.query_or_create(**value)
            case PydProcedureType():
                output = value.to_sql(update=False)
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._proceduretype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._proceduretype to {type(output)}")

    @hybrid_property
    def run(self):
        return self._run

    @run.setter
    def run(self, value):
        from backend.validators.pydant import PydRun
        from .submissions import Run
        match value:
            case str():
                output = Run.query(name=value, limit=1)
            case dict():
                # If caller provided a clientsubmission object inside the dict, avoid
                # running Run.query_or_create which may build queries with pagination
                # applied earlier; instead construct a Run instance directly.
                if isinstance(cs, BaseClass):
                    output = Run(**value)
                else:
                    output = Run.query_or_create(**value)
            case PydRun():
                output = value.to_sql(update=False)
            case Run():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._run")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Run):
            self._run = output
        else:
            logger.error(f"Unable to set {self.__class__.__qualname__}._run to {type(output)}")
    
    @hybrid_property
    def results(self):
        return [result for result in self._results if not result.is_sample]  # filter out sample-level results, only return procedure-level results

    @results.setter
    def results(self, value):
        from backend.validators.pydant import PydResults
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        
        for item in value:
            match item:
                case str():
                    output = Results.query(name=item, limit=1)
                case dict():
                    output = Results.query_or_create(**item)
                case PydResults():
                    output = item.to_sql()
                case Results():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._results")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Results):
                if not self.already_in_collection(output, self._results):
                    self._results.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._results")
    
    @hybrid_property
    def repeat_of(self):
        return self._repeat_of

    @repeat_of.setter
    def repeat_of(self, value):
        from backend.validators.pydant import PydProcedure
        match value:
            case str():
                output = Procedure.query(name=value, limit=1)
            case dict():
                output = Procedure.query_or_create(**value)
            case PydProcedure():
                output = value.to_sql(update=False)
                if isinstance(output, tuple):
                    output = output[0]
            case Procedure():
                output = value
            case None:
                output = None
            case _:
                raise ValueError(f"Unmatched value {value} for {self.__class__.__qualname__}._repeat_of")
        if isinstance(output, Procedure):
            self._repeat_of = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._repeat_of to {type(output)}")
    
    @hybrid_property
    def repeat(self) -> bool:
        return self._repeat_of is not None

    @hybrid_property
    def cost(self) -> float:
        return self._cost

    @property
    def info_results(self) -> dict[str, dict]:
        grouped_results: dict[str, dict] = {}
        for result in self._results:
            if result.is_sample or result.assoc_id is not None:
                continue
            try:
                resultstype = result.resultstype.name
            except AttributeError:
                resultstype = "Unassigned ResultsType"
            
            grouped_results[resultstype] = result.to_pydantic()
        return grouped_results

    @property
    def sample_results(self) -> dict[str, list]:
        grouped_results: dict[str, list] = {}
        for result in flatten_list([[result for result in item.results] for item in self.proceduresampleassociation]):
            if not result.is_sample:
                continue
            try:
                resultstype = result.resultstype.name
            except AttributeError:
                resultstype = "Unassigned ResultsType"
            grouped_results.setdefault(resultstype, []).append(result.to_pydantic())
        return grouped_results

    @property
    def grouped_results(self) -> dict[str, dict[str, list]]:
        """Group procedure-level and sample-level results by resultstype.

        Returns a dict keyed by resultstype, with nested "procedure" and "sample"
        result lists.
        """
        grouped: dict[str, dict[str, list]] = {}
        procedure_groups = self.info_results
        sample_groups = self.sample_results

        all_resultstypes = set(procedure_groups) | set(sample_groups)
        for resultstype in all_resultstypes:
            grouped[resultstype] = {
                "info": procedure_groups.get(resultstype, None),
                "sample": sample_groups.get(resultstype, []),
            }

        return grouped

    @hybrid_property
    def comment(self):
        if not self._comment:
            return []
        return [item for item in self._comment if all(key in ['user', 'text', 'time'] for key in item.keys())]
    
    @comment.setter
    def comment(self, value):
        if not isinstance(value, dict):
            logger.error(f"Invalid comment value {value} for {self.__class__.__qualname__}, must be a dictionary.")
            return
        if value['text'] in [""]:
            return
        current = self._comment or []
        current.append(value)
        self._comment = current

    @classmethod
    @setup_lookup
    def query(cls, id: int | None = None, name: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None, limit: int = 0, **kwargs) -> Procedure | List[
        Procedure]:
        """
        Lookup procedures by id, name, or date range.

        :param id: Procedure id. Defaults to None.
        :type id: int | None
        :param name: Procedure name or prefix. Defaults to None.
        :type name: str | None
        :param start_date: Start date for procedure start time. Defaults to None.
        :type start_date: date | datetime | str | int | None
        :param end_date: End date for procedure start time. Defaults to None.
        :type end_date: date | datetime | str | int | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: Procedure or list of Procedure objects matching filter.
        :rtype: Procedure | List[Procedure]
        """
        query: Query = cls.__database_session__.query(cls)
        if start_date is not None and end_date is None:
            logger.warning(f"Start date with no end date, using today.")
            end_date = date.today()
        if end_date is not None and start_date is None:
            # NOTE: this query returns a tuple of (object, datetime), need to get only datetime.
            start_date = cls.__database_session__.query(cls, func.min(cls.submitted_date)).first()[1]
            logger.warning(f"End date with no start date, using first procedure date: {start_date}")
        if start_date is not None:
            start_date = cls.rectify_query_date(start_date)
            end_date = cls.rectify_query_date(end_date, eod=True)
            query = query.filter(cls.started_date.between(start_date, end_date))
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                # NOTE: Updated to startswith to enable search using truncated excel tab names.
                # Possible problem: Another procedure starts with same string.
                query = query.filter(cls.name.istartswith(name))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @property
    def custom_context_events(self) -> dict:
        """
        Create a mapping of event names to handler methods for context menus.

        :return: mapping of context menu labels to callable methods.
        :rtype: dict[str, callable]
        """
        names = ["Add Results", "Edit", "Add Comment", "Show Details", "Delete"]
        return {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}

    def add_results(self, obj, resultstype_name: str):
        """
        Add results for this procedure using a manager determined by resultstype_name.

        :param obj: Parent object owning the procedure UI.
        :type obj: Any
        :param resultstype_name: Name of the result type to add.
        :type resultstype_name: str
        :return: None
        """
        resultstype = resultstype_name.replace(" ", "")
        logger.info(f"Add Results! {resultstype_name}")
        from backend.managers import results
        results_manager = getattr(results, f"{resultstype}Manager")
        rs = results_manager(procedure=self, parent=obj)
        procedure_results = rs.procedure_to_pydantic()
        samples_results = rs.samples_to_pydantic()
        if procedure_results:
            procedure_sql = procedure_results.to_sql()
        else:
            return
        if isinstance(procedure_sql, tuple):
            procedure_sql = procedure_sql[0]
        procedure_sql.save()
        for sample in samples_results:
            sample_sql = sample.to_sql()
            if isinstance(sample_sql, tuple):
                sample_sql = sample_sql[0]
            sample_sql.save()

    def edit(self, obj):
        """
        Launch the procedure edit dialog and persist updated procedure details.

        :param obj: Parent UI object used for dialog control.
        :type obj: Any
        :return: None
        """
        from frontend.widgets.procedure_creation import ProcedureCreation
        logger.debug("Edit!")
        procedure = self.construct_pyd_procedure_for_creation()
        procedure.active_reagentroles = [assoc.reagentrole.name for assoc in self.procedurereagentlotassociation]
        procedure.active_equipmentroles = [assoc.equipmentrole.name for assoc in self.procedureequipmentassociation]
        dlg = ProcedureCreation(parent=obj, procedure=procedure, edit=True)
        if dlg.exec():
            sql: Procedure = dlg.return_sql()
            sql.update_last_useds()
            # Use the edited PydProcedure from the dialog to populate SQL relationships
            pyd = dlg.procedure
            sql.sample = pyd.sample
            sql.equipment = pyd.equipment
            sql.save()
        obj.set_data()

    def add_comment(self, obj):
        """
        Add a comment to this procedure.

        This method is a placeholder for comment UI integration.

        :param obj: Parent object for the comment action.
        :type obj: Any
        :return: None
        """
        logger.debug("Add Comment!")
        dlg = SubmissionComment(parent=obj, submission=self)
        if dlg.exec():
            logger.debug(f"Comment dialog returned: {dlg.parse_form()}")
            self.comment = dlg.parse_form()
            self.save()

    @check_authorization
    def delete(self, obj):
        from frontend.widgets.pop_ups import QuestionAsker
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {self.name}?\n")
        if msg.exec():
            self.procedureequipmentassociation = []
            self.procedurereagentlotassociation = []
            self.proceduresampleassociation = []
            self.__database_session__.delete(self)
            try:
                self.__database_session__.commit()
            except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
                self.__database_session__.rollback()
                raise e
            try:
                obj.set_data()
            except AttributeError:
                logger.error("App will not refresh data at this time.")
        
    # TODO: Convert references to details_dict_expand_fields calls so I can trim this down.
    @property
    def details_dict(self) -> dict:
        """
        Produce a JSON-serializable details dictionary for this procedure.

        :return: Detailed procedure metadata for serialization and UI display.
        :rtype: dict
        """
        output = super().details_dict
        try:
            output['proceduretype'] = output['proceduretype'].details_dict['name']
        except AttributeError:
            pass
        output['results'] = [result.details_dict for result in self.results]
        run_samples = [sample for sample in self.run.sample]
        active_samples = [sample.details_dict for sample in self.proceduresampleassociation
                          if sample.sample.sample_id in [s.sample_id for s in run_samples]]
        for sample in active_samples:
            sample['active'] = True
        inactive_samples = [sample.details_dict for sample in run_samples if
                            sample.name not in [s['sample_id'] for s in active_samples]]
        for sample in inactive_samples:
            sample['active'] = False
        output['sample'] = active_samples + inactive_samples
        output['reagent'] = [reagent.details_dict for reagent in self.procedurereagentlotassociation]
        output['equipment'] = [equipment.details_dict for equipment in self.procedureequipmentassociation]
        output['repeat'] = self.repeat
        output['run'] = self.run.name
        output['excluded'] += self.get_default_info("details_ignore")
        output['sample_count'] = len(active_samples)
        output['comment'] = self.comment
        try:
            output['clientlab'] = self.run.clientsubmission.clientlab.name
        except AttributeError:
            logger.error(f"Run: {self.run}, ClientSubmission: {self.run.clientsubmission}")
            output['clientlab'] = "Unknown"
        output['cost'] = 0.00
        return output

    def to_pydantic(self, **kwargs):
        """
        Convert this Procedure into its pydantic representation.

        :param kwargs: Additional keyword arguments for serialization.
        :type kwargs: dict
        :return: Pydantic procedure model representing this SQL object.
        :rtype: BaseModel
        """
        output = super().to_pydantic()
        output.sample = [item.to_pydantic() for item in self.proceduresampleassociation]
        output.run = self.run.to_pydantic()
        output.reagentlot = [item.to_pydantic() for item in self.procedurereagentlotassociation]
        output.equipment = [item.to_pydantic() for item in self.procedureequipmentassociation]
        output.info_results = self.info_results
        output.sample_results = self.sample_results
        return output

    def construct_pyd_procedure_for_creation(self) -> "PydProcedure":
        """Return a widget-ready PydProcedure for ProcedureCreation."""
        from backend.validators.pydant import PydProcedure, PydSample, PydReagentLot, PydProcedureReagentLotAssociation, PydProcedureSampleAssociation

        sample_list = []
        for assoc in self.proceduresampleassociation:
            sample = assoc.sample.to_pydantic() if hasattr(assoc.sample, "to_pydantic") else assoc.sample
            if isinstance(sample, PydSample):
                sample.row = assoc.row
                sample.column = assoc.column
                sample.rank = assoc.procedure_rank
                sample.enabled = getattr(assoc, "enabled", True)
                sample.control_type = ('positivecontrol' if sample.is_control == 1 else 'negativecontrol' if sample.is_control == -1 else 'regular')
            sample_list.append(sample)
        # Build a PydProcedureType instance and attach expanded relationship
        # dicts (reagentrole/equipmentrole) to its model_extra. Mark which
        # roles are already present on this Procedure with a 'filled' flag.
        try:
            pyd_proc_type = self.proceduretype.to_pydantic()
            expanded = pyd_proc_type.improved_dict_expand_fields([
                {"reagentrole": [{"reagent": ["reagentlot"]}]},
                {"equipmentrole": [{"equipmentroleequipmentassociation": ["equipment", "process"]}]}
            ])
            # annotate filled flags on expanded entries
            for item in expanded.get('reagentrole', []):
                item['filled'] = any(assoc.reagentrole.name == item.get('name') for assoc in self.procedurereagentlotassociation)
            for item in expanded.get('equipmentrole', []):
                item['filled'] = any(assoc.equipmentrole.name == item.get('name') for assoc in self.procedureequipmentassociation)
            # attach expanded dicts so templates can read them via proceduretype['reagentrole']
            pyd_proc_type.model_extra.update(expanded)
        except Exception as e:
            logger.error(f"Couldn't build expanded proceduretype for {self.__class__.__qualname__} with name {self.name}")
            logger.error(f"Error: {e}")
            pyd_proc_type = self.proceduretype.to_pydantic() if hasattr(self.proceduretype, 'to_pydantic') else self.proceduretype
        output = dict(
            proceduretype=pyd_proc_type,
            run=self.run.to_pydantic(),
            technician=self.technician,
            repeat=bool(self.repeat),
            repeat_of=self.repeat_of.to_pydantic() if self.repeat_of is not None else None,
            sample=sample_list,
            reagentlot=[item.to_pydantic() for item in self.procedurereagentlotassociation],
            equipment=[item.to_pydantic() for item in self.procedureequipmentassociation],
            results=[item.to_pydantic() for item in self.results],
            started_date=self.started_date,
            completed_date=self.completed_date,
            sql_instance=self,
        )
        pyd = PydProcedure(**output)
        return pyd

    @classmethod
    def get_default_info(cls, *args) -> dict | list | str:
        """
        Return default field visibility and serialization settings.

        :param args: Specific keys to filter in the returned dictionary.
        :type args: tuple
        :return: Default metadata configuration for this class.
        :rtype: dict | list | str
        """
        dicto = super().get_default_info()
        recover = ['filepath', 'sample', 'csv', 'comment', 'equipment']
        dicto.update(dict(
            details_ignore=['excluded', 'reagents', 'sample', 'extraction_info', 'comment', 'barcode',
                            'platemap', 'export_map', 'equipment', 'tips', 'custom', 'reagentlot', 'reagent_lot',
                            "results", "proceduresampleassociation", "sample",
                            "procedurereagentlotassociation",
                            "procedureequipmentassociation", "proceduretipsassociation", "reagent", "equipment",
                            "tips", "control"],
            # NOTE: Fields not placed in ui form
            form_ignore=['reagents', 'ctx', 'id', 'cost', 'extraction_info', 'signed_by', 'comment', 'namer',
                         'submission_object', "tips", 'contact_phone', 'custom', 'cost_centre', 'completed_date',
                         'control', "origin_plate"] + recover,
            # NOTE: Fields not placed in ui form to be moved to pydantic
            form_recover=recover
        ))
        if args:
            if len(args) > 1:
                output = {k: v for k, v in dicto.items() if k in args}
            else:
                output = dicto[args[0]]
        else:
            output = {k: v for k, v in dicto.items()}
        return output

    @property
    def submissiontype(self):
        return self.run.clientsubmission.submissiontype

    def set_cost(self):
        """
        Calculate and store the total cost of this procedure.

        The cost includes reagent volumes, tip usage, and plate cost.

        :return: None
        """
        numbers_array = []
        for reagentlotassoc in self.procedurereagentlotassociation:
            reagent = reagentlotassoc.reagentlot.reagent
            cost_per_ml = reagent.cost_per_ml
            reagentrole = reagentlotassoc.reagentrole
            rr_reg_assoc = ReagentRoleReagentAssociation.query(reagent=reagent, reagentrole=reagentrole, limit=1)
            ml_per_sample = rr_reg_assoc.ml_used_per_sample
            numbers_array.append(cost_per_ml * ml_per_sample * len(self.sample))
        for equipmentassoc in self.procedureequipmentassociation:
            for tipassoc in equipmentassoc.tipslot:
                tip = tipassoc.tips
                cost_per_tip = tip.cost_per_tip
                numbers_array.append(cost_per_tip * len(self.sample))
        samples_cost = np.sum(numbers_array)
        try:
            plate_cost = self.proceduretype.plate_cost or 0.00
        except AttributeError:
            plate_cost = 0.00
        self._cost = plate_cost + samples_cost

    def save(self):
        """
        Persist this procedure after recalculating cost and sample associations.

        :return: None
        """
        from backend.db.models import RunSampleAssociation
        self.set_cost()
        assert self.run is not None
        super().save()
        try:
            rank = max([item.run_rank for item in self.run.runsampleassociation])
        except AttributeError:
            rank = 0
        for iii, sampleassociation in enumerate(self.proceduresampleassociation, start=1):
            if not sampleassociation:
                logger.error(f"No association at rank {iii}")
                continue
            try:
                check = sampleassociation.sample.sample_id in [s.sample_id for s in self.run.sample]
            except AttributeError as e:
                logger.error(f"Couldn't get sample_id due to {e}")
                check = True
            if not check:
                assoc = RunSampleAssociation(sample=sampleassociation.sample, run=self.run, rank=rank+iii)
                assoc.save()
        
    @property
    def column_count(self) -> int:
        """
        Calculate the number of unique columns in this procedure.

        :return: number of unique columns.
        :rtype: int
        """
        columns = set([assoc.column for assoc in self.proceduresampleassociation])
        return len(columns)
    
    @property
    def row_count(self) -> int:
        """
        Calculate the number of unique rows in this procedure.

        :return: number of unique rows.
        :rtype: int
        """
        columns = set([assoc.row for assoc in self.proceduresampleassociation])
        return len(columns)
    
    def update_last_useds(self):
        """
        Update 'last used' reagent lot metadata for each reagent role in this procedure.

        :return: None
        """
        for reagentlotassoc in self.procedurereagentlotassociation:
            reagentrole = reagentlotassoc.reagentrole
            proceduretype = self.proceduretype
            assoc = ProcedureTypeReagentRoleAssociation.query(proceduretype=proceduretype, reagentrole=reagentrole, limit=1)
            if assoc:
                try:
                    assoc.update_last_used(reagentlotassoc.reagentlot)
                except Exception as e:
                    logger.error(f"Error updating last used for {assoc}: {e}")
            else:
                logger.error(f"Association not found for {reagentrole} and {proceduretype}")
                

class ProcedureTypeReagentRoleAssociation(BaseClass):
    """
    Junction model associating procedure types with reagent roles.

    :ivar reagentrole_id: Foreign key to the reagent role
    :vartype reagentrole_id: int
    :ivar proceduretype_id: Foreign key to the procedure type
    :vartype proceduretype_id: int
    :ivar _reagentrole: Related ReagentRole object
    :vartype _reagentrole: ReagentRole
    :ivar _proceduretype: Related ProcedureType object
    :vartype _proceduretype: ProcedureType
    :ivar _last_used: Last used reagent lot association
    :vartype _last_used: ReagentLot|None
    :ivar last_used_lot: Lot number of the last used reagent
    :vartype last_used_lot: str|None
    """

    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id"),
                            primary_key=True)  #: id of associated reagentrole
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"),
                              primary_key=True)  #: id of associated proceduretype
    
    # NOTE: reference to the "ReagentType" object
    _reagentrole = relationship(ReagentRole,
                               back_populates="reagentroleproceduretypeassociation")  #: relationship to associated ReagentType

    # NOTE: reference to the "SubmissionType" object
    _proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypereagentroleassociation")  #: relationship to associated SubmissionType
    # NOTE: reference to the "ReagentLot" object for the last used lot of this type of reagent
    _last_used = relationship(ReagentLot)
    
    last_used_lot = Column(String(64), ForeignKey("_reagentlot.lot"))  #: id of associated procedure

    _always_used = Column(INTEGER, default=1)  #: flag indicating if this reagent role is always used in the procedure type

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the SQL object of this class might go by.

        :return: list of alias names for this junction model.
        :rtype: List[str]
        """
        return super().aliases + ["reagentroleproceduretypeassociation"]
    
    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        reagentrole = kwargs.pop('reagentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                logger.error(f"Couldn't set reagentrole to {reagentrole} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def always_used(self):
        """Return whether this reagent role is always used in the procedure type."""
        au = getattr(self, "_always_used", 1)
        return bool(au)

    @always_used.setter
    def always_used(self, value):
        match value:
            case int():
                self._always_used = value
            case bool():
                self._always_used = int(value)
            case str():
                if value.lower() in ['true', '1', 'yes', 'on']:
                    self._always_used = 1
                elif value.lower() in ['false', '0', 'no', 'off']:
                    self._always_used = 0
                else:
                    raise ValueError(f"Cannot convert string {value} to boolean for {self.__class__.__qualname__}._always_used")
            case _:
                raise TypeError(f"Unsupported type {type(value)} for {self.__class__.__qualname__}._always_used")

    @hybrid_property
    def proceduretype(self):
        """Return the resolved ProcedureType linked to this association."""
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        """Resolve and set the associated ProcedureType from flexible inputs.

        Accepts a ProcedureType instance, PydProcedureType, dict payload, or
        procedure type name string.

        :param value: Input representing the procedure type.
        :type value: ProcedureType | PydProcedureType | dict | str
        :return: None
        """
        from backend.validators.pydant import PydProcedureType
        match value:
            case str():
                output = ProcedureType.query(name=value, limit=1)
            case dict():
                output = ProcedureType.query_or_create(**value)
            case PydProcedureType():
                output = value.to_sql(update=False)
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._proceduretype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._proceduretype to {type(output)}")

    @hybrid_property
    def reagentrole(self):
        """Return the resolved ReagentRole linked to this association."""
        return self._reagentrole

    @reagentrole.setter
    def reagentrole(self, value):
        """Resolve and set the associated ReagentRole from flexible inputs.

        Accepts a ReagentRole instance, PydReagentRole, dict payload, or role
        name string.

        :param value: Input representing the reagent role.
        :type value: ReagentRole | PydReagentRole | dict | str
        :return: None
        """
        from backend.validators.pydant import PydReagentRole
        match value:
            case str():
                output = ReagentRole.query(name=value, limit=1)
            case dict():
                output = ReagentRole.query_or_create(**value)
            case PydReagentRole():
                output = value.to_sql(update=False)
            case ReagentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._reagentrole")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ReagentRole):
            self._reagentrole = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._reagentrole to {type(output)}")

    @hybrid_property
    def name(self):
        try:
            proceduretype = self.proceduretype.name
        except AttributeError:
            proceduretype = "Unassigned ProcedureType"
        try:
            reagentrole = self.reagentrole.name
        except AttributeError:
            reagentrole = "Unassigned ReagentRole"
        return f"{proceduretype}->{reagentrole}"
        
    @name.expression
    def name(cls):
        proceduretype_subquery = (
            select(ProcedureType.name)
            .where(ProcedureType.id==cls.proceduretype_id)
            .correlate(cls)
            .scalar_subquery()
        )
        reagentrole_subquery = (
            select(ReagentRole.name)
            .where(ReagentRole.id==cls.reagentrole_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return proceduretype_subquery + "->" + reagentrole_subquery

    @classmethod
    @setup_lookup
    def query(cls,
              reagentrole: ReagentRole | str | None = None,
              proceduretype: ProcedureType | str | None = None,
              name: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> ProcedureTypeReagentRoleAssociation | List[ProcedureTypeReagentRoleAssociation]:
        """
        Lookup procedure type / reagent role associations.

        :param reagentrole: ReagentRole of interest. Defaults to None.
        :type reagentrole: ReagentRole | str | None
        :param proceduretype: ProcedureType of interest. Defaults to None.
        :type proceduretype: ProcedureType | str | None
        :param name: Association name. Defaults to None.
        :type name: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: ProcedureTypeReagentRoleAssociation or list matching filter.
        :rtype: ProcedureTypeReagentRoleAssociation | List[ProcedureTypeReagentRoleAssociation]
        """
        query: Query = cls.__database_session__.query(cls)
        match reagentrole:
            case ReagentRole():
                query = query.filter(cls.reagentrole == reagentrole)
            case str():
                query = query.join(ReagentRole).filter(ReagentRole.name == reagentrole)
            case _:
                pass
        match proceduretype:
            case ProcedureType():
                query = query.filter(cls.proceduretype == proceduretype)
            case str():
                query = query.join(ProcedureType).filter(ProcedureType.name == proceduretype)
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def update_last_used(self, reagentlot: ReagentLot):
        self._last_used = reagentlot
        self.save()


class ProcedureReagentLotAssociation(BaseClass):
    """
    Represents the association between a procedure and a reagent lot, including reagent role details.

    :ivar reagentlot_id: Foreign key to the reagent lot
    :vartype reagentlot_id: int
    :ivar procedure_id: Foreign key to the procedure
    :vartype procedure_id: int
    :ivar reagentrole_id: Foreign key to the reagent role
    :vartype reagentrole_id: int
    :ivar _comment: Optional comment for the reagent lot usage
    :vartype _comment: str
    :ivar _procedure: Related Procedure object
    :vartype _procedure: Procedure
    :ivar _reagentlot: Related ReagentLot object
    :vartype _reagentlot: ReagentLot
    :ivar _reagentrole: Related ReagentRole object
    :vartype _reagentrole: ReagentRole
    """

    skip_on_edit = True

    procedure_id = Column(INTEGER, ForeignKey("_procedure.id", ondelete="CASCADE"), primary_key=True)  #: id of associated procedure
    reagentlot_id = Column(INTEGER, ForeignKey("_reagentlot.id", ondelete="RESTRICT"), primary_key=True)  #: id of associated reagent
    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id", ondelete="CASCADE"), primary_key=True)
    _comment = Column(String(1024))  #: Comments about reagent

    _procedure = relationship("Procedure",
                             back_populates="procedurereagentlotassociation")  #: associated procedure

    _reagentlot = relationship(ReagentLot, back_populates="reagentlotprocedureassociation")  #: associated reagent

    _reagentrole = relationship(ReagentRole)  #: associated reagentrole

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        procedure = kwargs.pop('procedure', None)
        reagentlot = kwargs.pop('reagentlot', None)
        reagentrole = kwargs.pop('reagentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentlot
        if reagentlot is not None:
            try:
                self.reagentlot = reagentlot
            except Exception:
                logger.error(f"Couldn't set reagentlot to {reagentlot} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                logger.error(f"Couldn't set reagentrole to {reagentrole} for {self.__class__.__qualname__} with name {self.name}")
    
    @hybrid_property
    def name(self):
        try:
            procedure = self.procedure.name
        except AttributeError:
            procedure = "Unassigned Procedure"
        try:
            reagentlot = self.reagentlot.name
        except AttributeError:
            reagentlot = "Unassigned ReagentLot"
        return f"{procedure}->{reagentlot}"

    @name.expression
    def name(cls):
        procedure_subquery = (
            select(Procedure.name)
            .where(Procedure.id==cls.procedure_id)
            .correlate(cls)
            .scalar_subquery()
        )
        reagentlot_subquery = (
            select(ReagentLot.name)
            .where(ReagentLot.id==cls.reagentlot_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return procedure_subquery + "->" + reagentlot_subquery

    @hybrid_property
    def reagentlot(self):
        """Return the resolved ReagentLot associated with this procedure association."""
        return self._reagentlot

    @reagentlot.setter
    def reagentlot(self, value):
        """Resolve and attach the related ReagentLot from a flexible input."""
        from backend.validators.pydant import PydReagentLot
        match value:
            case str():
                output = ReagentLot.query(name=value, limit=1)
            case dict():
                output = ReagentLot.query_or_create(**value)
            case PydReagentLot():
                output = value.to_sql(update=False)
            case ReagentLot():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._reagentlot")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ReagentLot):
            self._reagentlot = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._reagentlot to {type(output)}")
    
    @hybrid_property
    def procedure(self):
        """Return the linked Procedure object for this reagent lot association."""
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        """Resolve and attach the related Procedure from a flexible input."""
        from backend.validators.pydant import PydProcedure
        match value:
            case str():
                output = Procedure.query(name=value, limit=1)
            case dict():
                output = Procedure.query_or_create(**value)
            case PydProcedure():
                output = value.to_sql(update=False)
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._procedure")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._procedure to {type(output)}")

    @hybrid_property
    def reagentrole(self):
        """Return the resolved ReagentRole for this procedure/reagent lot association."""
        return self._reagentrole

    @reagentrole.setter
    def reagentrole(self, value):
        """Resolve and attach the related ReagentRole from flexible input."""
        from backend.validators.pydant import PydReagentRole
        match value:
            case str():
                output = ReagentRole.query(name=value, limit=1)
            case dict():
                output = ReagentRole.query_or_create(**value)
            case PydReagentRole():
                output = value.to_sql(update=False)
            case ReagentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._reagentrole")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ReagentRole):
            self._reagentrole = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._reagentrole to {type(output)}")

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              procedure: Procedure | str | int | None = None,
              reagentlot: ReagentLot | str | None = None,
              reagentrole: str | ReagentRole | None = None,
              limit: int = 0) -> ProcedureReagentLotAssociation | List[ProcedureReagentLotAssociation]:
        """
        Lookup procedure/reagent lot associations.

        :param name: Association name. Defaults to None.
        :type name: str | None
        :param procedure: Identifier of joined procedure. Defaults to None.
        :type procedure: Procedure | str | int | None
        :param reagentlot: Identifier of joined reagent lot. Defaults to None.
        :type reagentlot: ReagentLot | str | None
        :param reagentrole: Identifier of joined reagent role. Defaults to None.
        :type reagentrole: ReagentRole | str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: ProcedureReagentLotAssociation or list matching filter.
        :rtype: ProcedureReagentLotAssociation | List[ProcedureReagentLotAssociation]
        """
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
            case _:
                pass
        match reagentlot:
            case ReagentLot() | str():
                if isinstance(reagentlot, str):
                    reagentlot = ReagentLot.query(lot=reagentlot)
                query = query.filter(cls.reagentlot == reagentlot)
            case _:
                pass
        match procedure:
            case Procedure() | str():
                if isinstance(procedure, str):
                    procedure = Procedure.query(name=procedure)
                query = query.filter(cls.procedure == procedure)
            case int():
                query = query.join(Procedure).filter(Procedure.id == procedure)
            case _:
                pass
        if reagentrole:
            if isinstance(reagentrole, str):
                reagentrole = ReagentRole.query(name=reagentrole)
            query = query.filter(cls.reagentrole == reagentrole)
        return cls.execute_query(query=query, limit=limit)

    @property
    def details_dict(self) -> dict:
        """
        Return a merged details dictionary for this procedure/reagent lot association.

        :return: Serialized details for this association.
        :rtype: dict
        """
        output = super().details_dict
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['reagent']}
        output = self.reagentlot.details_dict
        output['reagent_name'] = self.reagentlot.reagent.name
        misc = output.get('misc_info', {})
        output.update(relevant)
        output['reagentrole'] = self.reagentrole.name
        output['misc_info'] = misc
        return output

    def delete(self, **kwargs):
        """
        Remove this association record from the database.

        :return: None
        """
        self.__database_session__.delete(self)
        try:
            self.__database_session__.commit()
        except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
            self.__database_session__.rollback()
            raise e

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the SQL object of this class might go by.

        :return: list of alias names for this junction model.
        :rtype: List[str]
        """
        return super().aliases + ["reagentlotprocedureassociation"]


class ReagentRoleReagentAssociation(BaseClass):
    """
    Junction model associating reagents with their roles.

    :ivar reagentrole_id: Foreign key to the reagent role
    :vartype reagentrole_id: int
    :ivar reagent_id: Foreign key to the reagent
    :vartype reagent_id: int
    :ivar ml_used_per_sample: Volume used per sample for this role
    :vartype ml_used_per_sample: float|None
    :ivar _reagent: Related reagent object
    :vartype _reagent: Reagent
    :ivar _reagentrole: Related reagent role object
    :vartype _reagentrole: ReagentRole
    """
    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id", ondelete="CASCADE"), primary_key=True)  #: id of associated reagent
    reagent_id = Column(INTEGER, ForeignKey("_reagent.id", ondelete="CASCADE"), primary_key=True)  #: id of associated procedure
    ml_used_per_sample = Column(FLOAT(3))  #: amount of reagent used for this role.
    
    _reagent = relationship(Reagent, back_populates="reagentreagentroleassociation")  #: associated procedure

    _reagentrole = relationship(ReagentRole, back_populates="reagentrolereagentassociation")  #: associated reagent

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for reagent and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        reagent = kwargs.pop('reagent', None)
        reagentrole = kwargs.pop('reagentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve reagent
        if reagent is not None:
            try:
                self.reagent = reagent
            except Exception:
                logger.error(f"Couldn't set reagent to {reagent} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                logger.error(f"Couldn't set reagentrole to {reagentrole} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def name(self):
        try:
            reagent = self.reagent.name
        except AttributeError:
            reagent = "Unassigned Reagent"
        try:
            reagentrole = self.reagentrole.name
        except AttributeError:
            reagentrole = "Unassigned ReagentRole"
        return f"{reagentrole}->{reagent}"

    @name.expression
    def name(cls):
        reagentrole_subquery = (
            select(ReagentRole.name)
            .where(ReagentRole.id==cls.reagentrole_id)
            .correlate(cls)
            .scalar_subquery()
        )
        reagent_subquery = (
            select(Reagent.name)
            .where(Reagent.id==cls.reagent_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return reagentrole_subquery + "->" + reagent_subquery

    @hybrid_property
    def reagent(self):
        return self._reagent

    @reagent.setter
    def reagent(self, value):
        from backend.validators.pydant import PydReagent
        match value:
            case str():
                output = Reagent.query(name=value, limit=1)
            case dict():
                output = Reagent.query_or_create(**value)
            case PydReagent():
                output = value.to_sql(update=False)
            case Reagent():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._reagent")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Reagent):
            self._reagent = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._reagent to {type(output)}")
    
    @hybrid_property
    def reagentrole(self):
        return self._reagentrole

    @reagentrole.setter
    def reagentrole(self, value):
        from backend.validators.pydant import PydReagentRole
        match value:
            case str():
                output = ReagentRole.query(name=value, limit=1)
            case dict():
                output = ReagentRole.query_or_create(**value)
            case PydReagentRole():
                output = value.to_sql(update=False)
            case ReagentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._reagentrole")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ReagentRole):
            self._reagentrole = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._reagentrole to {type(output)}")

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the SQL object of this class might go by.

        :return: list of alias names for this junction model.
        :rtype: List[str]
        """
        return super().aliases + ["reagentreagentroleassociation"]


class EquipmentRole(BaseClass):
    """
    Represents an equipment role that can be associated with procedure types and equipment instances.

    :ivar id: Primary key identifier for the equipment role
    :vartype id: int
    :ivar name: Name of the role
    :vartype name: str
    :ivar equipmentroleproceduretypeassociation: Associations to procedure types
    :vartype equipmentroleproceduretypeassociation: list[ProcedureTypeEquipmentRoleAssociation]
    :ivar _proceduretype: Association proxy to procedure types
    :vartype _proceduretype: list[ProcedureType]
    :ivar equipmentroleequipmentassociation: Associations to equipment instances
    :vartype equipmentroleequipmentassociation: list[EquipmentRoleEquipmentAssociation]
    :ivar _equipment: Association proxy to equipment objects
    :vartype _equipment: list[Equipment]
    """

    id = Column(INTEGER, primary_key=True)  #: Role id, primary key
    name = Column(String(32), nullable=False, unique=True)  #: Common name

    equipmentroleproceduretypeassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="_equipmentrole",
        cascade="all, delete-orphan",
    )  #: relation to SubmissionTypes

    _proceduretype = association_proxy("equipmentroleproceduretypeassociation", "_proceduretype",
                                       creator=lambda proceduretype: ProcedureTypeEquipmentRoleAssociation(proceduretype=proceduretype))
    
    equipmentroleequipmentassociation = relationship(
        "EquipmentRoleEquipmentAssociation",
        back_populates="_equipmentrole",
        cascade="all, delete-orphan",
    )

    _equipment = association_proxy("equipmentroleequipmentassociation", "_equipment",
                                    creator=lambda equipment: EquipmentRoleEquipmentAssociation(equipment=equipment))
    
    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for reagent and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        equipment = kwargs.pop('equipment', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                # fallback: store in misc_info if setter fails
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipment
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                logger.error(f"Couldn't set equipment to {equipment} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def equipment(self) -> List[Equipment]:
        return self._equipment
    
    @equipment.setter
    def equipment(self, value: List[Equipment | str | dict]):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.equipmentroleequipmentassociation if assoc.equipment.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.equipment.name for eq in self.equipmentroleequipmentassociation]}")
                        output = EquipmentRoleEquipmentAssociation(equipment=item, equipmentrole=self)
                case dict():
                    output = EquipmentRoleEquipmentAssociation(equipment=item, equipmentrole=self, **{k: v for k, v in item.items() if k not in ['name', 'equipment', "equipmentrole"]})
                case EquipmentRoleEquipmentAssociation():
                    output = item
                case Equipment():
                    output = EquipmentRoleEquipmentAssociation(equipment=item, equipmentrole=self)
                case _:
                    logger.error(f"Unmatched value {item} to {self.__class__.__qualname__}._equipment")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, EquipmentRoleEquipmentAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Can't add item {output} to {self.__class__.__qualname__}._equipment")
                continue
        self.equipmentroleequipmentassociation = list_

    @hybrid_property
    def proceduretype(self) -> List[ProcedureType]:
        return self._proceduretype  

    @proceduretype.setter
    def proceduretype(self, value: List[ProcedureType | str | dict]):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                # NOTE: A string is assumed to be an existing association
                case str():
                    try:
                        output = next((assoc for assoc in self.equipmentroleproceduretypeassociation if assoc.proceduretype.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.proceduretype.name for eq in self.equipmentroleproceduretypeassociation]}")
                        output = ProcedureTypeEquipmentRoleAssociation(proceduretype=item, equipmentrole=self)
                case dict():
                    output = ProcedureTypeEquipmentRoleAssociation(proceduretype=item, equipmentrole=self, **{k: v for k, v in item.items() if k not in ['proceduretype', 'equipmentrole', 'name']})
                case ProcedureType():
                    output = ProcedureTypeEquipmentRoleAssociation(proceduretype=item, equipmentrole=self)
                case ProcedureTypeEquipmentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value type: {item} for {self.__class__.__qualname__}._proceduretype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcedureTypeEquipmentRoleAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Can't add {output} to {self.__class__.__qualname__}._proceduretype")
                continue
        self.equipmentroleproceduretypeassociation = list_

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[EquipmentRole, bool]:
        """
        Find an EquipmentRole by kwargs or create a new one.

        :param kwargs: Attributes used to query or set on the EquipmentRole.
        :type kwargs: dict
        :return: Tuple of (EquipmentRole instance, created flag).
        :rtype: Tuple[EquipmentRole, bool]
        """
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            setattr(instance, k, v)
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              id: int | None = None,
              limit: int = 0,
              **kwargs
              ) -> EquipmentRole | List[EquipmentRole]:
        """
        Lookup equipment roles.

        :param name: EquipmentRole name. Defaults to None.
        :type name: str | None
        :param id: EquipmentRole id. Defaults to None.
        :type id: int | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: EquipmentRole or list of EquipmentRole objects matching filter.
        :rtype: EquipmentRole | List[EquipmentRole]
        """
        query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)


class Equipment(BaseClass, LogMixin):
    """
    Represents a concrete equipment asset.

    :ivar id: Primary key identifier for equipment
    :vartype id: int
    :ivar name: Equipment name
    :vartype name: str
    :ivar manufacturer: Manufacturer name
    :vartype manufacturer: str
    :ivar ref: Reference code
    :vartype ref: str
    :ivar serial_number: Serial number
    :vartype serial_number: str
    :ivar _nickname: Equipment nickname
    :vartype _nickname: str
    :ivar asset_number: Asset number identifier
    :vartype asset_number: str
    :ivar _calibration_date: Date of last calibration
    :vartype _calibration_date: datetime|None
    :ivar equipmentprocedureassociation: Procedure associations
    :vartype equipmentprocedureassociation: list[ProcedureEquipmentAssociation]
    :ivar _procedure: Association proxy to Procedure objects
    :vartype _procedure: list[Procedure]
    :ivar equipmentequipmentroleassociation: Role associations for this equipment
    :vartype equipmentequipmentroleassociation: list[EquipmentRoleEquipmentAssociation]
    :ivar _equipmentrole: Association proxy to EquipmentRole objects
    :vartype _equipmentrole: list[EquipmentRole]
    """

    id = Column(INTEGER, primary_key=True)  #: id, primary key
    name = Column(String(64), nullable=False, unique=True)  #: equipment name
    manufacturer = Column(String(32))
    ref = Column(String(16))
    serial_number = Column(String(16))
    _nickname = Column(String(64))  #: equipment nickname
    asset_number = Column(String(16))  #: Given asset number (corpo nickname if you will)
    _calibration_date = Column(TIMESTAMP)

    equipmentprocedureassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="_equipment",
        cascade="all, delete-orphan",
    )  #: Association with BasicRun

    _procedure = association_proxy("equipmentprocedureassociation", "_procedure",
                                   creator=lambda procedure: ProcedureEquipmentAssociation(procedure=procedure))  #: proxy to equipmentprocedureassociation.procedure

    equipmentequipmentroleassociation = relationship(
        "EquipmentRoleEquipmentAssociation",
        back_populates="_equipment",
        cascade="all, delete-orphan",
    )

    _equipmentrole = association_proxy("equipmentequipmentroleassociation", "_equipmentrole",
                                       creator=lambda equipmentrole: EquipmentRoleEquipmentAssociation(equipmentrole=equipmentrole))  #: proxy to equipmentroleassociation.equipmentrole

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for reagent and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        procedure = kwargs.pop('procedure', None)
        equipmentrole = kwargs.pop('equipment', None)
        nickname = kwargs.pop('nickname', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipmentrole
        if equipmentrole is not None:
            try:
                self.equipment = equipmentrole
            except Exception:
                logger.error(f"Couldn't set equipmentrole to {equipmentrole} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve nickname
        try:
            self.nickname = nickname
        except Exception:
            logger.error(f"Couldn't set nickname to {nickname} for {self.__class__.__qualname__} with name {self.name}")
            
    @hybrid_property
    def equipmentrole(self) -> List[EquipmentRole]:
        return self._equipmentrole
    
    @equipmentrole.setter
    def equipmentrole(self, value: List[dict | str | EquipmentRole]):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.equipmentequipmentroleassociation if assoc.equipmentrole.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.equipmentrole.name for eq in self.equipmentequipmentroleassociation]}")
                        output = EquipmentRoleEquipmentAssociation(equipmentrole=item, equipment=self)
                case dict():
                    output = EquipmentRoleEquipmentAssociation(equipmentrole=item, equipment=self, **{k: v for k, v in item.items() if k not in ['equipment', 'equipmentrole', 'name']})
                case EquipmentRoleEquipmentAssociation():
                    output = item
                case EquipmentRole():
                    output = EquipmentRoleEquipmentAssociation(equipmentrole=item, equipment=self)
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipmentrole")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, EquipmentRoleEquipmentAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._equipmentrole")
        self.equipmentequipmentroleassociation = list_

    @hybrid_property
    def procedure(self) -> List[Procedure]:
        return self._procedure

    @procedure.setter
    def procedure(self, value: List[Procedure | str | dict]):
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    try:
                        output = next((assoc for assoc in self.equipmentprocedureassociation if assoc.procedure.name==item))
                    except StopIteration:
                        logger.error(f"Couldn't find {item} in {[eq.procedure.name for eq in self.equipmentprocedureassociation]}")
                        output = ProcedureEquipmentAssociation(procedure=item, equipment=self)
                case dict():
                    output = ProcedureEquipmentAssociation(procedure=item, equipment=self, **{k: v for k, v in item.items() if k not in ['name', 'procedure', 'equipment']})
                case Procedure():
                    output = ProcedureEquipmentAssociation(procedure=item, equipment=self)
                case ProcedureEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._procedure")
                    continue
            if isinstance(output, ProcedureEquipmentAssociation):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._procedure")
        self.equipmentprocedureassociation = list_

    @hybrid_property
    def nickname(self) -> str:
        return self._nickname or self.name
                            
    @nickname.setter
    def nickname(self, value: str|None):
        if value is None or value.lower() in ["", "na", "n/a"]:
            self._nickname = self.name
        else:
            self._nickname = value

    @hybrid_property
    def calibration_date(self):
        return self._calibration_date or datetime(year=2000, month=1, day=1, hour=0, minute=0, second=0, tzinfo=timezone)
    
    @calibration_date.setter
    def calibration_date(self, value):
        match value:
            case datetime() | date():
                output = value
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}.expiry")
        output = datetime.combine(output, datetime.min.time())
        value = output.replace(tzinfo=timezone)
        self._calibration_date = value

    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              nickname: str | None = None,
              asset_number: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> Equipment | List[Equipment]:
        """
        Lookup equipment by id, name, nickname, or asset number.

        :param id: Equipment id. Defaults to None.
        :type id: int | None
        :param name: Equipment name. Defaults to None.
        :type name: str | None
        :param nickname: Equipment nickname. Defaults to None.
        :type nickname: str | None
        :param asset_number: Equipment asset number. Defaults to None.
        :type asset_number: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: Equipment or list of Equipment matching filter.
        :rtype: Equipment | List[Equipment]
        """
        query = cls.__database_session__.query(cls)
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match nickname:
            case str():
                query = query.filter(cls.nickname == nickname)
                limit = 1
            case _:
                pass
        match asset_number:
            case str():
                query = query.filter(cls.asset_number == asset_number)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)
    
    @classmethod
    def manufacturer_regex(cls) -> re.Pattern:
        """
        Create a regex to determine tip manufacturer from a reference string.

        :return: compiled regular expression for tip manufacturers.
        :rtype: re.Pattern
        """
        return re.compile(r"""
                          (?P<PHAC>50\d{5}$)|
                          (?P<HC>HC-\d{6}$)|
                          (?P<Beckman>[^\d][A-Z0-9]{6}$)|
                          (?P<Axygen>[A-Z]{3}-\d{2}-[A-Z]-[A-Z]$)|
                          (?P<Labcon>\d{4}-\d{3}-\d{3}-\d$)""",
                          re.VERBOSE)


class EquipmentRoleEquipmentAssociation(BaseClass):
    """
    Junction table linking equipment roles, equipment assets, and processes.

    :ivar equipmentrole_id: Foreign key to EquipmentRole
    :vartype equipmentrole_id: int
    :ivar equipment_id: Foreign key to Equipment
    :vartype equipment_id: int
    :ivar _equipmentrole: Related EquipmentRole object
    :vartype _equipmentrole: EquipmentRole
    :ivar _equipment: Related Equipment object
    :vartype _equipment: Equipment
    :ivar _process: Related Process objects
    :vartype _process: list[Process]
    """
    
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id", ondelete="CASCADE"), primary_key=True)  #: id of associated reagent
    equipment_id = Column(INTEGER, ForeignKey("_equipment.id", ondelete="RESTRICT"), primary_key=True)  #: id of associated procedure

    _equipmentrole = relationship("EquipmentRole",
                                 back_populates="equipmentroleequipmentassociation")  #: associated procedure

    _equipment = relationship("Equipment",
                             back_populates="equipmentequipmentroleassociation")  #: associated procedure

    _process = relationship("Process", secondary=equipmentroleequipmentassociation_process,
                           back_populates="_equipmentroleequipmentassociation")  #: associated procedure

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        process = kwargs.pop('process', None)
        equipmentrole = kwargs.pop('equipmentrole', None)
        equipment = kwargs.pop('equipment', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve process
        if process is not None:
            try:
                self.process = process
            except Exception:
                logger.error(f"Couldn't set process to {process} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipmentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                logger.error(f"Couldn't set equipmentrole to {equipmentrole} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipment
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                logger.error(f"Couldn't set equipment to {equipment} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def name(self):
        try:
            equipment = self.equipment.name
        except AttributeError:
            equipment = "Unassigned Equipment"
        try:
            equipmentrole = self.equipmentrole.name
        except AttributeError:
            equipmentrole = "Unassigned EquipmentRole"
        return f"{equipmentrole}->{equipment}"

    @name.expression
    def name(cls):
        equipmentrole_subquery = (
            select(EquipmentRole.name)
            .where(EquipmentRole.id==cls.equipmentrole_id)
            .correlate(cls)
            .scalar_subquery()
        )
        equipment_subquery = (
            select(Equipment.name)
            .where(Equipment.id==cls.equipment_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return equipmentrole_subquery + "->" + equipment_subquery
    
    @hybrid_property
    def equipment(self):
        return self._equipment

    @equipment.setter
    def equipment(self, value):
        from backend.validators.pydant import PydEquipment
        match value:
            case str():
                output = Equipment.query(name=value, limit=1)              
            case dict():
                output = Equipment.query_or_create(**value)
            case PydEquipment():
                output = value.to_sql(update=False)
            case Equipment():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._equipment")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Equipment):
            self._equipment = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._equipment to {type(output)}")
    
    @hybrid_property
    def equipmentrole(self):
        """
        Return the equipment roles assigned to this equipment.

        :return: list of EquipmentRole objects associated with this equipment.
        :rtype: List[EquipmentRole]
        """
        return self._equipmentrole

    @equipmentrole.setter
    def equipmentrole(self, value):
        """
        Set equipment roles for this equipment from flexible input types.

        Accepts string names, dictionaries, Pydantic models, or EquipmentRole instances.

        :param value: Equipment role data or instance to assign.
        :type value: str | dict | PydEquipmentRole | EquipmentRole | list
        :return: None
        """
        from backend.validators.pydant import PydEquipmentRole
        match value:
            case str():
                output = EquipmentRole.query(name=value, limit=1)
            case dict():
                output = EquipmentRole.query_or_create(**value)
            case PydEquipmentRole():
                output = value.to_sql(update=False)
            case EquipmentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._equipmentrole")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, EquipmentRole):
            self._equipmentrole = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._equipmentrole to {value}")
        
    @hybrid_property
    def process(self):
        return self._process

    @process.setter
    def process(self, value):
        from backend.validators.pydant import PydProcess
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Process.query(name=item, limit=1)
                case dict():
                    output = Process.query_or_create(**item)
                case PydProcess():
                    output = item.to_sql(update=False)
                case Process():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._process")
                    return
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Process):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Can't add item {type(output)} to {self.__class__.__qualname__}._process")
                continue
        self._process = list_

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the SQL object of this class might go by.

        :return: list of alias names for this junction model.
        :rtype: List[str]
        """
        return super().aliases + ["equipmentequipmentroleassociation"]
    
    @classmethod
    @setup_lookup
    def query(cls,
              equipment: str | Equipment | None = None,
              equipmentrole: str | EquipmentRole | None = None,
              process: str | Process | None = None,
              limit: int = 0,
              **kwargs) -> EquipmentRoleEquipmentAssociation | List[EquipmentRoleEquipmentAssociation]:
        """
        Lookup equipment role associations by equipment, role, or process.

        :param equipment: Equipment name or object. Defaults to None.
        :type equipment: str | Equipment | None
        :param equipmentrole: EquipmentRole name or object. Defaults to None.
        :type equipmentrole: str | EquipmentRole | None
        :param process: Process name or object. Defaults to None.
        :type process: str | Process | None
        :param limit: Maximum number of results to return (0=all). Defaults to 0.
        :type limit: int
        :return: EquipmentRoleEquipmentAssociation or list matching filter.
        :rtype: EquipmentRoleEquipmentAssociation | List[EquipmentRoleEquipmentAssociation]
        """
        query = cls.__database_session__.query(cls)
        match equipment:
            case str():
                equipment = Equipment.query(name=equipment)
                query = query.filter(cls._equipment == equipment)
            case Equipment():
                query = query.filter(cls._equipment == equipment)
            case _:
                pass
        match equipmentrole:
            case str():
                equipmentrole = EquipmentRole.query(name=equipmentrole)
                query = query.filter(cls._equipmentrole == equipmentrole)
            case EquipmentRole():
                query = query.filter(cls._equipmentrole == equipmentrole)
            case _:
                pass
        match process:
            case str():
                process = Process.query(name=process)
                query = query.filter(cls._process == process)
            case Process():
                query = query.filter(cls._process == process)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)


class Process(BaseClass):
    """
    Represents a method that can be performed by equipment during a procedure.

    :ivar id: Primary key identifier for the process
    :vartype id: int
    :ivar name: Unique process name
    :vartype name: str
    :ivar _tips: Related tips for the process
    :vartype _tips: list[Tips]
    :ivar _processversion: Related process versions
    :vartype _processversion: list[ProcessVersion]
    :ivar _equipmentroleequipmentassociation: Equipment-role associations for this process
    :vartype _equipmentroleequipmentassociation: list[EquipmentRoleEquipmentAssociation]
    """

    id = Column(INTEGER, primary_key=True)  #: Process id, primary key
    name = Column(String(64), nullable=False, unique=True)  #: Process name
    _tips = relationship("Tips", back_populates='_process',
                        secondary=process_tips)  #: relation to KitType

    _processversion = relationship("ProcessVersion", back_populates="_process")  #: relation to KitType

    _equipmentroleequipmentassociation = relationship(
        "EquipmentRoleEquipmentAssociation", 
        secondary=equipmentroleequipmentassociation_process, 
        back_populates="_process")
        
    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        processversion = kwargs.pop('processversion', None)
        equipmentroleequipmentassociation = kwargs.pop('equipmentroleequipmentassociation', None)
        tips = kwargs.pop('tips', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve processversion
        if processversion is not None:
            try:
                self.processversion = processversion
            except Exception:
                logger.error(f"Couldn't set processversion to {processversion} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipmentroleequipmentassociation
        if equipmentroleequipmentassociation is not None:
            try:
                self.equipmentroleequipmentassociation = equipmentroleequipmentassociation
            except Exception:
                logger.error(f"Couldn't set equipmentroleequipmentassociation to {equipmentroleequipmentassociation} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve tips
        if tips is not None:
            try:
                self.tips = tips
            except Exception:
                logger.error(f"Couldn't set tips to {tips} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def equipmentroleequipmentassociation(self):
        return self._equipmentroleequipmentassociation

    @equipmentroleequipmentassociation.setter
    def equipmentroleequipmentassociation(self, value):
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case EquipmentRoleEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._equipmentroleequipmentassociation")
                    continue
            if isinstance(output, EquipmentRoleEquipmentAssociation):
                list_.append(output)
            else:
                logger.error(f"Could not add {output} to {self.__class__.__qualname__}._equipmentroleequipmentassociation")
        # assign to the correct private attribute for equipment-role<->equipment associations
        self._equipmentroleequipmentassociation = list_
    
    @hybrid_property
    def processversion(self):
        """
        Return the list of process versions associated with this process.

        :return: list of ProcessVersion objects for this process.
        :rtype: list[ProcessVersion]
        """
        return self._processversion

    @processversion.setter
    def processversion(self, value):
        """
        Set process versions for this process from flexible input types.

        Accepts string names, dicts, Pydantic models, or ProcessVersion instances.

        :param value: Process version data or instance to assign.
        :type value: str | dict | PydProcessVersion | ProcessVersion | list | None
        :return: None
        """
        from backend.validators.pydant import PydProcessVersion
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ProcessVersion.query(name=item, limit=1)
                case dict():
                    output = ProcessVersion.query_or_create(**item)
                case PydProcessVersion():
                    output = item.to_sql(update=False)
                case ProcessVersion():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._processversion")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcessVersion):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._processversion")
        self._processversion = list_

    @hybrid_property
    def tips(self):
        """
        Return the list of tip types used in this process.

        :return: list of Tips objects for this process.
        :rtype: list[Tips]
        """
        return self._tips

    @tips.setter
    def tips(self, value):
        """
        Set tip types for this process from flexible input types.

        Accepts string names, dicts, Pydantic models, or Tips instances.

        :param value: Tips data or instance to assign.
        :type value: str | dict | PydTips | Tips | list | None
        :return: None
        """
        from backend.validators.pydant import PydTips
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Tips.query(name=item, limit=1)
                case dict():
                    output = Tips.query_or_create(**item)
                case PydTips():
                    output = item.to_sql(update=False)
                case Tips():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._tips")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Tips):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._tips")
        self._tips = list_

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              id: int | None = None,
              proceduretype: str | ProcedureType | None = None,
              equipmentrole: str | EquipmentRole | None = None,
              limit: int = 0,
              **kwargs) -> Process | List[Process]:
        """
        Lookup processes by name, ID, procedure type, or equipment role.

        :param name: Process name. Defaults to None.
        :type name: str | None
        :param id: Process id. Defaults to None.
        :type id: int | None
        :param proceduretype: ProcedureType name or object. Defaults to None.
        :type proceduretype: str | ProcedureType | None
        :param equipmentrole: EquipmentRole name or object. Defaults to None.
        :type equipmentrole: str | EquipmentRole | None
        :param limit: Maximum number of results to return (0=all). Defaults to 0.
        :type limit: int
        :return: Process or list of processes matching filter.
        :rtype: Process | List[Process]
        """
        query = cls.__database_session__.query(cls)
        match proceduretype:
            case str():
                proceduretype = ProcedureType.query(name=proceduretype)
                query = query.filter(cls.proceduretype.contains(proceduretype))
            case ProcedureType():
                query = query.filter(cls.proceduretype.contains(proceduretype))
            case _:
                pass
        match equipmentrole:
            case str():
                equipmentrole = EquipmentRole.query(name=equipmentrole)
                query = query.filter(cls.equipmentrole.contains(equipmentrole))
            case EquipmentRole():
                query = query.filter(cls.equipmentrole.contains(equipmentrole))
            case _:
                pass
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match id:
            case int():
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)
    
    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        """
        super().save()

    @property
    def details_dict(self) -> dict:
        output = super().details_dict
        output['processversion'] = [item.details_dict for item in self.processversion]
        tips = flatten_list([tipslot for tipslot in [tips.tipslot for tips in self.tips]])
        output['tips'] = [tipslot.details_dict for tipslot in tips]
        return output


class ProcessVersion(BaseClass):
    """
    Represents a version of a process, including verification date and active status.

    :ivar id: Primary key identifier for the process version
    :vartype id: int
    :ivar version: Numeric version value
    :vartype version: float
    :ivar _date_verified: Timestamp when this version was verified
    :vartype _date_verified: datetime|None
    :ivar project: Project associated with this version
    :vartype project: str
    :ivar _active: Active flag stored as an integer
    :vartype _active: int
    :ivar _process: Related Process object
    :vartype _process: Process
    :ivar process_id: Foreign key to Process
    :vartype process_id: int
    :ivar procedureequipmentassociation: Equipment usage associations
    :vartype procedureequipmentassociation: list[ProcedureEquipmentAssociation]
    """

    id = Column(INTEGER, primary_key=True)  #: Process id, primary key
    version = Column(FLOAT(2), default=1.00)  #: Version number
    _date_verified = Column(TIMESTAMP)  #: Date this version was deemed worthy
    project = Column(String(128))  #: Name of the project this belonds to.
    _active = Column(INTEGER, default=1)  #: Is this version in use?
    _process = relationship("Process", back_populates="_processversion")  #: relation to Process
    process_id = Column(INTEGER, ForeignKey("_process.id", ondelete="SET NULL",
                                            name="fk_version_process_id"))
    procedureequipmentassociation = relationship("ProcedureEquipmentAssociation",
                                                 back_populates='_processversion', cascade="all, delete-orphan")  #: relation to RunEquipmentAssociation

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        process = kwargs.pop('process', None)
        active = kwargs.pop('active', None)
        date_verified = kwargs.pop('date_verified', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve process
        if process is not None:
            try:
                self.process = process
            except Exception:
                logger.error(f"Couldn't set process to {process} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve active
        if active is not None:
            try:
                self.active = active
            except Exception:
                logger.error(f"Couldn't set active to {active} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve date_verified
        if date_verified is not None:
            try:
                self.date_verified = date_verified
            except Exception:
                logger.error(f"Couldn't set date_verified to {date_verified} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def date_verified(self):
        return self._date_verified if self._date_verified else None
    
    @date_verified.setter
    def date_verified(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.min.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}._date_verified")
        value = output.replace(tzinfo=timezone)
        self._date_verified = value

    @hybrid_property
    def process(self):
        """
        Return the parent process for this version.

        :return: Process object associated with this version.
        :rtype: Process
        """
        return self._process

    @process.setter
    def process(self, value):
        """
        Set the parent process for this version from flexible input types.

        Accepts string names, dicts, Pydantic models, or Process instances.

        :param value: Process data or instance to assign.
        :type value: str | dict | PydProcess | Process | None
        :return: None
        """
        from backend.validators.pydant import PydProcess
        match value:
            case str():
                output = Process.query(name=value, limit=1)
            case dict():
                output = Process.query_or_create(**value)
            case PydProcess():
                output = value.to_sql(update=False)
            case Process():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._process")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Process):
            self._process = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._process to {type(output)}")
    
    @hybrid_property
    def name(self) -> str:
        if self.process is None:
            return f"Unassigned - v{str(self.version)}"
        return f"{self.process.name} - v{str(self.version)}"

    @name.expression
    def name(cls):
        process_subquery = (
            select(Process.name)
            .where(Process.id==cls.process_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return process_subquery + " - v" + cast(cls.version, String)

    @name.setter
    def name(self, value):
        process, version = value.split(" - v")
        self.process = process.strip()
        self.version = float(version.strip())

    @hybrid_property
    def active(self):
        return bool(self._active)

    @active.setter
    def active(self, value):
        match value:
            case int():
                output = value
            case bool():
                output = int(value)
            case str():
                if value.lower() in ["false", "0", "no", "off"]:
                    output = 0
                elif value.lower() in ["true", "1", "yes", "on"]:
                    output = 1
                else:
                    raise ValueError(f"Cannot convert string {value} to boolean for {self.lot}.active")
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}.active")
        self._active = output

    @property
    def details_dict(self) -> dict:
        output = super().details_dict
        output['name'] = self.name
        if not output['project']:
            output['project'] = ""
        output['tips'] = flatten_list(
            [[lot.details_dict for lot in tips.tipslot if bool(lot.active)] for tips in self.process.tips])
        return output

    @classmethod
    def query(cls,
              version: str | float | None = None,
              name: str | None = None,
              limit: int = 0,
              active: bool | int | None = None,
              **kwargs) -> ProcessVersion | List[ProcessVersion]:
        """
        Lookup process versions by version, name, or active status.

        :param version: Process version number or string. Defaults to None.
        :type version: str | float | None
        :param name: Process version name. Defaults to None.
        :type name: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :param active: Active flag to filter versions. Defaults to None.
        :type active: bool | int | None
        :return: ProcessVersion or list of ProcessVersion objects matching filter.
        :rtype: ProcessVersion | List[ProcessVersion]
        """
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
            case _:
                pass
        match version:
            case str() | float():
                query = query.filter(cls.version == float(version))
            case _:
                pass
        if active is not None:
            query = query.filter(cls._active == int(active))
        return cls.execute_query(query=query, limit=limit)

    
class Tips(BaseClass):
    """
    Represents a tip type used during a process.

    :ivar id: Primary key identifier for tip type
    :vartype id: int
    :ivar _tipslot: Related tip lots
    :vartype _tipslot: list[TipsLot]
    :ivar manufacturer: Tip manufacturer name
    :vartype manufacturer: str
    :ivar capacity: Volume capacity in microliters
    :vartype capacity: int
    :ivar ref: Tip reference code
    :vartype ref: str
    :ivar _cost_per_tip: Cost per tip
    :vartype _cost_per_tip: float
    :ivar _process: Related Process objects
    :vartype _process: list[Process]
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _tipslot = relationship("TipsLot", back_populates="_tips", cascade="all, delete-orphan")  #: concrete instance of this tip type
    manufacturer = Column(String(64))  #: Name of manufacturer
    capacity = Column(INTEGER)  #: How many uL the tip can hold.
    ref = Column(String(64))  #: tip reference number
    _cost_per_tip = Column(FLOAT(2))  #: cost per tip in CAD
    _process = relationship("Process", back_populates="_tips", secondary=process_tips)  #: Associated process

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        process = kwargs.pop('process', None)
        tipslot = kwargs.pop('tipslot', None)
        cost_per_tip = kwargs.pop('cost_per_tip', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve process
        if process is not None:
            try:
                self.process = process
            except Exception:
                logger.error(f"Couldn't set process to {process} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve tipslot
        if tipslot is not None:
            try:
                self.tipslot = tipslot
            except Exception:
                logger.error(f"Couldn't set tipslot to {tipslot} for {self.__class__.__qualname__} with name {self.name}")
        try:
            self.cost_per_tip = cost_per_tip
        except Exception:
            logger.error(f"Couldn't set cost_per_tip to {cost_per_tip} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def cost_per_tip(self):
        """
        Get the cost per individual tip.

        Returns 0.00 if cost is not set or is negative.

        :return: Cost per tip in currency units.
        :rtype: float
        """
        return self._cost_per_tip if self._cost_per_tip else 0.00
    
    @cost_per_tip.setter
    def cost_per_tip(self, value):
        """
        Set the cost per individual tip from flexible input types.

        Accepts int, float, or string representations of numeric cost values.

        :param value: Cost per tip, negative values converted to 0.00.
        :type value: int | float | str | None
        :return: None
        """
        if value is None or value < 0:
            value = 0.00
        match value:
            case int() | float():
                output = float(value)
            case str():
                try:
                    output = float(value)
                except ValueError:
                    logger.error(f"Could not convert {value} to float for {self.__class__.__qualname__}.cost_per_tip")
                    return
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}.cost_per_tip")
                return
        self._cost_per_tip = output

    @hybrid_property
    def process(self):
        """
        Get the processes associated with these tips.

        :return: list of Process objects using these tips.
        :rtype: list[Process]
        """
        return self._process

    @process.setter
    def process(self, value):
        """
        Set processes for these tips from flexible input types.

        Accepts string names, dicts, Pydantic models, or Process instances.

        :param value: Process data or instance to assign.
        :type value: str | dict | PydProcess | Process | list | None
        :return: None
        """
        from backend.validators.pydant import PydProcess
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Process.query(name=item, limit=1)
                case dict():
                    output = Process.query_or_create(**item)
                case PydProcess():
                    output = item.to_sql(update=False)
                case Process():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._process")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Process):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._process")
        self._process = list_
    
    @hybrid_property
    def tipslot(self):
        """
        Get the tip lots available for this tip type.

        :return: list of TipsLot objects representing specific lots of these tips.
        :rtype: list[TipsLot]
        """
        return self._tipslot

    @tipslot.setter
    def tipslot(self, value):
        """
        Set tip lots for this tip type from flexible input types.

        Accepts string names, dicts, Pydantic models, or TipsLot instances.

        :param value: TipsLot data or instance to assign.
        :type value: str | dict | PydTipsLot | TipsLot | list
        :return: None
        """
        from backend.validators.pydant import PydTipsLot
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = TipsLot.query(name=item, limit=1)
                case dict():
                    output = TipsLot.query_or_create(**item)
                case PydTipsLot():
                    output = item.to_sql(update=False)
                case TipsLot():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._tipslot")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, TipsLot):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._tipslot")
        self._tipslot = list_

    @hybrid_property
    def name(self):
        return f"{self.manufacturer} - {self.ref}({self.capacity}uL)"

    @name.expression
    def name(cls):
        return func.concat(cls.manufacturer, ' - ', cls.ref, "(", cast(cls.capacity, String), "uL)")

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              manufacturer: str | None = None,
              capacity: str | None = None,
              ref: str | None = None,
              limit: int = 0,
              **kwargs) -> Tips | List[Tips]:
        """
        Lookup tip types by name, manufacturer, capacity, or reference.

        :param name: Tip type display name. Defaults to None.
        :type name: str | None
        :param manufacturer: Tip manufacturer name. Defaults to None.
        :type manufacturer: str | None
        :param capacity: Tip capacity string. Defaults to None.
        :type capacity: str | None
        :param ref: Tip reference code. Defaults to None.
        :type ref: str | None
        :param limit: Maximum number of results to return (0 = all). Defaults to 0.
        :type limit: int
        :return: Tips or list of Tips matching filter.
        :rtype: Tips | List[Tips]
        """
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match manufacturer:
            case str():
                query = query.filter(cls.manufacturer == manufacturer)
            case _:
                pass
        match capacity:
            case int():
                query = query.filter(cls.capacity == capacity)
            case _:
                pass
        match ref:
            case str():
                query = query.filter(cls.ref == ref)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        """
        super().save()

    
class TipsLot(BaseClass, LogMixin):
    """
    Represents a specific lot of tips with expiry and active state.

    :ivar id: Primary key identifier for the tip lot
    :vartype id: int
    :ivar _tips: Parent tip type
    :vartype _tips: Tips
    :ivar tips_id: Foreign key to parent tips
    :vartype tips_id: int
    :ivar lot: Unique lot number
    :vartype lot: str
    :ivar _expiry: Expiry timestamp for this lot
    :vartype _expiry: datetime|None
    :ivar _active: Active state flag stored as integer
    :vartype _active: int
    :ivar _procedureequipmenttipslotassociation: Related procedure-equipment-tipslot associations
    :vartype _procedureequipmenttipslotassociation: list[ProcedureEquipmentTipslotAssociation]
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _tips = relationship("Tips", back_populates="_tipslot")  #: joined parent tip type
    tips_id = Column(INTEGER, ForeignKey("_tips.id", ondelete='SET NULL',
                                         name="fk_tips_id"))  #: id of parent tip type
    lot = Column(String(64), nullable=False)  #: lot number
    _expiry = Column(TIMESTAMP)  #: date of expiry
    _active = Column(INTEGER, default=1)  #: whether or not these tips are currently in use.
    _procedureequipmenttipslotassociation = relationship("ProcedureEquipmentTipslotAssociation", 
                                                 back_populates="_tipslot", 
                                                 cascade="all, delete-orphan"
                                                 )

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        tips = kwargs.pop('tips', None)
        expiry = kwargs.pop('expiry', None)
        active = kwargs.pop('active', None)
        procedureequipmenttipslotassociation = kwargs.pop('procedureequipmenttipslotassociation', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve tips
        if tips is not None:
            try:
                self.tips = tips
            except Exception:
                logger.error(f"Couldn't set tips to {tips} for {self.__class__.__qualname__} with name {self.name}")
        if procedureequipmenttipslotassociation is not None:
            try:
                self.procedureequipmenttipslotassociation = procedureequipmenttipslotassociation
            except Exception:
                logger.error(f"Couldn't set procedureequipmenttipslotassociation to {procedureequipmenttipslotassociation} for {self.__class__.__qualname__} with name {self.name}")
        if expiry is not None:
            try:
                self.expiry = expiry
            except Exception:
                logger.error(f"Couldn't set expiry to {expiry} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve active
        if active is not None:
            try:
                self.active = active
            except Exception:
                logger.error(f"Couldn't set active to {active} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def expiry(self) -> str:
        """
        Get the expiry date for this tip lot.

        :return: expiry timestamp, or None if not set.
        :rtype: datetime | None
        """
        return self._expiry if self._expiry else datetime(year=2099, month=12, day=31, hour=23, minute=59, second=59, tzinfo=timezone)

    @expiry.setter
    def expiry(self, value):
        """
        Set the expiry date for this tip lot from various input formats.

        Accepts datetime, date, timestamp integer, or date string.

        :param value: Expiry date value in various formats.
        :type value: datetime | date | int | str
        :return: None
        """
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.max.time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value['value']} for {self.__class__.__qualname__}.expiry")
        value = output.replace(tzinfo=timezone)
        self._expiry = value
    
    @hybrid_property
    def tips(self):
        """
        Get the tip type for this lot of tips.

        :return: Tips object representing the tip type.
        :rtype: Tips
        """
        return self._tips

    @tips.setter
    def tips(self, value):
        """
        Set the tip type for this lot from flexible input types.

        Accepts string names, dicts, Pydantic models, or Tips instances.

        :param value: Tips data or instance to assign.
        :type value: str | dict | PydTips | Tips | None
        :return: None
        """
        from backend.validators.pydant import PydTips
        match value:
            case str():
                output = Tips.query(name=value, limit=1)
            case dict():
                output = Tips.query_or_create(**value)
            case PydTips():
                output = value.to_sql(update=False)
            case Tips():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._tips")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Tips):
            self._tips = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._tips to {type(output)}")
    
    @hybrid_property
    def procedureequipmenttipslotassociation(self):
        """
        Get the procedure-equipment-tipslot associations for this tip lot.

        :return: list of ProcedureEquipmentTipslotAssociation objects.
        :rtype: list[ProcedureEquipmentTipslotAssociation]
        """
        return self._procedureequipmenttipslotassociation

    @procedureequipmenttipslotassociation.setter
    def procedureequipmenttipslotassociation(self, value):
        """
        Set procedure-equipment-tipslot associations for this tip lot.

        Accepts dict or ProcedureEquipmentTipslotAssociation instances.

        :param value: Association data or instance to assign.
        :type value: dict | ProcedureEquipmentTipslotAssociation | ProcedureEquipmentAssociation | list | None
        :return: None
        """
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case dict():
                    output = ProcedureEquipmentTipslotAssociation.query_or_create(**item)
                case ProcedureEquipmentTipslotAssociation():
                    output = item
                case ProcedureEquipmentAssociation():
                    output = ProcedureEquipmentTipslotAssociation(
                        procedureequipmentassociation = item,
                        tipslot = self
                    )
                case _:
                    logger.error(f"Unmatched value {type(value)} for {self.__class__.__name__}._procedureequipmenttipslotassociation")
                    return
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcedureEquipmentTipslotAssociation):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__name__}._procedureequipmenttipslotassociation")
        self._procedureequipmenttipslotassociation = list_

    @property
    def capacity(self) -> str:
        return f"{self.tips.capacity}uL" if self.tips and self.tips.capacity else "Unknown capacity"

    @hybrid_property
    def name(self) -> str:
        try:
            manufacturer = self.tips.manufacturer
        except AttributeError:
            manufacturer = "Unassigned manufacturer"
        try:
            ref = self.tips.ref
        except AttributeError:
            ref = "Unassigned manufacturer"
        return f"{manufacturer} - {ref} - {self.lot}"

    @name.expression
    def name(cls):
        tipsman_subquery = (
            select(Tips.manufacturer)
            .where(Tips.id==cls.tips_id)
            .correlate(cls)
            .scalar_subquery()
        )
        tipsref_subquery = (
            select(Tips.ref)
            .where(Tips.id==cls.tips_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return tipsman_subquery + " - " + tipsref_subquery + " - " + cast(cls.lot, String)

    @hybrid_property
    def active(self):
        """
        Get the active status flag for this tip lot.

        :return: True if tips are active, False otherwise.
        :rtype: bool
        """
        return bool(self._active)

    @active.setter
    def active(self, value):
        """
        Set the active status flag for this tip lot from flexible input types.

        Accepts int, bool, or string representations of boolean values.

        :param value: Active status value.
        :type value: int | bool | str
        :return: None
        :raises ValueError: If string value cannot be converted to boolean.
        :raises TypeError: If type is not supported.
        """
        match value:
            case int():
                output = value
            case bool():
                output = int(value)
            case str():
                if value.lower() in ["false", "0", "no", "off"]:
                    output = 0
                elif value.lower() in ["true", "1", "yes", "on"]:
                    output = 1
                else:
                    raise ValueError(f"Cannot convert string {value} to boolean for {self.__class__.__qualname__}._active")
            case _:
                raise TypeError(f"Unsupported type: {type(value)} for {self.__class__.__qualname__}._active")
        self._active = output

    @classmethod
    def query(cls,
              name: str | None = None,
              manufacturer: str | None = None,
              ref: str | None = None,
              lot: str | None = None,
              limit: int = 0,
              **kwargs) -> Tips | List[Tips]:
        """
        Lookup tips by name, manufacturer, reference, or lot.

        :param name: Tips name. Defaults to None.
        :type name: str | None
        :param manufacturer: Tips manufacturer. Defaults to None.
        :type manufacturer: str | None
        :param ref: Tips reference. Defaults to None.
        :type ref: str | None
        :param lot: Tips lot number. Defaults to None.
        :type lot: str | None
        :param limit: Maximum number of results to return (0=all). Defaults to 0.
        :type limit: int
        :return: Tips or list of Tips matching filter.
        :rtype: Tips | List[Tips]
        """
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        if manufacturer is not None and ref is not None:
            manufacturer = None
        match manufacturer:
            case str():
                query = query.join(Tips).filter(Tips.manufacturer == manufacturer)
            case _:
                pass
        match ref:
            case str():
                query = query.join(Tips).filter(Tips.ref == ref)
            case _:
                pass
        match lot:
            case str():
                query = query.filter(cls.lot == lot)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)
    
    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        """
        super().save()

    @property
    def details_dict(self) -> dict:
        output = super().details_dict
        output['name'] = self.name
        return output


class ProcedureEquipmentTipslotAssociation(BaseClass):
    """
    Junction model linking a procedure-equipment association to a specific tipslot.

    :ivar procedure_id: Foreign key to procedure.
    :vartype procedure_id: int
    :ivar equipment_id: Foreign key to equipment.
    :vartype equipment_id: int
    :ivar equipmentrole_id: Foreign key to equipment role.
    :vartype equipmentrole_id: int
    :ivar tipslot_id: Foreign key to tip lot.
    :vartype tipslot_id: int
    :ivar _procedureequipmentassociation: Related ProcedureEquipmentAssociation object.
    :vartype _procedureequipmentassociation: ProcedureEquipmentAssociation
    :ivar _tipslot: Related TipsLot object.
    :vartype _tipslot: TipsLot
    """

    procedure_id = Column(
        INTEGER,
        # ForeignKey("_procedureequipmentassociation.procedure_id"),
        primary_key=True
    )
    equipment_id = Column(
        INTEGER,
        # ForeignKey("_procedureequipmentassociation.equipment_id"),
        primary_key=True
    )
    equipmentrole_id = Column(
        INTEGER,
        # ForeignKey("_procedureequipmentassociation.equipmentrole_id"),
        primary_key=True
    )
    tipslot_id = Column(
        INTEGER,
        ForeignKey("_tipslot.id", ondelete="CASCADE"),
        primary_key=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["equipment_id", "procedure_id", "equipmentrole_id"],
            [
                "_procedureequipmentassociation.equipment_id",
                "_procedureequipmentassociation.procedure_id",
                "_procedureequipmentassociation.equipmentrole_id",
            ],
            ondelete="CASCADE",
        ),
    )

    # Relationships
    _procedureequipmentassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="_procedureequipmenttipslotassociation",
        primaryjoin=lambda: and_(
            ProcedureEquipmentTipslotAssociation.procedure_id == ProcedureEquipmentAssociation.procedure_id,
            ProcedureEquipmentTipslotAssociation.equipment_id == ProcedureEquipmentAssociation.equipment_id,
            ProcedureEquipmentTipslotAssociation.equipmentrole_id == ProcedureEquipmentAssociation.equipmentrole_id,
        ),
        foreign_keys=[
            procedure_id,
            equipment_id,
            equipmentrole_id
        ]
    )

    _tipslot = relationship(
        "TipsLot",
        back_populates="_procedureequipmenttipslotassociation",
        foreign_keys=[tipslot_id]
    )

    @hybrid_property
    def procedureequipmentassociation(self):
        """
        Get the parent procedure-equipment association for this tipslot binding.

        :return: ProcedureEquipmentAssociation object linking procedure and equipment.
        :rtype: ProcedureEquipmentAssociation
        """
        return self._procedureequipmentassociation

    @procedureequipmentassociation.setter
    def procedureequipmentassociation(self, value):
        """
        Assign the related ProcedureEquipmentAssociation for this tipslot binding.

        :param value: ProcedureEquipmentAssociation data or instance.
        :type value: dict | ProcedureEquipmentAssociation
        :return: None
        """
        match value:
            case dict():
                output = ProcedureEquipmentAssociation.query_or_create(**value)
            case ProcedureEquipmentAssociation():
                output = value
            case _:
                logger.error(f"Unmatched value {type(value)} for {self.__class__.__name__}._procedureequipmentassociation")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureEquipmentAssociation):
            self._procedureequipmentassociation = output
        else:
            logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._procedureequipmentassociation")

    @hybrid_property
    def tipslot(self):
        """
        Get the tip lot assigned to this procedure-equipment association.

        :return: TipsLot object representing specific tip lot.
        :rtype: TipsLot
        """
        return self._tipslot

    @tipslot.setter
    def tipslot(self, value):
        """
        Set the tip lot for this procedure-equipment association from flexible input types.

        Accepts string names, dicts, Pydantic models, or TipsLot instances.

        :param value: TipsLot data or instance to assign.
        :type value: str | dict | PydTipsLot | TipsLot | None
        :return: None
        """
        from backend.validators.pydant.concrete import PydTipsLot
        match value:
            case str():
                output = TipsLot.query(name=value, limit=1)
            case dict():
                output = TipsLot.query_or_create(**value)
            case PydTipsLot():
                output = value.to_sql(update=False)
            case TipsLot():
                output = value
            case _:
                logger.error(f"Unmatched value {type(value)} for {self.__class__.__qualname__}._tipslot")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, TipsLot):
            self._tipslot = output
        else:
            logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._tipslot")

    @hybrid_property
    def name(self) -> str:
        try:
            procedure = self.procedureequipmentassociation.procedure.name
        except AttributeError as e:
            procedure = "Unknown Procedure"
        try:
            equipmentrole = self.procedureequipmentassociation.equipmentrole.name
        except AttributeError as e:
            equipmentrole = "Unknown EquipmentRole"
        try:
            tipslot = self.tipslot.name
        except AttributeError as e:
            tipslot = "Unknown TipsLot"
        return f"{procedure}({equipmentrole})->{tipslot}"

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        from backend.validators.pydant import PydProcessVersion
        procedureequipmentassociation = kwargs.pop('procedureequipmentassociation', None)
        tipslot = kwargs.pop('tipslot', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve procedureequipmentassociation
        if procedureequipmentassociation is not None:
            try:
                self.procedureequipmentassociation = procedureequipmentassociation
            except Exception:
                logger.error(f"Couldn't set procedureequipmentassociation to {procedureequipmentassociation} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve tipslot
        if tipslot is not None:
            try:
                self.tipslot = tipslot
            except Exception:
                logger.error(f"Couldn't set tipslot to {tipslot} for {self.__class__.__qualname__} with name {self.name}")


class ProcedureEquipmentAssociation(BaseClass):
    """
    Represents equipment usage for a specific procedure, including process version and calibration details.

    :ivar equipment_id: Foreign key to equipment
    :vartype equipment_id: int
    :ivar procedure_id: Foreign key to procedure
    :vartype procedure_id: int
    :ivar equipmentrole_id: Foreign key to equipment role
    :vartype equipmentrole_id: int
    :ivar processversion_id: Foreign key to process version
    :vartype processversion_id: int
    :ivar _start_time: Use start timestamp
    :vartype _start_time: datetime|None
    :ivar _end_time: Use end timestamp
    :vartype _end_time: datetime|None
    :ivar _comment: Optional usage comment
    :vartype _comment: str|None
    :ivar _calibration_date: Calibration timestamp
    :vartype _calibration_date: datetime|None
    :ivar _procedure: Related Procedure object
    :vartype _procedure: Procedure
    :ivar _equipment: Related Equipment object
    :vartype _equipment: Equipment
    :ivar _equipmentrole: Related EquipmentRole object
    :vartype _equipmentrole: EquipmentRole
    :ivar _processversion: Related ProcessVersion object
    :vartype _processversion: ProcessVersion|None
    :ivar _procedureequipmenttipslotassociation: Related ProcedureEquipmentTipslotAssociation objects
    :vartype _procedureequipmenttipslotassociation: list[ProcedureEquipmentTipslotAssociation]
    :ivar _tipslot: Association proxy to tipslot objects
    :vartype _tipslot: list[TipsLot]
    """

    procedure_id = Column(INTEGER, ForeignKey("_procedure.id", ondelete="CASCADE"), primary_key=True)  #: id of associated procedure
    equipment_id = Column(INTEGER, ForeignKey("_equipment.id", ondelete="CASCADE"), primary_key=True)  #: id of associated equipment
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id", ondelete="CASCADE"), primary_key=True)
    processversion_id = Column(INTEGER, ForeignKey("_processversion.id", ondelete="SET NULL",
                                                   name="SEA_Process_id"))  #: Foreign key of process id
    _start_time = Column(TIMESTAMP)  #: start time of equipment use
    _end_time = Column(TIMESTAMP)  #: end time of equipment use
    _comment = Column(String(1024))  #: comments about equipment
    _calibration_date = Column(TIMESTAMP)

    _procedure = relationship(Procedure,
                             back_populates="procedureequipmentassociation")  #: associated procedure

    _equipment = relationship(Equipment, back_populates="equipmentprocedureassociation")  #: associated equipment

    _equipmentrole = relationship(EquipmentRole)

    _processversion = relationship(ProcessVersion, back_populates="procedureequipmentassociation")  #: Associated process version

    _procedureequipmenttipslotassociation = relationship(
        ProcedureEquipmentTipslotAssociation, 
        back_populates="_procedureequipmentassociation", 
        primaryjoin=lambda: and_(
            ProcedureEquipmentAssociation.procedure_id == ProcedureEquipmentTipslotAssociation.procedure_id,
            ProcedureEquipmentAssociation.equipment_id == ProcedureEquipmentTipslotAssociation.equipment_id,
            ProcedureEquipmentAssociation.equipmentrole_id == ProcedureEquipmentTipslotAssociation.equipmentrole_id,
        ),
        foreign_keys=[
            ProcedureEquipmentTipslotAssociation.procedure_id,
            ProcedureEquipmentTipslotAssociation.equipment_id,
            ProcedureEquipmentTipslotAssociation.equipmentrole_id,
        ],
        cascade="all, delete-orphan")
    
    _tipslot = association_proxy("_procedureequipmenttipslotassociation", "_tipslot")

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        procedure = kwargs.pop('procedure', None)
        equipment = kwargs.pop('equipment', None)
        processversion = kwargs.pop('processversion', None)
        equipmentrole = kwargs.pop('equipmentrole', None)
        tipslot = kwargs.pop('tipslot', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                logger.error(f"Couldn't set equipment to {equipment} for {self.__class__.__qualname__} with name {self.name}")
        if processversion is not None:
            try:
                self.processversion = processversion
            except Exception:
                logger.error(f"Couldn't set processversion to {processversion} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                logger.error(f"Couldn't set equipment to {equipment} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve reagentrole
        if tipslot is not None:
            try:
                self.tipslot = tipslot
            except Exception:
                logger.error(f"Couldn't set tipslot to {tipslot} for {self.__class__.__qualname__} with name {self.name}")
    
    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the SQL object of this class might go by.

        :return: list of alias names for this junction model.
        :rtype: List[str]
        """
        return super().aliases + ["equipmentprocedureassociation"]
    
    @hybrid_property
    def tipslot(self):
        """
        Get the tip lots associated with this procedure-equipment use.

        :return: list of TipsLot objects used during this procedure.
        :rtype: list[TipsLot]
        """
        return self._tipslot

    @tipslot.setter
    def tipslot(self, value):
        """
        Set tip lots for this procedure-equipment association from flexible input types.

        Accepts string names, dicts, Pydantic models, or TipsLot instances.

        :param value: TipsLot data or instances to assign.
        :type value: str | dict | PydTipsLot | TipsLot | list
        :return: None
        """
        from backend.validators.pydant.concrete import PydTipsLot
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = TipsLot.query(name=item, limit=1)
                case dict():
                    output = TipsLot.query_or_create(**item)
                case PydTipsLot():
                    output = item.to_sql(update=False)
                case TipsLot():
                    output = item
                case _:
                    logger.error(f"Unmatched value {type(item)} for {self.__class__.__qualname__}._tipslot")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            output = ProcedureEquipmentTipslotAssociation(procedureequipmentassociation=self, tipslot=output)
            if isinstance(output, ProcedureEquipmentTipslotAssociation):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._tipslot")
        self._procedureequipmenttipslotassociation = list_
    
    @hybrid_property
    def equipmentrole(self):
        """
        Get the equipment role used for this procedure-equipment association.

        :return: EquipmentRole object defining the role of the equipment.
        :rtype: EquipmentRole
        """
        return self._equipmentrole

    @equipmentrole.setter
    def equipmentrole(self, value):
        """
        Set the equipment role for this procedure-equipment association from flexible input types.

        Accepts string names, dicts, Pydantic models, or EquipmentRole instances.

        :param value: EquipmentRole data or instance to assign.
        :type value: str | dict | PydEquipmentRole | EquipmentRole
        :return: None
        """
        from backend.validators.pydant import PydEquipmentRole
        match value:
            case str():
                output = EquipmentRole.query(name=value, limit=1)
            case dict():
                output = EquipmentRole.query_or_create(**value)
            case PydEquipmentRole():
                output = value.to_sql(update=False)
            case EquipmentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._equipmentrole.")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, EquipmentRole):
            self._equipmentrole = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._equipmentrole to {type(output)}")
    
    @hybrid_property
    def equipment(self):
        """
        Get the equipment used for this procedure-equipment association.

        :return: Equipment object used during this procedure.
        :rtype: Equipment
        """
        return self._equipment

    @equipment.setter
    def equipment(self, value):
        """
        Set the equipment for this procedure-equipment association from flexible input types.

        Accepts string names, dicts, Pydantic models, or Equipment instances.

        :param value: Equipment data or instance to assign.
        :type value: str | dict | PydEquipment | Equipment
        :return: None
        """
        from backend.validators.pydant import PydEquipment
        match value:
            case str():
                output = Equipment.query(name=value, limit=1)
            case dict():
                output = Equipment.query_or_create(**value)
            case PydEquipment():
                output = value.to_sql(update=False)
            case Equipment():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._equipment")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Equipment):
            self._equipment = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._equipment to {type(output)}")
    
    @hybrid_property
    def procedure(self):
        """
        Get the procedure for this equipment-procedure association.

        :return: Procedure object using this equipment.
        :rtype: Procedure
        """
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        """
        Set the procedure for this equipment association from flexible input types.

        Accepts string names, dicts, Pydantic models, or Procedure instances.

        :param value: Procedure data or instance to assign.
        :type value: str | dict | PydProcedure | Procedure
        :return: None
        """
        from backend.validators.pydant import PydProcedure
        match value:
            case str():
                output = Procedure.query(name=value, limit=1)
            case dict():
                output = Procedure.query_or_create(**value)
            case PydProcedure():
                output = value.to_sql(update=False)
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._procedure")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._procedure to {type(output)}")
    
    @hybrid_property
    def processversion(self):
        """
        Get the process version used for this equipment-procedure activity.

        :return: ProcessVersion object describing the process method used.
        :rtype: ProcessVersion | None
        """
        return self._processversion

    @processversion.setter
    def processversion(self, value):
        """
        Set the process version for this equipment association from flexible input types.

        Accepts string names, dicts, Pydantic models, or ProcessVersion instances.

        :param value: ProcessVersion data or instance to assign.
        :type value: str | dict | PydProcessVersion | ProcessVersion | None
        :return: None
        """
        from backend.validators.pydant import PydProcessVersion
        match value:
            case str():
                output = ProcessVersion.query(name=value, limit=1)
            case dict():
                output = ProcessVersion.query_or_create(**value)
            case PydProcessVersion():
                output = value.to_sql(update=False)
            case ProcessVersion():
                output = value
            case _:
                output = None
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcessVersion):
            self._processversion = output
        else:
            self._processversion = None
    
    @hybrid_property
    def name(self):
        """
        Get the display name for this equipment-procedure association.

        :return: Formatted name combining procedure and equipment names.
        :rtype: str
        """
        try:
            equipment = self.equipment.name
        except AttributeError:
            equipment = "Unassigned Equipment"
        try:
            procedure = self.procedure.name
        except AttributeError:
            procedure = "Unassigned Procedure"
        return f"{procedure}->{equipment}"

    @name.expression
    def name(cls):
        """
        SQL expression for computing the name in database queries.

        :return: SQLAlchemy expression for concatenating procedure and equipment names.
        :rtype: sqlalchemy.sql.elements.BinaryExpression
        """
        procedure_subquery = (
            select(Procedure.name)
            .where(Procedure.id==cls.procedure_id)
            .correlate(cls)
            .scalar_subquery()
        )
        equipment_subquery = (
            select(Equipment.name)
            .where(Equipment.id==cls.equipment_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return procedure_subquery + "->" + equipment_subquery

    @hybrid_property
    def comment(self):
        return self._comment

    def to_pydantic(self) -> PydProcedureEquipmentAssociation:
        """
        Return a pydantic model representation for this association.

        :return: pydantic model representing this procedure-equipment association.
        :rtype: PydProcedureEquipmentAssociation
        """
        from backend.validators.pydant import PydProcedureEquipmentAssociation
        
        output = PydProcedureEquipmentAssociation(**self.details_dict)
        return output
    
    @classmethod
    @setup_lookup
    def query(cls,
              equipment: int | Equipment | None = None,
              procedure: int | Procedure | None = None,
              equipmentrole: str | None = None,
              limit: int = 0, **kwargs) \
            -> Any | List[Any]:
        """
        Lookup procedure-equipment association records.

        :param equipment: The associated equipment of interest. Defaults to None.
        :type equipment: int | Equipment | None
        :param procedure: The associated procedure of interest. Defaults to None.
        :type procedure: int | Procedure | None
        :param equipmentrole: The associated equipment role. Defaults to None.
        :type equipmentrole: str | None
        :param limit: Maximum number of results to return (0=all). Defaults to 0.
        :type limit: int
        :return: ProcedureEquipmentAssociation or list matching filter.
        :rtype: Any | List[Any]
        """
        query: Query = cls.__database_session__.query(cls)
        match equipment:
            case int():
                query = query.filter(cls.equipment_id == equipment)
            case Equipment():
                query = query.filter(cls.equipment == equipment)
            case str():
                query = query.filter(cls._equipment.has(Equipment.name == equipment))
            case _:
                pass
        match procedure:
            case int():
                query = query.filter(cls.procedure_id == procedure)
            case Procedure():
                query = query.filter(cls.procedure == procedure)
            case str():
                query = query.filter(cls._procedure.has(Procedure.name == procedure))
            case _:
                pass
        if equipmentrole is not None:
            query = query.filter(cls.equipmentrole == equipmentrole)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @property
    def details_dict(self) -> dict:
        """
        Produce a detailed dictionary representation of this procedure equipment association.

        :return: Details dictionary containing equipment, role, process version and tipslot metadata.
        :rtype: dict
        """
        output = super().details_dict
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['equipment']}
        output = self.equipment.details_dict
        misc = output.get('misc_info', {})
        output.update(relevant)
        output['misc_info'] = misc
        output['equipment'] = self.equipment.name
        # equipmentrole is optional and may be None (see bug report)
        output['equipmentrole'] = self.equipmentrole.name if self.equipmentrole else ""
        output['processversion'] = self.processversion.name if self.processversion else ""
        output['tipslot'] = [tipslot.name for tipslot in self.tipslot]
        return output


class ProcedureTypeEquipmentRoleAssociation(BaseClass):
    """
    Junction table linking procedure types with equipment roles.

    :ivar equipmentrole_id: Foreign key to equipment role
    :vartype equipmentrole_id: int
    :ivar proceduretype_id: Foreign key to procedure type
    :vartype proceduretype_id: int
    :ivar _static: Static usage flag
    :vartype _static: int
    :ivar _proceduretype: Related ProcedureType object
    :vartype _proceduretype: ProcedureType
    :ivar _equipmentrole: Related EquipmentRole object
    :vartype _equipmentrole: EquipmentRole
    """
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)  #: id of associated equipment
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"), primary_key=True)  #: id of associated procedure
    _always_used = Column(INTEGER, default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?
    _proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypeequipmentroleassociation",
                                 foreign_keys=[proceduretype_id])  #: associated procedure
    _equipmentrole = relationship(EquipmentRole,
                                 back_populates="equipmentroleproceduretypeassociation",
                                 foreign_keys=[equipmentrole_id])  #: associated equipment

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        proceduretype = kwargs.pop('proceduretype', None)
        equipmentrole = kwargs.pop('equipmentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve equipmentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                logger.error(f"Couldn't set equipmentrole to {equipmentrole} for {self.__class__.__qualname__} with name {self.name}")

    @hybrid_property
    def always_used(self):
        return bool(self._always_used)
    
    @always_used.setter
    def always_used(self, value):
        match value:
            case int():
                self._always_used = value
            case bool():
                self._always_used = int(value)
            case str():
                if value.lower() in ['true', '1', 'yes', 'on']:
                    self._always_used = 1
                elif value.lower() in ['false', '0', 'no', 'off']:
                    self._always_used = 0
                else:
                    raise ValueError(f"Cannot convert string {value} to boolean for {self.__class__.__qualname__}._always_used")
            case _:
                raise TypeError(f"Unsupported type {type(value)} for {self.__class__.__qualname__}._always_used")

    @hybrid_property
    def name(self):
        try:
            equipmentrole = self.equipmentrole.name
        except AttributeError:
            equipmentrole= "Unassigned EquipmentRole"
        try:
            proceduretype = self.proceduretype.name
        except AttributeError:
            proceduretype = "Unassigned ProcedureType"
        return f"{proceduretype}->{equipmentrole}"

    @name.expression
    def name(cls):
        proceduretype_subquery = (
            select(ProcedureType.name)
            .where(ProcedureType.id==cls.proceduretype_id)
            .correlate(cls)
            .scalar_subquery()
        )
        equipmentrole_subquery = (
            select(EquipmentRole.name)
            .where(EquipmentRole.id==cls.equipmentrole_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return proceduretype_subquery + "->" + equipmentrole_subquery

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        match value:
            case str():
                output = ProcedureType.query(name=value, limit=1)
            case dict():
                output = ProcedureType.query_or_create(**value)
            case PydProcedureType():
                output = value.to_sql(update=False)
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._proceduretype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._proceduretype to {type(output)}")
    
    @hybrid_property
    def equipmentrole(self):
        return self._equipmentrole

    @equipmentrole.setter
    def equipmentrole(self, value):
        from backend.validators.pydant import PydEquipmentRole
        match value:
            case str():
                output = EquipmentRole.query(name=value, limit=1)
            case dict():
                output = EquipmentRole.query_or_create(**value)
            case PydEquipmentRole():
                output = value.to_sql(update=False)
            case EquipmentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._equipmentrole")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, EquipmentRole):
            self._equipmentrole = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._equipmentrole to {type(output)}")
            
    @classproperty
    def aliases(cls):
        """
        Gets other names the SQL object of this class might go by.

        :return: list of alias names for this association model.
        :rtype: list[str]
        """
        return super().aliases + ['equipmentroleproceduretypeassociation']
    
    @check_authorization
    def save(self):
        """
        Persist this object with authorization enforcement.

        Calls the base class save implementation after authorization succeeds.
        :return: None
        """
        super().save()
    
    @classmethod
    @setup_lookup
    def query(cls,
              proceduretype: str | ProcedureType | None = None,
              equipmentrole: str | EquipmentRole | None = None,
              limit: int = 0,
              **kwargs) -> ProcedureTypeEquipmentRoleAssociation | List[ProcedureTypeEquipmentRoleAssociation]:
        """
        Lookup procedure type / equipment role associations.

        :param proceduretype: ProcedureType name or object. Defaults to None.
        :type proceduretype: str | ProcedureType | None
        :param equipmentrole: EquipmentRole name or object. Defaults to None.
        :type equipmentrole: str | EquipmentRole | None
        :param limit: Maximum number of results to return (0=all). Defaults to 0.
        :type limit: int
        :return: ProcedureTypeEquipmentRoleAssociation or list matching filter.
        :rtype: ProcedureTypeEquipmentRoleAssociation | List[ProcedureTypeEquipmentRoleAssociation]
        """
        query = cls.__database_session__.query(cls)
        match proceduretype:
            case str():
                proceduretype = ProcedureType.query(name=proceduretype)
                query = query.filter(cls._proceduretype == proceduretype)
            case ProcedureType():
                query = query.filter(cls._proceduretype == proceduretype)
            case _:
                pass
        match equipmentrole:
            case str():
                equipmentrole = EquipmentRole.query(name=equipmentrole)
                query = query.filter(cls._equipmentrole == equipmentrole)
            case EquipmentRole():
                query = query.filter(cls._equipmentrole == equipmentrole)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)


class Results(BaseClass):
    """
    Represents result metadata and values for a procedure or sample.

    :ivar id: Primary key identifier for the result
    :vartype id: int
    :ivar _result: JSON payload containing result values
    :vartype _result: dict
    :ivar _date_analyzed: Timestamp when the result was analyzed
    :vartype _date_analyzed: datetime|None
    :ivar procedure_id: Foreign key to parent procedure
    :vartype procedure_id: int
    :ivar _procedure: Parent Procedure object
    :vartype _procedure: Procedure
    :ivar assoc_id: Foreign key to sample association
    :vartype assoc_id: int|None
    :ivar _sampleprocedureassociation: Related ProcedureSampleAssociation object
    :vartype _sampleprocedureassociation: ProcedureSampleAssociation|None
    :ivar _img: Zip archive filename for image storage
    :vartype _img: str|None
    :ivar resultstype_id: Foreign key to ResultsType
    :vartype resultstype_id: int
    :ivar _resultstype: Related ResultsType object
    :vartype _resultstype: ResultsType
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _result = Column(JSON)  #:
    _date_analyzed = Column(TIMESTAMP)
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id", ondelete='SET NULL',
                                              name="fk_RES_procedure_id"))
    _procedure = relationship("Procedure", back_populates="_results")
    assoc_id = Column(INTEGER, ForeignKey("_proceduresampleassociation.id", ondelete='SET NULL',
                                          name="fk_RES_ASSOC_id"))
    _sampleprocedureassociation = relationship("ProcedureSampleAssociation", back_populates="_results")
    _img = Column(String(128))
    _is_sample = Column(INTEGER, default=0)

    resultstype_id = Column(INTEGER, ForeignKey("_resultstype.id", ondelete='SET NULL',
                                              name="fk_RES_resultstype_id"))
    _resultstype = relationship("ResultsType", back_populates="_results")

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        date_analyzed = kwargs.pop('date_analyzed', None)
        procedure = kwargs.pop('procedure', None)
        sampleprocedureassociation = kwargs.pop('sampleprocedureassociation', None)
        image = kwargs.pop('image', None)
        resultstype = kwargs.pop('resultstype', None)
        result = kwargs.pop('result', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                logger.error(f"Couldn't set procedure to {procedure} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve date_analyzed
        if date_analyzed is not None:
            try:
                self.date_analyzed = date_analyzed
            except Exception:
                logger.error(f"Couldn't set date_analyzed to {date_analyzed} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve sampleprocedureassociation
        if sampleprocedureassociation is not None:
            try:
                self.sampleprocedureassociation = sampleprocedureassociation
            except Exception:
                logger.error(f"Couldn't set sampleprocedureassociation to {sampleprocedureassociation} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve image
        if image is not None:
            try:
                self.image = image
            except Exception:
                pass
        # Resolve resultstype
        if resultstype is not None:
            try:
                self.resultstype = resultstype
            except Exception:
                logger.error(f"Couldn't set resultstype to {resultstype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve result
        if result is not None:
            try:
                self.result = result
            except Exception:
                logger.error(f"Couldn't set result to {result} for {self.__class__.__qualname__} with name {self.name}")

    # TODO: Enable query from sample_association in addition to procedure

    @hybrid_property
    def result(self):
        return self._result
    
    @result.setter
    def result(self, value):
        if isinstance(value, str):
            logger.error(f"Got string {value}")
            try:
                value = json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {e}")
        match value:
            case dict():
                self._result = value
            case _:
                logger.error(f"Unmatched value for {self.__class__.__qualname__}._result: {type(value)}")
        
    @hybrid_property
    def name(self):
        try:
            assoc = self.procedure.name
        except AttributeError:
            assoc = "Unassigned Procedure Association"
        try:
            resultstype = self.resultstype.name
        except AttributeError:
            resultstype = "Unassigned ResultsType"
        return f"{assoc} - {resultstype}"
    
    @name.expression
    def name(cls):
        procedure_subquery = (
            select(Procedure.name)
            .where(Procedure.id==cls.procedure_id)
            .correlate(cls)
            .scalar_subquery()
        )
        resultstype_subquery = (
            select(ResultsType.name)
            .where(ResultsType.id==cls.resultstype_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # NOTE: Can't use f strings for this.
        return procedure_subquery + " - " + resultstype_subquery

    @hybrid_property
    def date_analyzed(self):
        return self._date_analyzed if self._date_analyzed else None
    
    @date_analyzed.setter
    def date_analyzed(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime():
                output = value
            case date():
                output = datetime.combine(value, datetime.now().time())
            case int():
                output = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + value - 2)
            case str():
                string = re.sub(r"(_|-)\d(R\d)?$", "", value)
                try:
                    output = dateparse(string)
                except ParserError as e:
                    logger.error(f"Problem parsing date: {e}")
                    try:
                        output = dateparse(string.replace("-", ""))
                    except Exception as e:
                        logger.error(f"Problem with parse fallback: {e}")
                        return value
            case _:
                raise ValueError(f"Unmatched value {value} for {self.__class__.__qualname__}.date_analyzed")
        value = output.replace(tzinfo=timezone)
        self._date_analyzed = output

    @hybrid_property
    def resultstype(self):
        return self._resultstype

    @resultstype.setter
    def resultstype(self, value):
        from backend.validators.pydant import PydResultsType
        match value:
            case str():
                output = ResultsType.query(name=value, limit=1)
            case dict():
                output = ResultsType.query_or_create(**value)
            case PydResultsType():
                output = value.to_sql(update=False)
            case ResultsType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._resultstype")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ResultsType):
            self._resultstype = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._resultstype to {type(output)}")
    
    @hybrid_property
    def procedure(self):
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        match value:
            case str():
                output = Procedure.query(name=value, limit=1)
            case dict():
                output = Procedure.query_or_create(**value)
            case PydProcedure():
                output = value.to_sql(update=False)
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for procedure")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._procedure to {type(output)}")

    @hybrid_property
    def sampleprocedureassociation(self):
        return self._sampleprocedureassociation

    @sampleprocedureassociation.setter
    def sampleprocedureassociation(self, value):
        """
        Input objects will be assumed to be sample only and use self.procedure to set.
        """
        from backend.validators.pydant import PydProcedureSampleAssociation
        from backend.db.models import ProcedureSampleAssociation
        try:
            proc = self.procedure
        except AttributeError as e:
            logger.critical(f"Could not get procedure for setting association.")
            raise e
        match value:
            case str():
                output = ProcedureSampleAssociation.query(sample=value, procedure=proc, limit=1)
            case dict():
                output = ProcedureSampleAssociation.query_or_create(**value)
            case PydProcedureSampleAssociation():
                output = value.to_sql(update=False)
            case ProcedureSampleAssociation():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for {self.__class__.__qualname__}._sampleprocedureassociation")
                return
        if isinstance(output, tuple):
            output = output[0]
        if isinstance(output, ProcedureSampleAssociation):
            self._sampleprocedureassociation = output
            try:
                self.procedure = output.procedure
            except Exception as e:
                logger.error(f"Problem setting procedure from sampleprocedureassociation: {e}")
        else:
            logger.error(f"Could not set {self.__class__.__qualname__}._sampleprocedureassociation to {output} of type {type(output)}")
    
    @property
    def sample_id(self):
        if self.assoc_id:
            try:
                return self.sampleprocedureassociation.sample.sample_id
            except AttributeError:
                return None
        else:
            return None

    @property
    def image(self) -> bytes | None:
        dir = self.__directory_path__.joinpath("submission_imgs.zip")
        if not self._img:
            return None
        try:
            assert dir.exists()
        except AssertionError:
            return None
        with zipfile.ZipFile(dir) as zf:
            with zf.open(self._img) as f:
                return f.read()

    @image.setter
    def image(self, value):
        self._img = value

    @hybrid_property
    def is_sample(self):
        if self._is_sample is not None:
            return bool(self._is_sample)
        else:
            return self.assoc_id is not None
        
    @is_sample.setter
    def is_sample(self, value):
        if value is None:
            value = False
        self._is_sample = int(value)

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs):
        output = super().to_pydantic(pyd_model_name=pyd_model_name, **kwargs)
        if bool(self.sample_id):
            output.sample_id = self.sample_id
            output.sample = self.sampleprocedureassociation.sample.sample_id
        if self.result:
            for k, v in self.result.items():
                setattr(output, k, v)
        return output


class ResultsType(BaseClass):

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), nullable=False, unique=True)
    _info = Column(JSON) #: where to look for procedure information
    _samples = Column(JSON) # where to look for sample information
    _results = relationship("Results", back_populates="_resultstype", cascade="all, delete-orphan")
    _proceduretype = relationship(ProcedureType, back_populates="_resultstype", secondary=proceduretype_resulttype)
    _saved_settings = Column(JSON)

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        results = kwargs.pop('results', None)
        proceduretype = kwargs.pop('proceduretype', None)
        info = kwargs.pop("info", {})
        samples = kwargs.pop("samples", {})
        saved_settings = kwargs.pop("saved_settings", [])
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                # fallback: store in misc_info if setter fails
                logger.error(f"Couldn't set proceduretype to {proceduretype} for {self.__class__.__qualname__} with name {self.name}")
        # Resolve results
        if results is not None:
            try:
                self.results = results
            except Exception:
                logger.error(f"Couldn't set results to {results} for {self.__class__.__qualname__} with name {self.name}")
        self.info = info
        self.samples = samples
        self.saved_settings = saved_settings

    @hybrid_property
    def proceduretype(self):
        return self._proceduretype

    @proceduretype.setter
    def proceduretype(self, value):
        from backend.validators.pydant import PydProcedureType
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = ProcedureType.query(name=item, limit=1)
                case dict():
                    output = ProcedureType.query_or_create(**item)
                case PydProcedureType():
                    output = item.to_sql(update=False)
                case ProcedureType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._proceduretype")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, ProcedureType):
                if output not in list_:
                    list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}._proceduretype")
        self._proceduretype = list_

    @hybrid_property
    def results(self):
        return self._results

    @results.setter
    def results(self, value):
        from backend.validators.pydant import PydResults
        from backend.db.models import Results
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        list_ = []
        for item in value:
            match item:
                case str():
                    output = Results.query(name=item, limit=1)
                case dict():
                    output = Results.query_or_create(**item)
                case PydResults():
                    output = item.to_sql()
                case Results():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for {self.__class__.__qualname__}._results")
                    continue
            if isinstance(output, tuple):
                output = output[0]
            if isinstance(output, Results):
                list_.append(output)
            else:
                logger.error(f"Could not add {type(output)} to {self.__class__.__qualname__}_results")
        self._results = list_

    @hybrid_property
    def info(self) -> dict:
        return self._info
    
    @info.setter
    def info(self, value):
        if isinstance(value, dict):
            self._info = value
        else:
            raise ValueError(f"Unmatched type {type(value)} for {self.__class__.__qualname__}._info")

    @hybrid_property
    def samples(self) -> dict:
        return self._samples
    
    @samples.setter
    def samples(self, value):
        if isinstance(value, dict):
            self._samples = value
        else:
            raise ValueError(f"Unmatched type {type(value)} for {self.__class__.__qualname__}._samples")

    @hybrid_property
    def saved_settings(self):
        return self._saved_settings or []
    
    @saved_settings.setter
    def saved_settings(self, value):
        if isinstance(value, dict):
            self._saved_settings = value
        else:
            raise ValueError(f"Unmatched type {type(value)} for {self.__class__.__qualname__}._saved_settings")

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs) -> BaseModel:
        return super().to_pydantic(pyd_model_name, **kwargs)
