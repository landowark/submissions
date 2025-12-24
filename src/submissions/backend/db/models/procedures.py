"""
All kittype and reagent related models
"""
from __future__ import annotations
from pprint import pformat
import zipfile, logging, re, numpy as np, sys
from operator import itemgetter
from sqlalchemy import Column, ForeignKeyConstraint, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, and_, cast, extract, func, select, case
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, Query, declared_attr, aliased
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date, datetime, time, timedelta
from dateutil.parser import parse as dateparse, ParserError
from tools import check_authorization, setup_lookup, check_regex_match, jinja_template_loading, flatten_list, timezone
from typing import List, Literal, Generator, Any, Tuple, TYPE_CHECKING
from . import BaseClass, ClientLab, LogMixin
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from inspect import getattr_static

if TYPE_CHECKING:
    from backend.db.models.submissions import Run, ProcedureSampleAssociation
    from backend.validators.pydant import PydSample, PydEquipment

logger = logging.getLogger(f'submissions.{__name__}')

proceduretype_resulttype = Table(
    "_proceduretype_resulttype",
    BaseClass.__base__.metadata,
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    Column("resultstype_id", INTEGER, ForeignKey("_resultstype.id")),
    extend_existing=True
)

equipment_process = Table(
    "_equipment_process",
    BaseClass.__base__.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    extend_existing=True
)

process_tips = Table(
    "_process_tips",
    BaseClass.__base__.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)

# procedure_equipment_tipslot = Table(
#     "_procedure_equipment_tipslot",
#     BaseClass.__base__.metadata,
#     Column("procedure_id", INTEGER, ForeignKey("_procedureequipmentassociation.procedure_id")),
#     Column("equipment_id", INTEGER, ForeignKey("_procedureequipmentassociation.equipment_id")),
#     Column("equipmentrole_id", INTEGER, ForeignKey("_procedureequipmentassociation.equipmentrole_id")),
#     Column("tipslot_id", INTEGER, ForeignKey("_tipslot.id")),
#     extend_existing=True
# )

submissiontype_proceduretype = Table(
    "_submissiontype_proceduretype",
    BaseClass.__base__.metadata,
    Column("submissiontype_id", INTEGER, ForeignKey("_submissiontype.id")),
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    extend_existing=True
)


class ReagentRole(BaseClass):
    """
    Base of reagent type abstract
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), unique=True)  #: name of reagentrole reagent plays
    
    reagentroleproceduretypeassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    _proceduretype = association_proxy("reagentroleproceduretypeassociation", "_proceduretype")

    reagentrolereagentassociation = relationship(
        "ReagentRoleReagentAssociation",
        back_populates="_reagentrole",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    _reagent = association_proxy("reagentrolereagentassociation", "_reagent")

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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if reagent is not None:
            try:
                self.reagent = reagent
            except Exception:
                try:
                    self._misc_info.update({'reagent': reagent})
                except Exception:
                    pass
        
    @hybrid_property
    def proceduretype(self) -> List[ProcedureType]:
        return self._proceduretype
    
    @proceduretype.setter
    def proceduretype(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureTypeReagentRoleAssociation(proceduretype=item['name'], reagentrole=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureTypeReagentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for {self}._proceduretype")
                    continue
            if isinstance(output, ProcedureTypeReagentRoleAssociation):
                if output not in self.reagentroleproceduretypeassociation:
                    # self.__database_session__.add(output)
                    self.reagentroleproceduretypeassociation.append(output)
            else:
                logger.error(f"Could not add {item} to _proceduretype")

    @hybrid_property
    def reagent(self) -> List[Reagent]:
        return self._reagent
    
    @reagent.setter
    def reagent(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ReagentRoleReagentAssociation(reagent=item['name'], reagentrole=self, **{k: v for k, v in item.items() if k != 'name'})
                case ReagentRoleReagentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for {self}._reagent")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ReagentRoleReagentAssociation):
                if output not in self.reagentrolereagentassociation:
                    self.reagentrolereagentassociation.append(output)
            else:
                logger.error(f"Could not add {item} to _reagent")

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

        Args:
            id (id | None, optional): Id of the object. Defaults to None.
            name (str | None, optional): Reagent type name. Defaults to None.
            proceduretype (ProcedureType | None, optional): Procedure the type of interest belongs to. Defaults to None.
            reagent (Reagent | str | None, optional): Concrete instance of the type of interest. Defaults to None.
            limit (int, optional): maxmimum number of results to return (0 = all). Defaults to 0.

        Raises:
            ValueError: Raised if only kittype or reagent, not both, given.

        Returns:
            ReagentRole|List[ReagentRole]: ReagentRole or list of ReagentRoles matching filter.
        """
        query: Query = cls.__database_session__.query(cls)
        # if (proceduretype is not None and reagent is None) or (reagent is not None and proceduretype is None):
        #     raise ValueError("Cannot filter without both reagent and kittype type.")
        # elif proceduretype is None and reagent is None:
        #     pass
        # else:
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
            # assert reagent.role
            # # NOTE: Get all roles common to the reagent and the kittype.
            # result = set(proceduretype.reagentrole).intersection(reagent.role)
            # return next((item for item in result), None)
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
        super().save()

    def get_reagents(self, proceduretype: str | ProcedureType | None = None):
        if not proceduretype:
            return [reagent.to_pydantic() for reagent in self.reagent]
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        assoc = next((item for item in self.reagentroleproceduretypeassociation if item.proceduretype == proceduretype),
                     None)
        reagents = [reagent for reagent in self.reagent]
        if assoc:
            last_used = Reagent.query(name=assoc.last_used)
            if isinstance(last_used, list):
                last_used = None
            if last_used:
                reagents.insert(0, reagents.pop(reagents.index(last_used)))
        return [reagent.to_pydantic(reagentrole=self.name) for reagent in reagents]

    
class Reagent(BaseClass, LogMixin):
    """
    Concrete reagent instance
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    _eol_ext = Column(Interval())  #: extension of life interval
    name = Column(String(64), unique=True)  #: reagent name
    cost_per_ml = Column(FLOAT(2))  #: amount a millilitre of reagent costs
    _reagentlot = relationship("ReagentLot", back_populates="_reagent", cascade="all, delete-orphan")  #: joined parent reagent type

    reagentreagentroleassociation = relationship(
        "ReagentRoleReagentAssociation",
        back_populates="_reagent",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    
    _reagentrole = association_proxy("reagentreagentroleassociation", "_reagentrole")  #: Association proxy to KitTypeReagentTypeAssociation

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
        for item in value:
            match item:
                case dict():
                    output = ReagentRoleReagentAssociation(reagentrole=item['name'], reagent=self, **{k: v for k, v in item.items() if k != 'name'})
                case ReagentRoleReagentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for {self}._reagentrole")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ReagentRoleReagentAssociation):
                if output not in self.reagentreagentroleassociation:
                    self.reagentreagentroleassociation.append(output)
            else:
                logger.error(f"Could not add {item} to _reagentrole")

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
        for item in value:
            match item:
                case str():
                    output = ReagentLot.query(name=item, limit=1)
                case dict():
                    output = ReagentLot.query_or_create(**item)
                case PydReagentLot():
                    output = item.to_sql()
                case ReagentLot():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for _reagentlot")
                    continue
            if isinstance(output, ReagentLot):
                self._reagentlot.append(output)
            else:
                logger.error(f"Could not add {item} to _reagentlot")

    @classmethod
    @declared_attr
    def searchables(cls):
        return [dict(label="Lot", field="lot")]

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

        Args:
            id (int | None, optional): reagent id number
            reagentrole (str | models.ReagentType | None, optional): Reagent type. Defaults to None.
            lot (str | None, optional): Reagent lot number. Defaults to None.
            name (str | None, optional): Reagent name. Defaults to None.
            limit (int, optional): limit of results returned. Defaults to 0.

        Returns:
            models.Reagent | List[models.Reagent]: reagent or list of reagents matching filter.
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

    # def details_dict(self, reagentrole: str | None = None, **kwargs):
    #     output = super().details_dict()
    #     if reagentrole:
    #         output['reagentrole'] = reagentrole
    #     else:
    #         output['reagentrole'] = self.reagentrole
    #     return output

    @property
    def lot_dicts(self):
        return [dict(name=self.name, lot=lot.lot, expiry=lot.expiry + self.eol_ext) for lot in self.reagentlot]


class ReagentLot(BaseClass):

    id = Column(INTEGER, primary_key=True)  #: primary key
    lot = Column(String(64), unique=True)  #: lot number of reagent
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

    _procedure = association_proxy("reagentlotprocedureassociation", "procedure")  #: Association proxy to ClientSubmissionSampleAssociation

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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'reagent': reagent})
                except Exception:
                    pass
        # Resolve procedure
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        else:
            self._procedure = []
        if expiry is not None:
            try:
                self.expiry = expiry
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'expiry': expiry})
                except Exception:
                    pass
        # Resolve reagentrole
        if active is not None:
            try:
                self.active = active
            except Exception:
                try:
                    self._misc_info.update({'active': active})
                except Exception:
                    pass

    @hybrid_property
    def procedure(self) -> List[Procedure]:
        return self._procedure
    
    @procedure.setter
    def procedure(self, value):
        error_msg = f"Can't add item {value} to {self.name}._procedure"
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureReagentLotAssociation(procedure=item['name'], reagentlot=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureReagentLotAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for .procedure")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureReagentLotAssociation):
                if output not in self.procedurereagentlotassociation:
                    self.procedurereagentlotassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._procedure")

    @hybrid_property
    def expiry(self):
        return self._expiry

    @expiry.setter
    def expiry(self, value):
        if isinstance(value, dict):
            value = value.get("value", datetime.now())
        match value:
            case datetime() | date():
                output = value
            # case date():
            #     output = datetime.combine(value, datetime.max.time())
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
                raise ValueError(f"Unmatched value {value['value']} for datetime")
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
                output = value.to_sql()
            case Reagent():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .reagent")
                return
        if isinstance(output, Reagent):
            self._reagent = output
        else:
                logger.error(f"Could not add {item} to ._reagent.")
        
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
        return f"{reagent}-{self.lot}"

    @name.expression
    def name(cls):
        # We need the Process table available in the context of the main query
        # We use a correlated approach or rely on an implicit join when filtering
        # The key is to return a SQL expression directly:
        # Use func.concat() with an explicit join to the Process table
        # return func.concat(
        #     Reagent.name,
        #     "-",
        #     cls.lot
        # ).label("name")
        regeant_subquery = (
            select(Reagent.name)
            .where(Reagent.id==cls.reagent_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # Note: Can't use f strings for this for some reason.
        return regeant_subquery + "-" + cls.lot

    @classmethod
    def query(cls,
              lot: str | None = None,
              name: str | None = None,
              reagent: str | Reagent | None = None,
              limit: int = 0,
              **kwargs) -> ReagentLot | List[ReagentLot]:
        """

        Args:
            lot ( str | None, optional): Lot number of this reagent instance. Defaults to None.
            name ( str | None, optional): Name of this reagent instance. Defaults to None.
            limit ( int ): Limit of number of query results.
            **kwargs ():

        Returns:
            ReagentLot | List[ReagentLot]

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

    @check_authorization
    def edit_from_search(self, obj, **kwargs):
        from frontend.widgets.omni_add_edit import AddEdit
        from backend.validators.pydant import PydElastic
        dlg = AddEdit(parent=None, instance=self, disabled=['reagent'])
        if dlg.exec():
            pyd = dlg.parse_form()
            # logger.debug(f"Pydantic returned: {type(pyd)} {pyd.model_fields}")
            fields = pyd.model_fields
            if isinstance(pyd, PydElastic):
                fields.update(pyd.model_extra)
            for field in fields:
                if field in ['instance']:
                    continue
                field_value = pyd.__getattribute__(field)
                # logger.debug(f"Setting {field} in Reagent Lot to {field_value}")
                self.set_attribute(field, field_value)
            self.save()

    def details_dict(self, **kwargs) -> dict:
        output = super().details_dict(**kwargs)
        output['excluded'] += ["reagentlotprocedureassociation", "procedures"]
        output['reagent'] = output['reagent']
        return output


