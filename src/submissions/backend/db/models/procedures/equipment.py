from __future__ import annotations
from pprint import pformat
import re, logging
from sqlalchemy import Column, ForeignKeyConstraint, String, TIMESTAMP, INTEGER, ForeignKey, FLOAT, and_, cast, func, select, Table
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, Query
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date, datetime
from dateutil.parser import parse as dateparse, ParserError
from tools import check_authorization, setup_lookup, flatten_list, timezone
from typing import List, Any, Tuple, TYPE_CHECKING
from .. import BaseClass, Base, LogMixin
from . import ProcedureType, Procedure
if TYPE_CHECKING:
    from backend.validators.pydant import PydProcedureEquipmentAssociation


logger = logging.getLogger(f"submissions.{__name__}")

# Define the association table instance first
equipmentroleequipmentassociation_process = Table(
    "_equipmentrolequipmentassociation_process",
    Base.metadata,
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
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)


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

    # @classmethod
    # def query_or_create(cls, **kwargs) -> Tuple[EquipmentRole, bool]:
    #     """
    #     Find an EquipmentRole by kwargs or create a new one.

    #     :param kwargs: Attributes used to query or set on the EquipmentRole.
    #     :type kwargs: dict
    #     :return: Tuple of (EquipmentRole instance, created flag).
    #     :rtype: Tuple[EquipmentRole, bool]
    #     """
    #     new = False
    #     disallowed = ['expiry']
    #     sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
    #     instance = cls.query(**sanitized_kwargs)
    #     if not instance or isinstance(instance, list):
    #         instance = cls()
    #         new = True
    #     for k, v in sanitized_kwargs.items():
    #         setattr(instance, k, v)
    #     return instance, new

    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           name: str | None = None,
    #           id: int | None = None,
    #           limit: int = 0,
    #           **kwargs
    #           ) -> EquipmentRole | List[EquipmentRole]:
    #     """
    #     Lookup equipment roles.

    #     :param name: EquipmentRole name. Defaults to None.
    #     :type name: str | None
    #     :param id: EquipmentRole id. Defaults to None.
    #     :type id: int | None
    #     :param limit: Maximum number of results to return (0 = all). Defaults to 0.
    #     :type limit: int
    #     :return: EquipmentRole or list of EquipmentRole objects matching filter.
    #     :rtype: EquipmentRole | List[EquipmentRole]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match id:
    #         case int():
    #             query = query.filter(cls.id == id)
    #             limit = 1
    #         case _:
    #             pass
    #     match name:
    #         case str():
    #             query = query.filter(cls.name == name)
    #             limit = 1
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit)


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

    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           id: int | None = None,
    #           name: str | None = None,
    #           nickname: str | None = None,
    #           asset_number: str | None = None,
    #           limit: int = 0,
    #           **kwargs
    #           ) -> Equipment | List[Equipment]:
    #     """
    #     Lookup equipment by id, name, nickname, or asset number.

    #     :param id: Equipment id. Defaults to None.
    #     :type id: int | None
    #     :param name: Equipment name. Defaults to None.
    #     :type name: str | None
    #     :param nickname: Equipment nickname. Defaults to None.
    #     :type nickname: str | None
    #     :param asset_number: Equipment asset number. Defaults to None.
    #     :type asset_number: str | None
    #     :param limit: Maximum number of results to return (0 = all). Defaults to 0.
    #     :type limit: int
    #     :return: Equipment or list of Equipment matching filter.
    #     :rtype: Equipment | List[Equipment]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match id:
    #         case int():
    #             query = query.filter(cls.id == id)
    #             limit = 1
    #         case _:
    #             pass
    #     match name:
    #         case str():
    #             query = query.filter(cls.name == name)
    #             limit = 1
    #         case _:
    #             pass
    #     match nickname:
    #         case str():
    #             query = query.filter(cls.nickname == nickname)
    #             limit = 1
    #         case _:
    #             pass
    #     match asset_number:
    #         case str():
    #             query = query.filter(cls.asset_number == asset_number)
    #             limit = 1
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit)
    
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
    
    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           equipment: str | Equipment | None = None,
    #           equipmentrole: str | EquipmentRole | None = None,
    #           process: str | Process | None = None,
    #           limit: int = 0,
    #           **kwargs) -> EquipmentRoleEquipmentAssociation | List[EquipmentRoleEquipmentAssociation]:
    #     """
    #     Lookup equipment role associations by equipment, role, or process.

    #     :param equipment: Equipment name or object. Defaults to None.
    #     :type equipment: str | Equipment | None
    #     :param equipmentrole: EquipmentRole name or object. Defaults to None.
    #     :type equipmentrole: str | EquipmentRole | None
    #     :param process: Process name or object. Defaults to None.
    #     :type process: str | Process | None
    #     :param limit: Maximum number of results to return (0=all). Defaults to 0.
    #     :type limit: int
    #     :return: EquipmentRoleEquipmentAssociation or list matching filter.
    #     :rtype: EquipmentRoleEquipmentAssociation | List[EquipmentRoleEquipmentAssociation]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match equipment:
    #         case str():
    #             equipment = Equipment.query(name=equipment)
    #             query = query.filter(cls._equipment == equipment)
    #         case Equipment():
    #             query = query.filter(cls._equipment == equipment)
    #         case _:
    #             pass
    #     match equipmentrole:
    #         case str():
    #             equipmentrole = EquipmentRole.query(name=equipmentrole)
    #             query = query.filter(cls._equipmentrole == equipmentrole)
    #         case EquipmentRole():
    #             query = query.filter(cls._equipmentrole == equipmentrole)
    #         case _:
    #             pass
    #     match process:
    #         case str():
    #             process = Process.query(name=process)
    #             query = query.filter(cls._process == process)
    #         case Process():
    #             query = query.filter(cls._process == process)
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit, **kwargs)


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

    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           name: str | None = None,
    #           id: int | None = None,
    #           proceduretype: str | ProcedureType | None = None,
    #           equipmentrole: str | EquipmentRole | None = None,
    #           limit: int = 0,
    #           **kwargs) -> Process | List[Process]:
    #     """
    #     Lookup processes by name, ID, procedure type, or equipment role.

    #     :param name: Process name. Defaults to None.
    #     :type name: str | None
    #     :param id: Process id. Defaults to None.
    #     :type id: int | None
    #     :param proceduretype: ProcedureType name or object. Defaults to None.
    #     :type proceduretype: str | ProcedureType | None
    #     :param equipmentrole: EquipmentRole name or object. Defaults to None.
    #     :type equipmentrole: str | EquipmentRole | None
    #     :param limit: Maximum number of results to return (0=all). Defaults to 0.
    #     :type limit: int
    #     :return: Process or list of processes matching filter.
    #     :rtype: Process | List[Process]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match proceduretype:
    #         case str():
    #             proceduretype = ProcedureType.query(name=proceduretype)
    #             query = query.filter(cls.proceduretype.contains(proceduretype))
    #         case ProcedureType():
    #             query = query.filter(cls.proceduretype.contains(proceduretype))
    #         case _:
    #             pass
    #     match equipmentrole:
    #         case str():
    #             equipmentrole = EquipmentRole.query(name=equipmentrole)
    #             query = query.filter(cls.equipmentrole.contains(equipmentrole))
    #         case EquipmentRole():
    #             query = query.filter(cls.equipmentrole.contains(equipmentrole))
    #         case _:
    #             pass
    #     match name:
    #         case str():
    #             query = query.filter(cls.name == name)
    #             limit = 1
    #         case _:
    #             pass
    #     match id:
    #         case int():
    #             query = query.filter(cls.id == id)
    #             limit = 1
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit)
    
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

    # @classmethod
    # def query(cls,
    #           version: str | float | None = None,
    #           name: str | None = None,
    #           limit: int = 0,
    #           active: bool | int | None = None,
    #           **kwargs) -> ProcessVersion | List[ProcessVersion]:
    #     """
    #     Lookup process versions by version, name, or active status.

    #     :param version: Process version number or string. Defaults to None.
    #     :type version: str | float | None
    #     :param name: Process version name. Defaults to None.
    #     :type name: str | None
    #     :param limit: Maximum number of results to return (0 = all). Defaults to 0.
    #     :type limit: int
    #     :param active: Active flag to filter versions. Defaults to None.
    #     :type active: bool | int | None
    #     :return: ProcessVersion or list of ProcessVersion objects matching filter.
    #     :rtype: ProcessVersion | List[ProcessVersion]
    #     """
    #     query: Query = cls.__database_session__.query(cls)
    #     match name:
    #         case str():
    #             query = query.filter(cls.name == name)
    #         case _:
    #             pass
    #     match version:
    #         case str() | float():
    #             query = query.filter(cls.version == float(version))
    #         case _:
    #             pass
    #     if active is not None:
    #         query = query.filter(cls._active == int(active))
    #     return cls.execute_query(query=query, limit=limit)

    
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

    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           name: str | None = None,
    #           manufacturer: str | None = None,
    #           capacity: str | None = None,
    #           ref: str | None = None,
    #           limit: int = 0,
    #           **kwargs) -> Tips | List[Tips]:
    #     """
    #     Lookup tip types by name, manufacturer, capacity, or reference.

    #     :param name: Tip type display name. Defaults to None.
    #     :type name: str | None
    #     :param manufacturer: Tip manufacturer name. Defaults to None.
    #     :type manufacturer: str | None
    #     :param capacity: Tip capacity string. Defaults to None.
    #     :type capacity: str | None
    #     :param ref: Tip reference code. Defaults to None.
    #     :type ref: str | None
    #     :param limit: Maximum number of results to return (0 = all). Defaults to 0.
    #     :type limit: int
    #     :return: Tips or list of Tips matching filter.
    #     :rtype: Tips | List[Tips]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match name:
    #         case str():
    #             query = query.filter(cls.name == name)
    #             limit = 1
    #         case _:
    #             pass
    #     match manufacturer:
    #         case str():
    #             query = query.filter(cls.manufacturer == manufacturer)
    #         case _:
    #             pass
    #     match capacity:
    #         case int():
    #             query = query.filter(cls.capacity == capacity)
    #         case _:
    #             pass
    #     match ref:
    #         case str():
    #             query = query.filter(cls.ref == ref)
    #             limit = 1
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit)

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

    
    # @classmethod
    # def query(cls,
    #           name: str | None = None,
    #           manufacturer: str | None = None,
    #           ref: str | None = None,
    #           lot: str | None = None,
    #           limit: int = 0,
    #           **kwargs) -> Tips | List[Tips]:
    #     """
    #     Lookup tips by name, manufacturer, reference, or lot.

    #     :param name: Tips name. Defaults to None.
    #     :type name: str | None
    #     :param manufacturer: Tips manufacturer. Defaults to None.
    #     :type manufacturer: str | None
    #     :param ref: Tips reference. Defaults to None.
    #     :type ref: str | None
    #     :param lot: Tips lot number. Defaults to None.
    #     :type lot: str | None
    #     :param limit: Maximum number of results to return (0=all). Defaults to 0.
    #     :type limit: int
    #     :return: Tips or list of Tips matching filter.
    #     :rtype: Tips | List[Tips]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match name:
    #         case str():
    #             query = query.filter(cls.name == name)
    #             limit = 1
    #         case _:
    #             pass
    #     if manufacturer is not None and ref is not None:
    #         manufacturer = None
    #     match manufacturer:
    #         case str():
    #             query = query.join(Tips).filter(Tips.manufacturer == manufacturer)
    #         case _:
    #             pass
    #     match ref:
    #         case str():
    #             query = query.join(Tips).filter(Tips.ref == ref)
    #         case _:
    #             pass
    #     match lot:
    #         case str():
    #             query = query.filter(cls.lot == lot)
    #             limit = 1
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit)
    
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
    
    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           equipment: int | Equipment | None = None,
    #           procedure: int | Procedure | None = None,
    #           equipmentrole: str | None = None,
    #           limit: int = 0, **kwargs) \
    #         -> Any | List[Any]:
    #     """
    #     Lookup procedure-equipment association records.

    #     :param equipment: The associated equipment of interest. Defaults to None.
    #     :type equipment: int | Equipment | None
    #     :param procedure: The associated procedure of interest. Defaults to None.
    #     :type procedure: int | Procedure | None
    #     :param equipmentrole: The associated equipment role. Defaults to None.
    #     :type equipmentrole: str | None
    #     :param limit: Maximum number of results to return (0=all). Defaults to 0.
    #     :type limit: int
    #     :return: ProcedureEquipmentAssociation or list matching filter.
    #     :rtype: Any | List[Any]
    #     """
    #     query: Query = cls.__database_session__.query(cls)
    #     match equipment:
    #         case int():
    #             query = query.filter(cls.equipment_id == equipment)
    #         case Equipment():
    #             query = query.filter(cls.equipment == equipment)
    #         case str():
    #             query = query.filter(cls._equipment.has(Equipment.name == equipment))
    #         case _:
    #             pass
    #     match procedure:
    #         case int():
    #             query = query.filter(cls.procedure_id == procedure)
    #         case Procedure():
    #             query = query.filter(cls.procedure == procedure)
    #         case str():
    #             query = query.filter(cls._procedure.has(Procedure.name == procedure))
    #         case _:
    #             pass
    #     if equipmentrole is not None:
    #         query = query.filter(cls.equipmentrole == equipmentrole)
    #     return cls.execute_query(query=query, limit=limit, **kwargs)

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
    
    # @classmethod
    # @setup_lookup
    # def query(cls,
    #           proceduretype: str | ProcedureType | None = None,
    #           equipmentrole: str | EquipmentRole | None = None,
    #           limit: int = 0,
    #           **kwargs) -> ProcedureTypeEquipmentRoleAssociation | List[ProcedureTypeEquipmentRoleAssociation]:
    #     """
    #     Lookup procedure type / equipment role associations.

    #     :param proceduretype: ProcedureType name or object. Defaults to None.
    #     :type proceduretype: str | ProcedureType | None
    #     :param equipmentrole: EquipmentRole name or object. Defaults to None.
    #     :type equipmentrole: str | EquipmentRole | None
    #     :param limit: Maximum number of results to return (0=all). Defaults to 0.
    #     :type limit: int
    #     :return: ProcedureTypeEquipmentRoleAssociation or list matching filter.
    #     :rtype: ProcedureTypeEquipmentRoleAssociation | List[ProcedureTypeEquipmentRoleAssociation]
    #     """
    #     query = cls.__database_session__.query(cls)
    #     match proceduretype:
    #         case str():
    #             proceduretype = ProcedureType.query(name=proceduretype)
    #             query = query.filter(cls._proceduretype == proceduretype)
    #         case ProcedureType():
    #             query = query.filter(cls._proceduretype == proceduretype)
    #         case _:
    #             pass
    #     match equipmentrole:
    #         case str():
    #             equipmentrole = EquipmentRole.query(name=equipmentrole)
    #             query = query.filter(cls._equipmentrole == equipmentrole)
    #         case EquipmentRole():
    #             query = query.filter(cls._equipmentrole == equipmentrole)
    #         case _:
    #             pass
    #     return cls.execute_query(query=query, limit=limit, **kwargs)


__all__ = ["EquipmentRole", "Equipment", "EquipmentRoleEquipmentAssociation", "Process", "ProcessVersion", 
           "Tips", "TipsLot", "ProcedureEquipmentTipslotAssociation", "ProcedureEquipmentAssociation", "ProcedureTypeEquipmentRoleAssociation",
           "equipmentroleequipmentassociation_process", "process_tips"]
