from __future__ import annotations
from pprint import pformat
import logging, re 
from sqlalchemy import Column, String, TIMESTAMP, INTEGER, ForeignKey, Interval, FLOAT, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, Query
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from datetime import date, datetime, timedelta
from dateutil.parser import parse as dateparse, ParserError
from tools import check_authorization, classproperty, setup_lookup, timezone
from typing import List
from .. import BaseClass, LogMixin
from . import ProcedureType, Procedure

logger = logging.getLogger(f"subbmissions.{__name__}")


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
                limit = 1
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


__all__ = ["ReagentRole", "Reagent", "ReagentLot", "ReagentRoleReagentAssociation", "ProcedureTypeReagentRoleAssociation", "ProcedureReagentLotAssociation"]