class Discount(BaseClass):
    """
    Relationship table for client labs for certain kits.
    """

    # skip_on_edit = True

    id = Column(INTEGER, primary_key=True)  #: primary key
    _proceduretype = relationship("ProcedureType")  #: joined parent proceduretype
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete='SET NULL',
                                                  name="fk_DIS_procedure_type_id"))  #: id of joined proceduretype
    _clientlab = relationship("ClientLab")  #: joined client lab
    clientlab_id = Column(INTEGER,
                          ForeignKey("_clientlab.id", ondelete='SET NULL',
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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if clientlab is not None:
            try:
                self.clientlab = clientlab
            except Exception:
                try:
                    self._misc_info.update({'clientlab': clientlab})
                except Exception:
                    pass

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
        # We need the Process table available in the context of the main query
        # We use a correlated approach or rely on an implicit join when filtering
        # The key is to return a SQL expression directly:
        # Use func.concat() with an explicit join to the Process table
        # return func.concat(
        #     ClientLab.name,
        #     "-",
        #     ProcedureType.name,
        #     "-",
        #     cast(cls.amount, String)
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return clientlab_subquery + "-" + proceduretype_subquery + "-" + cast(cls.amount, String)

    @hybrid_property
    def clientlab(self) -> ClientLab:
        return self._clientlab

    @clientlab.setter
    def clientlab(self, value):
        from backend.validators.pydant import PydClientLab
        # if value is None:
        #     value = []
        # if not isinstance(value, list):
        #     value = [value]
        # for item in value:
            
        match value:
            case str():
                output = ClientLab.query(name=value, limit=1)
            case dict():
                output = ClientLab.query_or_create(**value)
            case PydClientLab():
                output = value.to_sql()
            case ClientLab():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .clientlab")
                # continue
                return
        if isinstance(output, ClientLab):
            # if output not in self._clientlab:
            self._clientlab = output
        else:
            logger.error(f"Couldn't add {value} to ._clientlab")
    
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
                output = value.to_sql()
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for .proceduretype")
                return
        if isinstance(output, ProcedureType):
            # if output not in self._clientlab:
            self._proceduretype = output
        else:
            logger.error(f"Couldn't add {value} to ._clientlab")

    @classmethod
    @setup_lookup
    def query(cls,
              clientlab: ClientLab | str | int | None = None,
              proceduretype: ProcedureType | str | int | None = None,
              ) -> Discount | List[Discount]:
        """
        Lookup discount objects (union of kittype and clientlab)

        Args:
            clientlab (models.ClientLab | str | int): ClientLab receiving discount.
            proceduretype (models.ProcedureType | str | int): Kit discount received on.

        Returns:
            models.Discount|List[models.Discount]: Discount(s) of interest.
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
        super().save()


class SubmissionType(BaseClass):
    """
    Abstract of types of procedure.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(128), unique=True)  #: name of procedure type
    defaults = Column(JSON)  #: Basic information about this procedure type
    file_name_template = Column(String(256))  #: Jinja2 template for naming files of this submission type
    abbreviation = Column(String(4))
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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if clientsubmission is not None:
            try:
                self.clientsubmission = clientsubmission
            except Exception:
                try:
                    self._misc_info.update({'clientsubmission': clientsubmission})
                except Exception:
                    pass
    
    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object.
        """
        return f"<SubmissionType({self.name})>"

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
        for item in value:
            match item:
                case str():
                    output = ClientSubmission.query(name=item, limit=1)
                case dict():
                    output = ClientSubmission.query_or_create(**item)
                case PydClientSubmission():
                    output = item.to_sql()
                case ClientSubmission():
                    output = item
                case _:
                    logger.error(f"Unmatched value: {item} for .clientsubmission")
                    continue
            if isinstance(output, ClientSubmission):
                if output not in self._clientsubmission:
                    self._clientsubmission.append(output)
            else:
                logger.error(f"Could not add {item} to ._clientsubmission")

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
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._proceduretype"
            match item:
                case str():
                    output = ProcedureType.query(name=item, limit=1)
                case dict():
                    output = ProcedureType.query_or_create(**item)
                case PydProcedureType():
                    output = item.to_pydantic()
                case ProcedureType():
                    output = item
                case _:
                    logger.error(f"Unmatched value: {item} for .proceduretype")
                    continue
            if isinstance(output, ProcedureType):
                if output not in self._proceduretype:
                    self._proceduretype.append(output)
            else:
                logger.error(f"Could not add {item} to ._proceduretype")
    
    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.

        Returns:
            List[str]: List of names
        """
        return super().aliases + ["submissiontypes"]

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[SubmissionType, bool]:
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            setattr(instance, k, v)
        logger.info(f"Instance from proceduretype query or create: {instance}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              key: str | None = None,
              limit: int = 0,
              **kwargs
              ) -> SubmissionType | List[SubmissionType]:
        """
        Lookup procedure type in the database by a number of parameters

        Args:
            name (str | None, optional): Name of procedure type. Defaults to None.
            key (str | None, optional): A key present in the info-map to lookup. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.SubmissionType|List[models.SubmissionType]: SubmissionType(s) of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                # logger.debug(f"querying with {name}")
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

    @classmethod
    @declared_attr
    def info_map_json_edit_fields(cls):
        dicto = dict()
        return dicto

    @classmethod
    @declared_attr
    def regex(cls) -> re.Pattern:
        """
        Constructs catchall regex.

        Returns:
            re.Pattern: Regular expression pattern to discriminate between procedure types.
        """
        res = [st.defaults['regex'] for st in cls.query() if st.defaults]
        rstring = rf'{"|".join(res)}'
        regex = re.compile(rstring, flags=re.IGNORECASE | re.VERBOSE)
        return regex

    @classmethod
    def get_regex(cls, submission_type: SubmissionType | str | None = None) -> re.Pattern:
        """
        Gets the regex string for identifying a certain class of procedure.

        Args:
            submission_type (SubmissionType | str | None, optional): procedure type of interest. Defaults to None.

        Returns:
            str: String from which regex will be compiled.
        """
        if not isinstance(submission_type, SubmissionType):
            submission_type = cls.query(name=submission_type['name'])
        if isinstance(submission_type, list):
            if len(submission_type) > 1:
                regex = "|".join([item.defaults['regex'] for item in submission_type])
            else:
                regex = submission_type[0].defaults['regex']
        else:
            try:
                regex = submission_type.defaults['regex']
            except AttributeError as e:
                logger.error(f"Couldn't get submission type for {submission_type.name}")
                regex = None
        try:
            regex = re.compile(rf"{regex}", flags=re.IGNORECASE | re.VERBOSE)
        except re.error as e:
            regex = None
        return regex


class ProcedureType(BaseClass):
    
    id = Column(INTEGER, primary_key=True)
    name = Column(String(64), unique=True)
    plate_columns = Column(INTEGER, default=0)
    plate_rows = Column(INTEGER, default=0)
    plate_cost = Column(FLOAT(2), default=0.00)

    _procedure = relationship("Procedure",
                             back_populates="_proceduretype", cascade="all, delete-orphan")  #: Concrete control of this type.

    _submissiontype = relationship("SubmissionType", back_populates="_proceduretype",
                                  secondary=submissiontype_proceduretype)  #: run this kittype was used for

    _resultstype = relationship("ResultsType", back_populates="_proceduretype",
                                  secondary=proceduretype_resulttype)  #: run this kittype was used for
    
    discount = relationship("Discount", back_populates="_proceduretype")

    proceduretypeequipmentroleassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="_proceduretype",
        cascade="all, delete-orphan"
    )  #: Association of equipmentroles

    _equipmentrole = association_proxy("proceduretypeequipmentroleassociation", "_equipmentrole")  #: Proxy of equipmentrole associations

    proceduretypereagentroleassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        back_populates="_proceduretype",
        cascade="all, delete-orphan"
    )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes

    _reagentrole = association_proxy("proceduretypereagentroleassociation", "_reagentrole")

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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        # Resolve reagentrole
        if submissiontype is not None:
            try:
                self.submissiontype = submissiontype
            except Exception:
                try:
                    self._misc_info.update({'submissiontype': submissiontype})
                except Exception:
                    pass
        else:
            self.submissiontype = ["Default SubmissionType"]
        if resultstype is not None:
            try:
                self.resultstype = resultstype
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'resultstype': resultstype})
                except Exception:
                    pass
        # Resolve reagentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                try:
                    self._misc_info.update({'equipmentrole': equipmentrole})
                except Exception:
                    pass
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                try:
                    self._misc_info.update({'reagentrole': reagentrole})
                except Exception:
                    pass

    def create_reagentrole_association(self, reagentrole: str | dict | ReagentRole) -> ProcedureTypeReagentRoleAssociation:
        """
        Create an association between this ProcedureType and a ReagentRole.

        Args:
            reagentrole (ReagentRole | str): ReagentRole of interest.
            uses (dict | None, optional): Map of uses for this reagentrole in this proceduretype. Defaults to None.
        Returns:
            ProcedureTypeReagentRoleAssociation: Created association.
        """        
        from backend.validators.pydant import PydReagentRole
        if not isinstance(reagentrole, list):
            reagentrole = [reagentrole]
        for rr in reagentrole:
            match rr:
                case str():
                    reagentrole_instance = ReagentRole.query(name=rr, limit=1)
                case dict():
                    reagentrole_instance = ReagentRole.query(name=rr.get('name'), limit=1)
                    del rr['name']
                case PydReagentRole():
                    reagentrole_instance = rr.to_sql()
                case ReagentRole():
                    reagentrole_instance = rr
                case _:
                    raise TypeError(f"Can't create association with {rr}")
            association = ProcedureTypeReagentRoleAssociation(proceduretype=self, reagentrole=reagentrole_instance, **(reagentrole if isinstance(reagentrole, dict) else {}))
            # association.proceduretype = self
            # association.reagentrole = reagentrole_instance
            # association.__dict__.update(reagentrole if isinstance(reagentrole, dict) else {})
            self.proceduretypereagentroleassociation.append(association)
            return association

    @hybrid_property
    def equipmentrole(self):
        return self._equipmentrole
    
    @equipmentrole.setter
    def equipmentrole(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureTypeEquipmentRoleAssociation(equipmentrole=item['name'], proceduretype=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureTypeEquipmentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for equipmentrole")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureTypeEquipmentRoleAssociation):
                if output not in self.proceduretypeequipmentroleassociation:
                    self.proceduretypeequipmentroleassociation.append(output)
            else:
                logger.error(f"Couldn't add {item} to _equipmentrole")
            
    @hybrid_property
    def reagentrole(self):
        return self._reagentrole    
    
    @reagentrole.setter
    def reagentrole(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureTypeReagentRoleAssociation(reagentrole=item['name'], proceduretype=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureTypeReagentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for reagentrole")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureTypeReagentRoleAssociation):
                if output not in self.proceduretypereagentroleassociation:
                    self.proceduretypereagentroleassociation.append(output)
            else:
                logger.debug(f"Couldn't add {item} to _reagentrole")

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
        for item in value:
            match item:
                case str():
                    output = ResultsType.query(name=item, limit=1)
                case dict():
                    output = ResultsType.query_or_create(**item)
                case PydResultsType():
                    output = item.to_sql()
                case ResultsType():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for resultstype.")
                    continue
            if isinstance(output, ResultsType):
                if output not in self._resultstype:
                    self._resultstype.append(output)
            else:
                logger.error(f"Could not add {item} to _resultstype")
    
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
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._submissiontype"
            match item:
                case str():
                    output = SubmissionType.query(name=item, limit=1)
                case dict():
                    output = SubmissionType.query_or_create(**item)
                case PydSubmissionType():
                    output = item.to_sql()
                case SubmissionType():
                    output = item
                case _:
                    raise TypeError(error_msg)
            if isinstance(output, SubmissionType):
                self._submissiontype.append(output)
            else:
                raise TypeError(error_msg)
        if "Default SubmissionType" not in [st.name for st in self._submissiontype]:
            self._submissiontype.append(SubmissionType.query(name="Default SubmissionType", limit=1))
        
    @hybrid_property
    def procedure(self):
        return self._procedure

    @procedure.setter
    def procedure(self, value):
        from backend.validators.pydant import PydProcedure
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = Procedure.query(name=item, limit=1)
                case dict():
                    output = Procedure.query_or_create(**item)
                case PydProcedure():
                    output = item.to_sql()
                case Procedure():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for procedure")
                    continue
            if isinstance(output, Procedure):
                if output not in self._procedure:
                    self._procedure.append(output)
            else:
                logger.error(f"Could not add {item} to procedure")

    def construct_field_map(self, field: Literal['equipment', 'tip']) -> Generator[(str, dict), None, None]:
        """
        Make a map of all locations for tips or equipment.

        Args:
            field (Literal['equipment', 'tip']): the field to construct a map for

        Returns:
            Generator[(str, dict), None, None]: Generator composing key, locations for each item in the map
        """
        for item in self.__getattribute__(f"proceduretype{field}role_associations"):
            fmap = item.uses
            if fmap is None:
                fmap = {}
            yield getattr(item, f"{field}_role").name, fmap

    def get_equipment(self) -> Generator['PydEquipmentRole', None, None]:
        """
        Returns PydEquipmentRole of all equipment associated with this SubmissionType

        Returns:
            Generator['PydEquipmentRole', None, None]: List of equipment roles
        """
        return (item.to_pydantic(proceduretype=self) for item in self.equipment)

    def get_processes_for_role(self, equipmentrole: str | EquipmentRole) -> list:
        """
        Get process associated with this SubmissionType for an EquipmentRole

        Args:
            equipmentrole (str | EquipmentRole): EquipmentRole of interest
            kittype (str | KitType | None, optional): Kit of interest. Defaults to None.

        Raises:
            TypeError: Raised if wrong type given for equipmentrole

        Returns:
            list: list of associated process
        """
        match equipmentrole:
            case str():
                relevant = [item.get_all_processes() for item in self.proceduretypeequipmentroleassociation if
                            item.equipmentrole.name == equipmentrole]
            case EquipmentRole():
                relevant = [item.get_all_processes() for item in self.proceduretypeequipmentroleassociation if
                            item.equipmentrole == equipmentrole]
            case _:
                raise TypeError(f"Type {type(equipmentrole)} is not allowed")
        return list(set([item for items in relevant for item in items if item is not None]))

    # def details_dict(self, **kwargs):
    #     output = super().details_dict(**kwargs)
    #     # output['submissiontype'] = [item.name for item in output['submissiontype']]
    #     output['reagentrole'] = [item.details_dict() for item in output['reagentrole']]
    #     output['equipmentrole'] = [item.details_dict() for item in output['equipmentrole']]
    #     return output

    def construct_dummy_procedure(self, run: Run | None = None):
        from backend.validators.pydant import PydProcedure
        if run:
            samples = run.constuct_sample_dicts_for_proceduretype(proceduretype=self)
            run = run.name
        else:
            samples = []
        output = dict(
            proceduretype=self,
            repeat=False,
            run=run,
            sample=samples
        )
        return PydProcedure(**output)

    def construct_plate_map(self, sample_dicts: List["PydSample"], creation:bool=True, vw_modifier:float=1.0) -> str:
        """
        Constructs an html based plate map for procedure details.

        Args:
            sample_list (list): List of procedure sample
            plate_rows (int, optional): Number of rows in the plate. Defaults to 8.
            plate_columns (int, optional): Number of columns in the plate. Defaults to 12.

        Returns:
            str: html output string.
        """
        if self.plate_rows == 0 or self.plate_columns == 0:
            return "<br/>"
        sample_dicts = self.pad_sample_dicts(sample_dicts=sample_dicts)
        vw = round((-0.07 * len(sample_dicts)) + (12.2 * vw_modifier), 1)
        # NOTE: An overly complicated list comprehension create a lisst of sample locations
        # NOTE: next will return a blank cell if no value found for row/column
        env = jinja_template_loading()
        template = env.get_template("support/plate_map.html")
        html = template.render(plate_rows=self.plate_rows, plate_columns=self.plate_columns, samples=sample_dicts,
                               vw=vw, creation=creation)
        return html + "<br/>"

    def pad_sample_dicts(self, sample_dicts: List[PydSample]):
        from backend.validators.pydant import PydSample
        output = []
        for row, column in self.ranked_plate.values():
            sample = next((sample for sample in sample_dicts if sample.row == row and sample.column == column),
                          PydSample(**dict(sample_id="", row=row, column=column, enabled=False, background_color="white")))
            # if not hasattr(sample, "background_color"):
            #     sample.background_color = "white"
            output.append(sample)
        return output

    @property
    def ranked_plate(self):
        matrix = np.array([[0 for yyy in range(1, self.plate_rows + 1)] for xxx in range(1, self.plate_columns + 1)])
        return {iii: (item[0][1] + 1, item[0][0] + 1) for iii, item in enumerate(np.ndenumerate(matrix), start=1)}

    @property
    def total_wells(self):
        return self.plate_rows * self.plate_columns


class Procedure(BaseClass):
    
    id = Column(INTEGER, primary_key=True)  #: Primary key
    name = Column(String, unique=True)  #: Name of the procedure (RSL number)
    repeat_of_id = Column(INTEGER, ForeignKey("_procedure.id", name="fk_repeat_id"))
    _repeat_of = relationship("Procedure", remote_side=[id])
    _started_date = Column(TIMESTAMP)
    _completed_date = Column(TIMESTAMP)
    technician = Column(String(64))  #: name of processing tech(s)
    _results = relationship("Results", back_populates="_procedure", uselist=True, cascade="all, delete-orphan")  #: Results from this procedure
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete="SET NULL",
                                                  name="fk_PRO_proceduretype_id"))  #: client lab id from _organizations))
    _proceduretype = relationship("ProcedureType", back_populates="_procedure")  #: ProcedureType of this procedure
    run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="SET NULL",
                                        name="fk_PRO_basicrun_id"))  #: client lab id from _organizations))
    _run = relationship("Run", back_populates="_procedure")  #: Run this procedure is part of

    proceduresampleassociation = relationship(
        "ProcedureSampleAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan",
    )

    _sample = association_proxy("proceduresampleassociation", "_sample")

    procedurereagentlotassociation = relationship(
        "ProcedureReagentLotAssociation",
        back_populates="_procedure",
        cascade="all, delete-orphan",
    )  #: Relation to ProcedureReagentAssociation

    _reagentlot = association_proxy("procedurereagentlotassociation", "_reagentlot")  #: Association proxy to ReagentLot

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
        started_date = kwargs.pop('started_date', None)
        completed_date = kwargs.pop('completed_date', None)
        proceduretype = kwargs.pop('proceduretype', None)
        results = kwargs.pop('results', None)
        run = kwargs.pop('run', None)
        sample = kwargs.pop('sample', None)
        reagentlot = kwargs.pop('reagentlot', None)
        equipment = kwargs.pop('equipment', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if repeat_of is not None:
            try:
                self.repeat_of = repeat_of
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'repeat_of': repeat_of})
                except Exception:
                    pass
        # Resolve reagentrole
        if started_date is not None:
            try:
                self.started_date = started_date
            except Exception:
                try:
                    self._misc_info.update({'started_date': started_date})
                except Exception:
                    pass
        if completed_date is not None:
            try:
                self.completed_date = completed_date
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'completed_date': completed_date})
                except Exception:
                    pass
        # Resolve reagentrole
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if results is not None:
            try:
                self.results = results
            except Exception:
                try:
                    self._misc_info.update({'results': results})
                except Exception:
                    pass
        # Resolve reagentrole
        if run is not None:
            try:
                self.run = run
            except Exception:
                try:
                    self._misc_info.update({'run': run})
                except Exception:
                    pass
        if sample is not None:
            try:
                self.sample = sample
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'sample': sample})
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
        # Resolve reagentrole
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                try:
                    self._misc_info.update({'equipment': equipment})
                except Exception:
                    pass
    
    @hybrid_property
    def reagentlot(self):
        return self._reagentlot
    
    @reagentlot.setter
    def reagentlot(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureReagentLotAssociation(reagentlot=item['name'], procedure=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureTypeReagentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for reagentlot")
                    return
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureReagentLotAssociation):
                if output not in self.procedurereagentlotassociation:
                    self.procedurereagentlotassociation.append(output)
            else:
                logger.error(f"Could not add {item} to ._reagentlot")

    @hybrid_property
    def equipment(self):
        return self._equipment
    
    @equipment.setter
    def equipment(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureEquipmentAssociation(equipment=item['name'], procedure=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for equipment")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureEquipmentAssociation):
                if output not in self.procedureequipmentassociation:
                    self.procedureequipmentassociation.append(output)
            else:
                logger.error(f"Could not add {item} to _equipment")

    @hybrid_property
    def sample(self):
        return self._sample
    
    @sample.setter
    def sample(self, value):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureSampleAssociation(sample=item['name'], procedure=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureSampleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for sample")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, ProcedureSampleAssociation):
                if output not in self.proceduresampleassociation:
                    self.proceduresampleassociation.append(output)
            else:
                logger.error(f"Could not add {item} to _sample")

    @hybrid_property
    def started_date(self):
        return self._started_date

    @started_date.setter
    def started_date(self, value):
        self._started_date = value

    @hybrid_property
    def completed_date(self):
        return self._completed_date

    @completed_date.setter
    def completed_date(self, value):
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
                output = value.to_sql()
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for proceduretype")
                return
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Could not set _proceduretype to {output}")

    @hybrid_property
    def run(self):
        return self._run

    @run.setter
    def run(self, value):
        from backend.validators.pydant import PydRun
        match value:
            case str():
                output = Run.query(name=value, limit=1)
            case dict():
                output = Run.query_or_create(**value)
            case PydRun():
                output = value.to_sql()
            case Run():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for run")
                return
        if isinstance(output, Run):
            self._run = output
        else:
            logger.error(f"Unable to set run to {value}")
    
    @hybrid_property
    def results(self):
        return self._results

    @results.setter
    def results(self, value):
        from backend.validators.pydant import PydResults
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            error_msg = f"Can't add item {item} to {self.name}._results"
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
                    logger.error(f"Unmatched value {item} for results")
                    continue
            if isinstance(output, Results):
                self._results.append(output)
            else:
                logger.error(f"Could not add {item} to _results")
    
    @hybrid_property
    def repeat_of(self):
        return self._repeat_of

    @repeat_of.setter
    def repeat_of(self, value):
        from backend.validators.pydant import PydProcedure
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = Procedure.query(name=item, limit=1)
                case dict():
                    output = Procedure.query_or_create(**item)
                case PydProcedure():
                    output = item.to_sql()
                case Procedure():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for repeat_of")
                    continue
            if isinstance(output, Procedure):
                if output not in self._repeat_of:
                    self._repeat_of.append(output)
            else:
                logger.error(f"Could not add {item} to _repeat_of")
    
    @hybrid_property
    def repeat(self) -> bool:
        return self._repeat_of is not None

    @classmethod
    @setup_lookup
    def query(cls, id: int | None = None, name: str | None = None,
              start_date: date | datetime | str | int | None = None,
              end_date: date | datetime | str | int | None = None, limit: int = 0, **kwargs) -> Procedure | List[
        Procedure]:
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
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @property
    def custom_context_events(self) -> dict:
        """
        Creates dictionary of str:function to be passed to context menu

        Returns:
            dict: dictionary of functions
        """
        names = ["Add Results", "Add Equipment", "Edit", "Add Comment", "Show Details", "Delete"]
        return {item: self.__getattribute__(item.lower().replace(" ", "_")) for item in names}

    def add_results(self, obj, resultstype_name: str):
        logger.info(f"Add Results! {resultstype_name}")
        from backend.managers import results
        results_manager = getattr(results, f"{resultstype_name}Manager")
        rs = results_manager(procedure=self, parent=obj)#, fname=Path("C:\\Users\lwark\Documents\Submission_Forms\QubitData_18-09-2025_13-43-53.csv"))
        procedure_results = rs.procedure_to_pydantic()
        samples_results = rs.samples_to_pydantic()
        if procedure_results:
            procedure_sql = procedure_results.to_sql()
        else:
            return
        procedure_sql.save()
        for sample in samples_results:
            sample_sql = sample.to_sql()
            sample_sql.save()

    def add_equipment(self, obj):
        """
        Creates widget for adding equipment to this submission

        Args:
            obj (_type_): parent widget
        """
        logger.info(f"Add equipment")
        from frontend.widgets.equipment_usage import EquipmentUsage
        dlg = EquipmentUsage(parent=obj, procedure=self.to_pydantic())
        if dlg.exec():
            dlg.save_procedure()

    def edit(self, obj):
        from frontend.widgets.procedure_creation import ProcedureCreation
        logger.debug("Edit!")
        dlg = ProcedureCreation(parent=obj, procedure=self.to_pydantic(), edit=True)
        if dlg.exec():
            sql, _ = dlg.return_sql()
            # NOTE: Print out all procedureequipmentassociation objects
            sql.save()

    def add_comment(self, obj):
        logger.debug("Add Comment!")

    def delete(self, obj):
        logger.debug("Delete!")

    def details_dict(self, **kwargs) -> dict:
        output = super().details_dict()
        output['proceduretype'] = output['proceduretype'].details_dict()['name']
        output['results'] = [result.details_dict() for result in output['results']]
        run_samples = [sample for sample in self.run.sample]
        active_samples = [sample.details_dict() for sample in output['proceduresampleassociation']
                          if sample.sample.sample_id in [s.sample_id for s in run_samples]]
        for sample in active_samples:
            sample['active'] = True
        inactive_samples = [sample.details_dict() for sample in run_samples if
                            sample.name not in [s['sample_id'] for s in active_samples]]
        for sample in inactive_samples:
            sample['active'] = False
        output['sample'] = active_samples + inactive_samples
        output['reagent'] = [reagent.details_dict() for reagent in output['procedurereagentlotassociation']]
        output['equipment'] = [equipment.details_dict() for equipment in output['procedureequipmentassociation']]
        output['repeat'] = self.repeat
        output['run'] = self.run.name
        output['excluded'] += self.get_default_info("details_ignore")
        output['sample_count'] = len(active_samples)
        output['clientlab'] = self.run.clientsubmission.clientlab.name
        output['cost'] = 0.00
        output['platemap'] = self.make_procedure_platemap()
        return output

    def to_pydantic(self, **kwargs):
        from backend.validators.pydant import PydReagent
        output = super().to_pydantic()
        output.sample = [item.to_pydantic() for item in output.proceduresampleassociation]
        reagents = []
        for reagent in output.reagent:
            match reagent:
                case dict():
                    reagents.append(PydReagent(**reagent))
                case PydReagent():
                    reagents.append(reagent)
                case _:
                    pass
        output.reagent = reagents
        output.result = [item.to_pydantic() for item in self.results]
        output.sample_results = flatten_list(
            [[result.to_pydantic() for result in item.results] for item in self.proceduresampleassociation])
        return output

    # def create_proceduresampleassociations(self, sample):
    #     from backend.db.models import ProcedureSampleAssociation
    #     return ProcedureSampleAssociation(procedure=self, sample=sample)

    @classmethod
    def get_default_info(cls, *args) -> dict | list | str:
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

    def make_procedure_platemap(self):
        dicto = [sample.to_pydantic() for sample in self.proceduresampleassociation]
        html = self.proceduretype.construct_plate_map(sample_dicts=dicto, creation=False, vw_modifier=1.15)
        return html

    @property
    def submissiontype(self):
        return self.run.clientsubmission.submissiontype


class ProcedureTypeReagentRoleAssociation(BaseClass):
    """
    table containing reagenttype/kittype associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id"),
                            primary_key=True)  #: id of associated reagentrole
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"),
                              primary_key=True)  #: id of associated proceduretype
    last_used = Column(String(32))  #: last used lot number of this type of reagent
    
    # NOTE: reference to the "ReagentType" object
    _reagentrole = relationship(ReagentRole,
                               back_populates="reagentroleproceduretypeassociation")  #: relationship to associated ReagentType

    # NOTE: reference to the "SubmissionType" object
    _proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypereagentroleassociation")  #: relationship to associated SubmissionType

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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                try:
                    self._misc_info.update({'reagentrole': reagentrole})
                except Exception:
                    pass

    

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
                output = value.to_sql()
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for proceduretype")
                return
        if isinstance(output, ProcedureType):
            self._proceduretype = output
        else:
            logger.error(f"Could not set _proceduretype to {value}")

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
                if isinstance(output, tuple):
                    output = output[0]
            case PydReagentRole():
                output = value.to_sql()
            case ReagentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for reagentrole")
                return
        # logger.debug(f"Setting reagentrole with output: {output}")
        if isinstance(output, ReagentRole):
            self._reagentrole = output
        else:
            logger.error(f"Could not set _reagentrole to {value}")

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
        # return func.concat(
        #     ProcedureType.name,
        #     "->",
        #     ReagentRole.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return proceduretype_subquery + "->" + reagentrole_subquery

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[ProcedureTypeReagentRoleAssociation, bool]:
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            # logger.debug(f"Key: {k} has value: {v}")
            match k:
                case "proceduretype":
                    if isinstance(v, str):
                        v = SubmissionType.query(name=v)
                    else:
                        v = v.instance_object
                case "reagentrole":
                    if isinstance(v, str):
                        v = ReagentRole.query(name=v)
                    else:
                        v = v.instance_object
                case _:
                    pass
            setattr(instance, k, v)
        # logger.info(f"Instance from query or create: {instance.__dict__}\nis new: {new}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              reagentrole: ReagentRole | str | None = None,
              proceduretype: ProcedureType | str | None = None,
              limit: int = 0,
              **kwargs
              ) -> ProcedureTypeReagentRoleAssociation | List[ProcedureTypeReagentRoleAssociation]:
        """
        Lookup junction of ReagentType and KitType

        Args:
            proceduretype (models.ProcedureType | str | None, optional): KitType of interest. Defaults to None.
            reagentrole (models.ReagentRole | str | None, optional): ReagentRole of interest. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]: Junction of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match reagentrole:
            case ReagentRole():
                query = query.filter(cls.reagent_role == reagentrole)
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
        pass
        return cls.execute_query(query=query, limit=limit)

    def get_all_relevant_reagents(self) -> Generator[Reagent, None, None]:
        """
        Creates a generator that will resolve in to a list filling the reagentrole associated with this object.

        Returns:
            Generator: Generates of reagents.
        """
        reagents = self.reagentrole.control
        try:
            regex = self.uses['exclude_regex']
        except KeyError:
            regex = "^$"
        relevant_reagents = [reagent for reagent in reagents if
                             not check_regex_match(pattern=regex, check=str(reagent.lot))]
        for rel_reagent in relevant_reagents:
            yield rel_reagent

    @classmethod
    @declared_attr
    def json_edit_fields(cls) -> dict:
        dicto = dict(
            sheet="str",
            expiry=dict(column="int", row="int"),
            lot=dict(column="int", row="int"),
            name=dict(column="int", row="int")
        )
        return dicto


class ProcedureReagentLotAssociation(BaseClass):
    """
    table containing procedure/reagent associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    skip_on_edit = True

    reagentlot_id = Column(INTEGER, ForeignKey("_reagentlot.id"), primary_key=True)  #: id of associated reagent
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id"), primary_key=True)
    comments = Column(String(1024))  #: Comments about reagents

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
        reagentlot = kwargs.pop('procedure', None)
        reagentrole = kwargs.pop('reagentrole', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'procedure': procedure})
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
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                try:
                    self._misc_info.update({'reagentrole': reagentrole})
                except Exception:
                    pass
    
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
        # return func.concat(
        #     Procedure.name,
        #     "->",
        #     ReagentLot.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return procedure_subquery + "->" + reagentlot_subquery

    @hybrid_property
    def reagentlot(self):
        return self._reagentlot

    @reagentlot.setter
    def reagentlot(self, value):
        from backend.validators.pydant import PydReagentLot
        match value:
            case str():
                output = ReagentLot.query(name=value, limit=1)
            case dict():
                output = ReagentLot.query_or_create(**value)
            case PydReagentLot():
                output = item.to_sql()
            case ReagentLot():
                output = item
            case _:
                logger.error(f"Unmatched value {value} for reagentlot")
                return
        if isinstance(output, ReagentLot):
            self._reagentlot = output
        else:
            logger.error(f"Could not set _reagentlot to {value}")
    
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
                output = item.to_sql()
            case Procedure():
                output = item
            case _:
                logger.error(f"Unmatched value {value} for procedure")
                return
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set _procedure to {value}")

    @classmethod
    @setup_lookup
    def query(cls,
              procedure: Procedure | str | int | None = None,
              reagentlot: Reagent | str | None = None,
              reagentrole: str | ReagentRole | None = None,
              limit: int = 0) -> ProcedureReagentLotAssociation | List[ProcedureReagentLotAssociation]:
        """
        Lookup SubmissionReagentAssociations of interest.

        Args:
            procedure (Procedure | str | int | None, optional): Identifier of joined procedure. Defaults to None.
            reagentlot (ReagentLot | str | None, optional): Identifier of joined reagent. Defaults to None.
            reagent (Reagent | str | None, optional): Identifier of joined reagent. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            RunReagentAssociation|List[RunReagentAssociation]: SubmissionReagentAssociation(s) of interest
        """
        query: Query = cls.__database_session__.query(cls)
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

    def details_dict(self, **kwargs):
        output = super().details_dict()
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['reagent']}
        output = output['reagentlot'].details_dict()
        output['reagent_name'] = self.reagentlot.reagent.name
        misc = output['misc_info']
        output.update(relevant)
        output['reagentrole'] = self.reagentrole.name
        output['misc_info'] = misc
        # logger.debug(f"Output: {pformat(output)}")
        return output

    def delete(self, **kwargs):
        self.__database_session__.delete(self)
        try:
            self.__database_session__.commit()
        except (SQLIntegrityError, SQLOperationalError, AlcIntegrityError, AlcOperationalError) as e:
            self.__database_session__.rollback()
            raise e


class ReagentRoleReagentAssociation(BaseClass):

    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id"), primary_key=True)  #: id of associated reagent
    reagent_id = Column(INTEGER, ForeignKey("_reagent.id"), primary_key=True)  #: id of associated procedure
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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'reagent': reagent})
                except Exception:
                    pass
        # Resolve reagentrole
        if reagentrole is not None:
            try:
                self.reagentrole = reagentrole
            except Exception:
                try:
                    self._misc_info.update({'reagentrole': reagentrole})
                except Exception:
                    pass

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
        # return func.concat(
        #     ReagentRole.name,
        #     "->",
        #     Reagent.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return reagentrole_subquery + "->" + reagent_subquery

    @hybrid_property
    def reagent(self):
        return self._reagent

    @reagent.setter
    def reagent(self, value):
        from backend.validators.pydant import PydReagent
        error_msg = f"Can't add item {value} to {self.name}._reagent"
        match value:
            case str():
                output = Reagent.query(name=value, limit=1)
            case dict():
                output = Reagent.query_or_create(**value)
            case PydReagent():
                output = value.to_sql()
            case Reagent():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for reagent")
                return
        if isinstance(output, Reagent):
            self._reagent = output
        else:
            logger.error(f"Could not set _reagent to {output}")
    
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
                output = value.to_sql()
            case ReagentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for reagentrole")
                return
        if isinstance(output, ReagentRole):
            self._reagentrole = output
        else:
            logger.error(f"Could not set _reagentrole to {output}")


class EquipmentRole(BaseClass):
    """
    Abstract roles for equipment
    """

    id = Column(INTEGER, primary_key=True)  #: Role id, primary key
    name = Column(String(32))  #: Common name

    equipmentroleproceduretypeassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="_equipmentrole",
        cascade="all, delete-orphan",
    )  #: relation to SubmissionTypes

    _proceduretype = association_proxy("equipmentroleproceduretypeassociation", "_proceduretype")
    
    equipmentroleequipmentassociation = relationship(
        "EquipmentRoleEquipmentAssociation",
        back_populates="_equipmentrole",
        cascade="all, delete-orphan",
    )

    _equipment = association_proxy("equipmentroleequipmentassociation", "_equipment")
    
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
        # Resolve reagent
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                try:
                    self._misc_info.update({'equipment': equipment})
                except Exception:
                    pass

    @hybrid_property
    def equipment(self) -> List[Equipment]:
        return self._equipment
    
    @equipment.setter
    def equipment(self, value: List[Equipment | str | dict]):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = EquipmentRoleEquipmentAssociation.query_or_create(equipment=item['name'], equipmentrole=self, **{k: v for k, v in item.items() if k != 'name'})
                    if isinstance(output, tuple):
                        output = output[0]
                case EquipmentRoleEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Can't add item {item} to {self.name}._equipment")
                    continue
            # logger.debug(f"Setting equipment with output: {output}")
            if isinstance(output, EquipmentRoleEquipmentAssociation):
                if output not in self.equipmentroleequipmentassociation:
                    self.equipmentroleequipmentassociation.append(output)
            else:
                logger.error(f"Can't add item {item} to {self.name}._equipment")
                continue

    @hybrid_property
    def proceduretype(self) -> List[ProcedureType]:
        return self._proceduretype  

    @proceduretype.setter
    def proceduretype(self, value: List[ProcedureType | str | dict]):
        from backend.validators.pydant import PydProcedureType
        logger.debug(f"Setting Equipmentrole.proceduretype to {value}")
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureTypeEquipmentRoleAssociation.query_or_create(proceduretype=item['name'], equipmentrole=self, **{k: v for k, v in item.items() if k != 'name'})
                    if isinstance(output, tuple):
                        output = output[0]
                case ProcedureTypeEquipmentRoleAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value type: {item} for EquipmentRole.proceduretype")
                    continue
            # logger.debug(f"Setting proceduretype with output: {output}")
            if isinstance(output, ProcedureTypeEquipmentRoleAssociation):
                if output not in self.equipmentroleproceduretypeassociation:
                    self.equipmentroleproceduretypeassociation.append(output)
            else:
                logger.error(f"Unknown instance for Equipmentrole.proceduretype: {output}")
                continue

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[EquipmentRole, bool]:
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            setattr(instance, k, v)
        # logger.info(f"Instance from query or create: {instance}")
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
        Lookup Equipment roles.

        Args:
            name (str | None, optional): EquipmentRole name. Defaults to None.
            id (int | None, optional): EquipmentRole id. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            EquipmentRole|List[EquipmentRole]: List of EquipmentRoles matching criteria
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

    def get_processes(self, proceduretype: str | ProcedureType | None) -> Generator[Process, None, None]:
        """
        Get process used by this EquipmentRole

        Args:
            proceduretype (str | SubmissionType | None): SubmissionType of interest
            kittype (str | KitType | None, optional): KitType of interest. Defaults to None.

        Returns:
            List[Process]: List of process
        """
        if isinstance(proceduretype, str):
            proceduretype = SubmissionType.query(name=proceduretype)
        for process in self.process:
            if proceduretype and proceduretype not in process.proceduretype:
                continue
            yield process.name


class Equipment(BaseClass, LogMixin):
    """
    A concrete instance of equipment
    """

    id = Column(INTEGER, primary_key=True)  #: id, primary key
    name = Column(String(64))  #: equipment name
    _nickname = Column(String(64))  #: equipment nickname
    asset_number = Column(String(16))  #: Given asset number (corpo nickname if you will)

    equipmentprocedureassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="_equipment",
        cascade="all, delete-orphan",
    )  #: Association with BasicRun

    _procedure = association_proxy("equipmentprocedureassociation", "_procedure")  #: proxy to equipmentprocedureassociation.procedure

    equipmentequipmentroleassociation = relationship(
        "EquipmentRoleEquipmentAssociation",
        back_populates="_equipment",
        cascade="all, delete-orphan",
    )

    _equipmentrole = association_proxy("equipmentequipmentroleassociation", "_equipmentrole")

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
        # Resolve reagent
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        # Resolve reagentrole
        if equipmentrole is not None:
            try:
                self.equipment = equipmentrole
            except Exception:
                try:
                    self._misc_info.update({'equipmentrole': equipmentrole})
                except Exception:
                    pass
        # Resolve reagentrole
        try:
            self.nickname = nickname
        except Exception:
            self._misc_info.update({'nickname': nickname})
            
    @hybrid_property
    def equipmentrole(self) -> List[EquipmentRole]:
        return self._equipmentrole
    
    @equipmentrole.setter
    def equipmentrole(self, value: List[dict | str | EquipmentRole]):
        # current = self.equipmentequipmentroleassociation
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = EquipmentRoleEquipmentAssociation.query_or_create(equipmentrole=item.get('name'), equipment=self, **{k: v for k, v in item.items() if k != 'name'})
                    if isinstance(output, tuple):
                        output = output[0]
                case EquipmentRoleEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for equipmentrole")
                    continue
            if isinstance(output, EquipmentRoleEquipmentAssociation):
                if output not in self.equipmentequipmentroleassociation:
                    self.equipmentequipmentroleassociation.append(output)
            else:
                logger.error(f"Could not add {output} to equipmentrole")

    @hybrid_property
    def procedure(self) -> List[Procedure]:
        return self._procedure

    @procedure.setter
    def procedure(self, value: List[Procedure | str | dict]):
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case dict():
                    output = ProcedureEquipmentAssociation(procedure=item['name'], equipment=self, **{k: v for k, v in item.items() if k != 'name'})
                case ProcedureEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for procedure")
                    continue
            if isinstance(output, ProcedureEquipmentAssociation):
                if output not in self.equipmentprocedureassociation:
                    self.equipmentprocedureassociation.append(output)
            else:
                logger.error(f"Could not add {item} to _procedure")

    @hybrid_property
    def nickname(self) -> str:
        return self._nickname or self.name
                            
    @nickname.setter
    def nickname(self, value: str|None):
        if value is None or value == "":
            self._nickname = self.name
        else:
            self._nickname = value

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
        Lookup a list of or single Equipment.

        Args:
            name (str | None, optional): Equipment name. Defaults to None.
            nickname (str | None, optional): Equipment nickname. Defaults to None.
            asset_number (str | None, optional): Equipment asset number. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            Equipment|List[Equipment]: Equipment or list of equipment matching query parameters.
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

    def to_pydantic(self, equipmentrole: str = None) -> PydEquipment:
        """
        Creates PydEquipment of this Equipment

        Args:
            proceduretype (ProcedureType): Relevant SubmissionType
            kittype (str | KitType | None, optional): Relevant KitType. Defaults to None.

        Returns:
            PydEquipment: pydantic equipment object
        """
        from backend.validators.pydant import PydEquipment
        creation_dict = self.details_dict()
        processes = self.get_processes(equipmentrole=equipmentrole)
        creation_dict['processes'] = processes
        creation_dict['equipmentrole'] = equipmentrole or creation_dict['equipmentrole']
        return PydEquipment(**creation_dict)

    @classmethod
    @declared_attr
    def manufacturer_regex(cls) -> re.Pattern:
        """
        Creates regex to determine tip manufacturer

        Returns:
            re.Pattern: regex
        """
        return re.compile(r"""
                          (?P<PHAC>50\d{5}$)|
                          (?P<HC>HC-\d{6}$)|
                          (?P<Beckman>[^\d][A-Z0-9]{6}$)|
                          (?P<Axygen>[A-Z]{3}-\d{2}-[A-Z]-[A-Z]$)|
                          (?P<Labcon>\d{4}-\d{3}-\d{3}-\d$)""",
                          re.VERBOSE)

    @classmethod
    def assign_equipment(cls, equipmentrole: EquipmentRole | str) -> List[Equipment]:
        """
        Creates a list of equipment from user input to be used in Submission Type creation

        Args:
            equipmentrole (EquipmentRole): Equipment reagentrole to be added to.

        Returns:
            List[Equipment]: User selected equipment.
        """
        if isinstance(equipmentrole, str):
            equipmentrole = EquipmentRole.query(name=equipmentrole)
        equipment = cls.query()
        options = "\n".join([f"{ii}. {item.name}" for ii, item in enumerate(equipment)])
        choices = input(f"Enter equipment numbers to add to {equipmentrole.name} (space separated):\n{options}\n\n")
        output = []
        for choice in choices.split(" "):
            try:
                choice = int(choice)
            except (AttributeError, ValueError):
                continue
            output.append(equipment[choice])
        return output

    def get_processes(self, equipmentrole: str):
        output = []
        for assoc in self.equipmentequipmentroleassociation:
            if assoc.equipmentrole.name != equipmentrole:
                continue
            output.append(assoc.process.to_pydantic())
        return output


class EquipmentRoleEquipmentAssociation(BaseClass):
    
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)  #: id of associated reagent
    equipment_id = Column(INTEGER, ForeignKey("_equipment.id"), primary_key=True)  #: id of associated procedure
    process_id = Column(INTEGER, ForeignKey("_process.id"))

    _equipmentrole = relationship("EquipmentRole",
                                 back_populates="equipmentroleequipmentassociation")  #: associated procedure

    _equipment = relationship("Equipment",
                             back_populates="equipmentequipmentroleassociation")  #: associated procedure

    _process = relationship("Process",
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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'process': process})
                except Exception:
                    pass
        # Resolve equipmentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                try:
                    self._misc_info.update({'equipmentrole': equipmentrole})
                except Exception:
                    pass
        # Resolve equipment
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                try:
                    self._misc_info.update({'equipment': equipment})
                except Exception:
                    pass

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
        # return func.concat(
        #     EquipmentRole.name,
        #     "->",
        #     Equipment.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return equipmentrole_subquery + "->" + equipment_subquery
    
    @hybrid_property
    def process(self):
        return self._process

    @process.setter
    def process(self, value):
        from backend.validators.pydant import PydProcess
        match value:
            case str():
                output = Process.query(name=value, limit=1)
            case dict():
                output = Process.query_or_create(**value)
                # query_or_create returns (instance, new) — unwrap to instance if needed
                if isinstance(output, tuple):
                    output = output[0]
            case PydProcess():
                output = value.to_sql()
            case Process():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for process")
                return
        if isinstance(output, Process):
            self._process = output
        else:
            self._process = None
    
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
                # query_or_create returns (instance, new) — unwrap to instance if needed
                if isinstance(output, tuple):
                    output = output[0]
            case PydEquipment():
                output = value.to_sql()
            case Equipment():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for equipment")
                return
        if isinstance(output, Equipment):
            self._equipment = output
        else:
            logger.error(f"Could not set _equipment to {value}")
    
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
                # query_or_create returns (instance, new) — unwrap to instance if needed
                if isinstance(output, tuple):
                    output = output[0]
            case PydEquipmentRole():
                output = value.to_sql()
            case EquipmentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for equipmentrole")
        if isinstance(output, EquipmentRole):
            self._equipmentrole = output
        else:
            logger.error(f"Could not set _equipmentrole to {value}")
    
    # def details_dict(self, **kwargs) -> dict:
    #     output = super().details_dict(**kwargs)
    #     output['equipment'] = self.equipment.details_dict()
    #     output['equipment']['process'] = [item.details_dict() for item in self.process.processversion if
    #                                       bool(item.active)]
    #     return output
        
    @classmethod
    @setup_lookup
    def query(cls,
              equipment: str | Equipment | None = None,
              equipmentrole: str | EquipmentRole | None = None,
              process: str | Process | None = None,
              limit: int = 0,
              **kwargs) -> EquipmentRoleEquipmentAssociation | List[EquipmentRoleEquipmentAssociation]:
        """
        Lookup Processes

        Args:
            id (int | None, optional): Process id. Defaults to None.
            name (str | None, optional): Process name. Defaults to None.
            limit (int, optional): Maximum number of results to return (0=all). Defaults to 0.

        Returns:
            Process|List[Process]: Process(es) matching criteria
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
    A Process is a method used by a piece of equipment.
    """

    id = Column(INTEGER, primary_key=True)  #: Process id, primary key
    name = Column(String(64), unique=True)  #: Process name
    _tips = relationship("Tips", back_populates='_process',
                        secondary=process_tips)  #: relation to KitType

    _processversion = relationship("ProcessVersion", back_populates="_process")  #: relation to KitType

    _equipmentroleequipmentassociation = relationship("EquipmentRoleEquipmentAssociation", back_populates="_process", cascade="all, delete-orphan")  #: relation to EquipmentRoleEquipmentAssociation

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
        # Resolve process
        if processversion is not None:
            try:
                self.processversion = processversion
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'processversion': processversion})
                except Exception:
                    pass
        # Resolve equipmentrole
        if equipmentroleequipmentassociation is not None:
            try:
                self.equipmentroleequipmentassociation = equipmentroleequipmentassociation
            except Exception:
                try:
                    self._misc_info.update({'equipmentroleequipmentassociation': equipmentroleequipmentassociation})
                except Exception:
                    pass
        # Resolve equipment
        if tips is not None:
            try:
                self.tips = tips
            except Exception:
                try:
                    self._misc_info.update({'tips': tips})
                except Exception:
                    pass

    @hybrid_property
    def equipmentroleequipmentassociation(self):
        return self._equipmentroleequipmentassociation

    @equipmentroleequipmentassociation.setter
    def equipmentroleequipmentassociation(self, value):
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case EquipmentRoleEquipmentAssociation():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for equipmentroleequipmentassociation")
                    continue
            if isinstance(output, EquipmentRoleEquipmentAssociation):
                self._processversion.append(output)
            else:
                logger.error(f"Could not add {item} to _equipmentroleequipmentassociation")
    
    @hybrid_property
    def processversion(self):
        return self._processversion

    @processversion.setter
    def processversion(self, value):
        from backend.validators.pydant import PydProcessVersion
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = ProcessVersion.query(name=item, limit=1)
                case dict():
                    output = ProcessVersion.query_or_create(**item)
                case PydProcessVersion():
                    output = item.to_sql()
                case ProcessVersion():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for processversion")
                    continue
            if isinstance(output, ProcessVersion):
                self._processversion.append(output)
            else:
                logger.error(f"Could not add {output} to _processversion")

    @hybrid_property
    def tips(self):
        return self._tips

    @tips.setter
    def tips(self, value):
        from backend.validators.pydant import PydTips
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = Tips.query(name=item, limit=1)
                case dict():
                    output = Tips.query_or_create(**item)
                case PydTips():
                    output = item.to_sql()
                case Tips():
                    output = item
                case _:
                    logger.error(f"Unmatched value {value} for tips")
                    continue
            if isinstance(output, Tips):
                self._tips.append(output)
            else:
                logger.error(f"Could not add {output} to _tips")

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              id: int | None = None,
              proceduretype: str | ProcedureType | None = None,
              # kittype: str | KitType | None = None,
              equipmentrole: str | EquipmentRole | None = None,
              limit: int = 0,
              **kwargs) -> Process | List[Process]:
        """
        Lookup Processes

        Args:
            id (int | None, optional): Process id. Defaults to None.
            name (str | None, optional): Process name. Defaults to None.
            limit (int, optional): Maximum number of results to return (0=all). Defaults to 0.

        Returns:
            Process|List[Process]: Process(es) matching criteria
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
        super().save()

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        output['processversion'] = [item.details_dict() for item in self.processversion]
        tips = flatten_list([tipslot for tipslot in [tips.tipslot for tips in self.tips]])
        output['tips'] = [tipslot.details_dict() for tipslot in tips]
        return output


class ProcessVersion(BaseClass):

    pyd_model_name = "ProcessVersion"

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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'process': process})
                except Exception:
                    pass
        # Resolve equipmentrole
        if active is not None:
            try:
                self.active = active
            except Exception:
                try:
                    self._misc_info.update({'active': active})
                except Exception:
                    pass
        # Resolve equipment
        if date_verified is not None:
            try:
                self.date_verified = date_verified
            except Exception:
                try:
                    self._misc_info.update({'date_verified': date_verified})
                except Exception:
                    pass

    @hybrid_property
    def date_verified(self):
        return self._date_verified
    
    @date_verified.setter
    def date_verified(self, value):
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                value = dateparse(value)
        self._date_verified = value

    @hybrid_property
    def process(self):
        return self._process

    @process.setter
    def process(self, value):
        from backend.validators.pydant import PydProcess
        match value:
            case str():
                output = Process.query(name=value, limit=1)
            case dict():
                output = Process.query_or_create(**value)
            case PydProcess():
                output = value.to_sql()
            case Process():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for process")
                return
        if isinstance(output, Process):
            self._process = output
        else:
            logger.error(f"Could not set _process to {output}")
    
    @hybrid_property
    def name(self) -> str:
        if self.process is None:
            return f"Unassigned-v{str(self.version)}"
        return f"{self.process.name}-v{str(self.version)}"

    @name.expression
    def name(cls):
        # We need the Process table available in the context of the main query
        # We use a correlated approach or rely on an implicit join when filtering
        # The key is to return a SQL expression directly:
        # Use func.concat() with an explicit join to the Process table
        # return func.concat(
        #     Process.name,
        #     "-v",
        #     cast(cls.version, String)
        # ).label("name")
        process_subquery = (
            select(Process.name)
            .where(Process.id==cls.process_id)
            .correlate(cls)
            .scalar_subquery()
        )
        # Note: Can't use f strings for this for some reason.
        return process_subquery + "-v" + cast(cls.version, String)

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
                logger.error(f"Unmatched value {value} for active")
        self._active = output

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        output['name'] = self.name
        if not output['project']:
            output['project'] = ""
        output['tips'] = flatten_list(
            [[lot.details_dict() for lot in tips.tipslot if bool(lot.active)] for tips in self.process.tips])
        return output

    @classmethod
    def query(cls,
              version: str | float | None = None,
              name: str | None = None,
              limit: int = 0,
              active: bool | int | None = None,
              **kwargs) -> ProcessVersion | List[ProcessVersion]:
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
    An abstract reagentrole that a tip fills during a process
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _tipslot = relationship("TipsLot", back_populates="_tips", cascade="all, delete-orphan")  #: concrete instance of this tip type
    manufacturer = Column(String(64))  #: Name of manufacturer
    capacity = Column(INTEGER)  #: How many uL the tip can hold.
    ref = Column(String(64))  #: tip reference number
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
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve process
        if process is not None:
            try:
                self.process = process
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'process': process})
                except Exception:
                    pass
        # Resolve equipmentrole
        if tipslot is not None:
            try:
                self.tipslot = tipslot
            except Exception:
                try:
                    self._misc_info.update({'tipslot': tipslot})
                except Exception:
                    pass

    @hybrid_property
    def process(self):
        return self._process

    @process.setter
    def process(self, value):
        from backend.validators.pydant import PydProcess
        if value is None:
            value = []
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = Process.query(name=item, limit=1)
                case dict():
                    output = Process.query_or_create(**item)
                case PydProcess():
                    output = item.to_sql()
                case Process():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for process")
                    continue
            if isinstance(output, Process):
                self._process.append(output)
            else:
                logger.error(f"Could not add {item} to _process")
    
    @hybrid_property
    def tipslot(self):
        return self._tipslot

    @tipslot.setter
    def tipslot(self, value):
        from backend.validators.pydant import PydTipsLot
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match item:
                case str():
                    output = TipsLot.query(name=item, limit=1)
                case dict():
                    output = TipsLot.query_or_create(**item)
                case PydTipsLot():
                    output = item.to_sql()
                case TipsLot():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for tipslot")
                    continue
            if isinstance(output, TipsLot):
                self._tipslot.append(output)
            else:
                logger.error(f"Could not add {output} to _tipslot")

    @hybrid_property
    def name(self):
        return f"{self.manufacturer}-{self.ref} ({self.capacity})"

    @name.expression
    def name(cls):
        return func.concat(cls.manufacturer, '-', cls.ref, "(", cast(cls.capacity, String), ")"
        ).label("name")

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              manufacturer: str | None = None,
              capacity: str | None = None,
              ref: str | None = None,
              limit: int = 0,
              **kwargs) -> Tips | List[Tips]:
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
        super().save()

    
class TipsLot(BaseClass, LogMixin):
    """
    A concrete instance of tips.
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    _tips = relationship("Tips", back_populates="_tipslot")  #: joined parent tip type
    tips_id = Column(INTEGER, ForeignKey("_tips.id", ondelete='SET NULL',
                                         name="fk_tips_id"))  #: id of parent tip type
    lot = Column(String(64), unique=True)  #: lot number
    _expiry = Column(TIMESTAMP)  #: date of expiry
    _active = Column(INTEGER, default=1)  #: whether or not these tips are currently in use.
    procedureequipmenttipslotassociation = relationship("ProcedureEquipmentTipslotAssociation", 
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
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if tips is not None:
            try:
                self.tips = tips
            except Exception:
                try:
                    self._misc_info.update({'tips': tips})
                except Exception:
                    pass
        if expiry is not None:
            try:
                self.expiry = expiry
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'expiry': expiry})
                except Exception:
                    pass
        # Resolve reagentrole
        if active is not None:
            try:
                self.active = active
            except Exception:
                try:
                    self._misc_info.update({'active': active})
                except Exception:
                    pass

    @hybrid_property
    def expiry(self) -> str:
        return self._expiry

    @expiry.setter
    def expiry(value):
        self._expiry = value
    
    @hybrid_property
    def tips(self):
        return self._tips

    @tips.setter
    def tips(self, value):
        from backend.validators.pydant import PydTips
        match value:
            case str():
                output = Tips.query(name=value, limit=1)
            case dict():
                output = Tips.query_or_create(**value)
            case PydTips():
                output = value.to_sql()
            case Tips():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for tips")
                return
        if isinstance(output, Tips):
            self._tips = output
        else:
            logger.error(f"Could not set _tips to {output}")
    
    @property
    def size(self) -> str:
        return f"{self.capacity}ul"

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
        return f"{manufacturer}-{ref}-{self.lot}"

    @name.expression
    def name(cls):
        # We need the Process table available in the context of the main query
        # We use a correlated approach or rely on an implicit join when filtering
        # The key is to return a SQL expression directly:
        # Use func.concat() with an explicit join to the Process table
        # return func.concat(
        #     Tips.manufacturer,
        #     "-",
        #     Tips.ref,
        #     "-",
        #     cast(cls.lot, String)
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return tipsman_subquery + "-" + tipsref_subquery + "-" + cast(cls.lot, String)

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

    @classmethod
    def query(cls,
              manufacturer: str | None = None,
              ref: str | None = None,
              lot: str | None = None,
              limit: int = 0,
              **kwargs) -> Tips | List[Tips]:
        """
        Lookup tips

        Args:
            manufacturer (str | None, optional): Name of parent tip manufacturer. Defaults to None.
            ref (str | None, optional): Name of parent tip reference number. Defaults to None.
            lot (str | None, optional): Lot number. Defaults to None.
            limit (int, optional): Maximum number of results to return (0=all). Defaults to 0.

        Returns:
            Tips | List[Tips]: Tips matching criteria
        """
        query = cls.__database_session__.query(cls)
        if manufacturer is not None and ref is not None:
            manufacturer = None
        match manufacturer:
            case str():
                # logger.debug(f"Looking for {manufacturer}")
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
        super().save()

    def details_dict(self, **kwargs) -> dict:
        output = super().details_dict()
        output['name'] = self.name
        return output


class ProcedureEquipmentTipslotAssociation(BaseClass):

    procedure_id = Column(
        INTEGER,
        ForeignKey("_procedureequipmentassociation.procedure_id"),
        primary_key=True
    )
    equipment_id = Column(
        INTEGER,
        ForeignKey("_procedureequipmentassociation.equipment_id"),
        primary_key=True
    )
    equipmentrole_id = Column(
        INTEGER,
        ForeignKey("_procedureequipmentassociation.equipmentrole_id"),
        primary_key=True
    )
    tipslot_id = Column(
        INTEGER,
        ForeignKey("_tipslot.id"),
        primary_key=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["procedure_id", "equipment_id", "equipmentrole_id"],
            [
                "_procedureequipmentassociation.procedure_id",
                "_procedureequipmentassociation.equipment_id",
                "_procedureequipmentassociation.equipmentrole_id",
            ],
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
        back_populates="procedureequipmenttipslotassociation",
        foreign_keys=[tipslot_id]
    )


class ProcedureEquipmentAssociation(BaseClass):
    """
    Abstract association between BasicRun and Equipment
    """

    equipment_id = Column(INTEGER, ForeignKey("_equipment.id"), primary_key=True)  #: id of associated equipment
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)
    processversion_id = Column(INTEGER, ForeignKey("_processversion.id", ondelete="SET NULL",
                                                   name="SEA_Process_id"))  #: Foreign key of process id
    _start_time = Column(TIMESTAMP)  #: start time of equipment use
    _end_time = Column(TIMESTAMP)  #: end time of equipment use
    comments = Column(String(1024))  #: comments about equipment

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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        # Resolve reagentrole
        if equipment is not None:
            try:
                self.equipment = equipment
            except Exception:
                try:
                    self._misc_info.update({'equipment': equipment})
                except Exception:
                    pass
        if processversion is not None:
            try:
                self.processversion = processversion
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'processversion': processversion})
                except Exception:
                    pass
        # Resolve reagentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                try:
                    self._misc_info.update({'equipmentrole': equipmentrole})
                except Exception:
                    pass
        # Resolve reagentrole
        if tipslot is not None:
            try:
                self.tipslot = tipslot
            except Exception:
                try:
                    self._misc_info.update({'tipslot': tipslot})
                except Exception:
                    pass

    # def __repr__(self) -> str:
    #     try:
    #         return f"<ProcedureEquipmentAssociation({self.name})>"
    #     except AttributeError:
    #         return "<ProcedureEquipmentAssociation(Unknown)>"

    @hybrid_property
    def tipslot(self):
        return self._tipslot

    @tipslot.setter
    def tipslot(self, value):
        from backend.validators.pydant import PydTipsLot
        if not isinstance(value, list):
            value = [value]
        for item in value:
            match value:
                case str():
                    output = TipsLot.query(name=item, limit=1)
                case dict():
                    output = TipsLot.query_or_create(**item)
                case PydTipsLot():
                    output = value.to_sql()
                case TipsLot():
                    output = value
                case _:
                    logger.error(f"Unmatched value {item} for tipslot")
                    continue
            if isinstance(output, TipsLot):
                self._tipslot.append(output)
            else:
                logger.error(f"Could not add {item} to _tipslot")
    
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
                output = value.to_sql()
            case EquipmentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for equipmentrole.")
                return
        if isinstance(output, EquipmentRole):
            self._equipmentrole =output
        else:
            logger.error(f"Could not set _equipmentrole to {output}")
    
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
                output = value.to_sql()
            case Equipment():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for equipment")
                return
        if isinstance(output, Equipment):
            self._equipment = output
        else:
            logger.error(f"Could not set _equipment to {output}")
    
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
                output = value.to_sql()
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for procedure")
                return
        if isinstance(output, Procedure):
            self._procedure = output
        else:
            logger.error(f"Could not set _procedure to {output}")
    
    @hybrid_property
    def processversion(self):
        return self._processversion

    @processversion.setter
    def processversion(self, value):
        from backend.validators.pydant import PydProcessVersion
        error_msg = f"Can't add item {value} to {self.name}._processversion"
        match value:
            case str():
                output = ProcessVersion.query(name=value, limit=1)
            case dict():
                output = ProcessVersion.query_or_create(**value)
            case PydProcessVersion():
                output = value.to_sql()
            case ProcessVersion():
                output = value
            case _:
                output = None
        if isinstance(output, ProcessVersion):
            self._processversion = output
        else:
            self._processversion = None
    
    @hybrid_property
    def name(self):
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
        # return func.concat(
        #     Procedure.name,
        #     "->",
        #     Equipment.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return procedure_subquery + "->" + equipment_subquery

    @property
    def process(self):
        return ProcessVersion.query(id=self.processversion_id)

    @property
    def tips(self):
        try:
            return TipsLot.query(id=self.tipslot_id, limit=1)
        except AttributeError:
            return None

    def to_sub_dict(self) -> dict:
        """
        This RunEquipmentAssociation as a dictionary

        Returns:
            dict: This RunEquipmentAssociation as a dictionary
        """
        try:
            process = self.process.name
        except AttributeError:
            process = "No process found"
        output = dict(name=self.equipment.name, asset_number=self.equipment.asset_number, comment=self.comments,
                      processes=[process], role=self.equipmentrole, nickname=self.equipment.nickname)
        return output

    def to_pydantic(self) -> PydEquipment:
        """
        Returns a pydantic model based on this object.

        Returns:
            PydEquipment: pydantic equipment model
        """
        from backend.validators import PydEquipment
        output = PydEquipment(**self.details_dict())
        output.tips = self.tips.to_pydantic(pyd_model_name="PydTips")
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

        Args:
            equipment ( int | Equipment | None, optional): The associated equipment of interest. Defaults to None.
            procedure ( int | Procedure | None, optional): The associated procedure of interest. Defaults to None.
            equipmentrole ( str | None, optional): The associated equipmentrole. Defaults to None.
            limit ( int ): Maximum number of results to return (0=all). Defaults to 0.
            **kwargs ():

        Returns:
            Any | List[Any]
        """
        query: Query = cls.__database_session__.query(cls)
        match equipment:
            case int():
                query = query.filter(cls.equipment_id == equipment)
            case Equipment():
                query = query.filter(cls.equipment == equipment)
            case _:
                pass
        match procedure:
            case int():
                query = query.filter(cls.procedure_id == procedure)
            case Procedure():
                query = query.filter(cls.procedure == procedure)
            case _:
                pass
        if equipmentrole is not None:
            query = query.filter(cls.equipmentrole == equipmentrole)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    def details_dict(self, **kwargs):
        output = super().details_dict()
        # NOTE: Figure out how to merge the misc_info if doing .update instead.
        relevant = {k: v for k, v in output.items() if k not in ['equipment']}
        output = output['equipment'].details_dict()
        misc = output['misc_info']
        output.update(relevant)
        output['misc_info'] = misc
        output['equipment_role'] = self.equipmentrole.name
        output['processes'] = [item for item in self.equipment.get_processes(equipmentrole=output['equipment_role'])]
        try:
            output['processversion'] = self.processversion.details_dict()
        except AttributeError:
            output['processversion'] = None
        try:
            output['tips'] = self.tipslot.details_dict()
        except AttributeError as e:
            output['tips'] = None
        return output


class ProcedureTypeEquipmentRoleAssociation(BaseClass):
    """
    Abstract association between SubmissionType and EquipmentRole
    """
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)  #: id of associated equipment
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"), primary_key=True)  #: id of associated procedure
    _static = Column(INTEGER, default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?
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
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if equipmentrole is not None:
            try:
                self.equipmentrole = equipmentrole
            except Exception:
                try:
                    self._misc_info.update({'equipmentrole': equipmentrole})
                except Exception:
                    pass

    @hybrid_property
    def static(self):
        return bool(self._static)
    
    @static.setter
    def static(self, value):
        match value:
            case int():
                self._static = value
            case bool():
                self._static = int(value)
            case str():
                if value.lower() in ['true', '1', 'yes', 'on']:
                    self._static = 1
                elif value.lower() in ['false', '0', 'no', 'off']:
                    self._static = 0
                else:
                    raise ValueError(f"Cannot convert string {value} to boolean for {self.name}._static")
            case _:
                raise TypeError(f"Unsupported type {type(value)} for {self.name}._static")

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
        # return func.concat(
        #     ProcedureType.name,
        #     "->",
        #     EquipmentRole.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
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
                output = value.to_sql()
            case ProcedureType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for proceduretype")
                return
        if isinstance(output, ProcedureType):
            self._proceduretype =output
        else:
            logger.error(f"Could not set _proceduretype to {output}")
    
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
                output = value.to_sql()
            case EquipmentRole():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for equipmentrole")
                return
        if isinstance(output, EquipmentRole):
            self._equipmentrole =output
        else:
            logger.error(f"Could not set _equipmentrole to {output}")
            
    @classproperty
    def aliases(cls):
        return super().aliases + ['equipmentroleproceduretypeassociation']
    
    @check_authorization
    def save(self):
        super().save()

    @classmethod
    @setup_lookup
    def query(cls,
              proceduretype: str | ProcedureType | None = None,
              equipmentrole: str | EquipmentRole | None = None,
              limit: int = 0,
              **kwargs) -> ProcedureTypeEquipmentRoleAssociation | List[ProcedureTypeEquipmentRoleAssociation]:
        """
        Lookup Processes

        Args:
            id (int | None, optional): Process id. Defaults to None.
            name (str | None, optional): Process name. Defaults to None.
            limit (int, optional): Maximum number of results to return (0=all). Defaults to 0.

        Returns:
            Process|List[Process]: Process(es) matching criteria
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

    id = Column(INTEGER, primary_key=True)  #: primary key
    result = Column(JSON)  #:
    _date_analyzed = Column(TIMESTAMP)
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id", ondelete='SET NULL',
                                              name="fk_RES_procedure_id"))
    _procedure = relationship("Procedure", back_populates="_results")
    assoc_id = Column(INTEGER, ForeignKey("_proceduresampleassociation.id", ondelete='SET NULL',
                                          name="fk_RES_ASSOC_id"))
    _sampleprocedureassociation = relationship("ProcedureSampleAssociation", back_populates="_results")
    _img = Column(String(128))

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
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if procedure is not None:
            try:
                self.procedure = procedure
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'procedure': procedure})
                except Exception:
                    pass
        # Resolve reagentrole
        if date_analyzed is not None:
            try:
                self.date_analyzed = date_analyzed
            except Exception:
                try:
                    self._misc_info.update({'date_analyzed': date_analyzed})
                except Exception:
                    pass
        if sampleprocedureassociation is not None:
            try:
                self.sampleprocedureassociation = sampleprocedureassociation
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'sampleprocedureassociation': sampleprocedureassociation})
                except Exception:
                    pass
        # Resolve reagentrole
        if image is not None:
            try:
                self.image = image
            except Exception:
                pass
        # Resolve reagentrole
        if resultstype is not None:
            try:
                self.resultstype = resultstype
            except Exception:
                try:
                    self._misc_info.update({'date_analyzed': resultstype})
                except Exception:
                    pass

    # TODO: Enable query from sample_association in addition to procedure

    @hybrid_property
    def name(self):
        try:
            assoc = self.procedure.name
        except AttributeError:
            assoc = "Unassigned Results Association"
        try:
            resultstype = self.resultstype.name
        except AttributeError:
            resultstype = "Unassigned ResultsType"
        return f"{assoc}-{resultstype}"
    
    @name.expression
    def name(cls):
        # return func.concat(
        #     Procedure.name,
        #     "-",
        #     ResultsType.name
        # ).label("name")
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
        # Note: Can't use f strings for this for some reason.
        return procedure_subquery + "->" + resultstype_subquery

    @hybrid_property
    def date_analyzed(self):
        return self._date_analyzed
    
    @date_analyzed.setter
    def date_analyzed(self, value):
        match value:
            case datetime():
                pass
            case date():
                value = datetime.combine(value, time=datetime.now(tz=timezone).time())
            case str():
                value = dateparse(value)
            case _:
                logger.error(f"Unmatched value {value} for date_analyzed.")
                value = datetime.combine(date.today(), datetime.max.time())
        self._date_analyzed = value

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
                output = value.to_sql()
            case ResultsType():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for resultstype")
                return
        if isinstance(output, ResultsType):
            self._resultstype = output
        else:
            logger.error(f"Could not set _resultstype to {output}")
    
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
                output = value.to_sql()
            case Procedure():
                output = value
            case _:
                logger.error(f"Unmatched value {value} for procedure")
                return
        if isinstance(output, Procedure):
            self._procedure =output
        else:
            logger.error(f"Could not set _procedure to {output}")
    
    @property
    def sample_id(self):
        if self.assoc_id:
            return self.sampleprocedureassociation.sample.sample_id
        else:
            return None

    @property
    def image(self) -> bytes | None:
        dir = self.__directory_path__.joinpath("submission_imgs.zip")
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

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs):
        output = super().to_pydantic(pyd_model_name=pyd_model_name, **kwargs)
        if bool(self.sample_id):
            output.sample = self._sampleprocedureassociation.name
        return output


class ResultsType(BaseClass):

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))
    _results = relationship("Results", back_populates="_resultstype", cascade="all, delete-orphan")
    _proceduretype = relationship(ProcedureType, back_populates="_resultstype", secondary=proceduretype_resulttype)

    def __init__(self, *args, **kwargs):
        """
        Resolve shorthand inputs (strings/dicts) for proceduretype and reagentrole
        into actual model instances before setting attributes. This allows callers
        to pass names like 'Omega Bacterial Extraction' and have the association
        properly wired.
        """
        results = kwargs.pop('results', None)
        proceduretype = kwargs.pop('proceduretype', None)
        # Call SQLAlchemy/dataclass init first to avoid missing internal setup
        super().__init__(*args, **kwargs)
        # Resolve proceduretype
        if proceduretype is not None:
            try:
                self.proceduretype = proceduretype
            except Exception:
                # fallback: store in misc_info if setter fails
                try:
                    self._misc_info.update({'proceduretype': proceduretype})
                except Exception:
                    pass
        # Resolve reagentrole
        if results is not None:
            try:
                self.results = results
            except Exception:
                try:
                    self._misc_info.update({'results': results})
                except Exception:
                    pass

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
        for item in value:
            match item:
                case str():
                    output = ProcedureType.query(name=item, limit=1)
                case dict():
                    output = {ProcedureType}.query_or_create(**item)
                case PydProcedureType():
                    output = item.to_sql()
                case Results():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for proceduretype")
                    continue
            if isinstance(output, ProcedureType):
                if output not in self._proceduretype:
                    self._results.append(output)
            else:
                logger.error(f"Could not add {output} to _proceduretype")

    @hybrid_property
    def results(self):
        return self._results

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
                    output = PydResults.query(name=item, limit=1)
                case dict():
                    output = PydResults.query_or_create(**item)
                case PydResults():
                    output = item.to_sql()
                case Results():
                    output = item
                case _:
                    logger.error(f"Unmatched value {item} for results")
                    continue
            if isinstance(output, Results):
                self._results.append(output)
            else:
                logger.error(f"Could not add {output} to _results")
    