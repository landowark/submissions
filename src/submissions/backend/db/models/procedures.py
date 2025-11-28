"""
All kittype and reagent related models
"""
from __future__ import annotations

import sys
import zipfile, logging, re, numpy as np
from operator import itemgetter
from pathlib import Path
from pprint import pformat
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship, validates, Query, declared_attr
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date, datetime, timedelta
from tools import check_authorization, setup_lookup, Report, Alert, check_regex_match, timezone, \
    jinja_template_loading, flatten_list
from typing import List, Literal, Generator, Any, Tuple, TYPE_CHECKING
from . import BaseClass, ClientLab, LogMixin
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError

if TYPE_CHECKING:
    from backend.db.models.submissions import Run, ProcedureSampleAssociation
    from backend.validators.pydant import PydSample

logger = logging.getLogger(f'submissions.{__name__}')

proceduretype_resulttype = Table(
    "_proceduretype_resulttype",
    BaseClass.__base__.metadata,
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    Column("resulttype_id", INTEGER, ForeignKey("_resulttype.id")),
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

    skip_on_edit = False
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), unique=True)  #: name of reagentrole reagent plays
    # reagent = relationship("Reagent", back_populates="reagentrole",
    #                        secondary=reagentrole_reagent)  #: concrete control of this reagent type
    reagentroleproceduretypeassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        back_populates="reagentrole",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    proceduretype = association_proxy("reagentroleproceduretypeassociation", "proceduretype",
                                      creator=lambda proceduretype: ProcedureTypeReagentRoleAssociation(
                                          proceduretype=proceduretype))  #: Association proxy to KitTypeReagentRoleAssociation

    reagentrolereagentassociation = relationship(
        "ReagentRoleReagentAssociation",
        back_populates="reagentrole",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    reagent = association_proxy("reagentrolereagentassociation", "reagent",
                                      creator=lambda reagent: ReagentRoleReagentAssociation(
                                          reagent=reagent))  #: Association proxy to KitTypeReagentRoleAssociation

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[ReagentRole, bool]:
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
        if (proceduretype is not None and reagent is None) or (reagent is not None and proceduretype is None):
            raise ValueError("Cannot filter without both reagent and kittype type.")
        elif proceduretype is None and reagent is None:
            pass
        else:
            match proceduretype:
                case str():
                    proceduretype = ProcedureType.query(name=proceduretype)
                case _:
                    pass
            match reagent:
                case str():
                    reagent = Reagent.query(lot=reagent)
                case _:
                    pass
            assert reagent.role
            # NOTE: Get all roles common to the reagent and the kittype.
            result = set(proceduretype.reagentrole).intersection(reagent.role)
            return next((item for item in result), None)
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

    skip_on_edit = False
    id = Column(INTEGER, primary_key=True)  #: primary key
    # reagentrole = relationship("ReagentRole", back_populates="reagent",
    #                            secondary=reagentrole_reagent)  #: joined parent ReagentRole
    # reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id", ondelete='SET NULL',
    #                                             name="fk_REG_reagent_role_id"))  #: id of parent ReagentRole
    eol_ext = Column(Interval())  #: extension of life interval
    name = Column(String(64), unique=True)  #: reagent name
    cost_per_ml = Column(FLOAT(2))  #: amount a millilitre of reagent costs
    reagentlot = relationship("ReagentLot", back_populates="reagent")

    reagentreagentroleassociation = relationship(
        "ReagentRoleReagentAssociation",
        back_populates="reagent",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation
    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    reagentrole = association_proxy("reagentrolereagentassociation", "reagentrole",
                                      creator=lambda reagentrole: ReagentRoleReagentAssociation(
                                          reagentrole=reagentrole))  #: Association proxy to KitTypeReagentRoleAssociation

    def __repr__(self):
        if self.name:
            name = f"<Reagent({self.name})>"
        else:
            name = f"<Reagent({self.reagentrole.name})>"
        return name

    def __init__(self, name: str, eol_ext: timedelta = timedelta(0), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.eol_ext = eol_ext

    @classmethod
    @declared_attr
    def searchables(cls):
        return [dict(label="Lot", field="lot")]

    def update_last_used(self, proceduretype: ProcedureType) -> Report:
        """
        Updates last used reagent lot for ReagentType/KitType

        Args:
            proceduretype (ProcedureType): ProcedureType this instance is used in.

        Returns:
            Report: Result of operation
        """
        report = Report()
        rt = ReagentRole.query(proceduretype=proceduretype, reagent=self, limit=1)
        if rt is not None:
            assoc = ProcedureTypeReagentRoleAssociation.query(proceduretype=proceduretype, reagentrole=rt)
            if assoc is not None:
                if assoc.last_used != self.lot:
                    assoc.last_used = self.lot
                    result = assoc.save()
                    report.add_result(result)
                    return report
        report.add_result(Result(msg=f"Updating last used {rt} was not performed.", status="Information"))
        return report

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
                query = query.join(cls.reagentrole).filter(ReagentRole.name == reagentrole)
            case ReagentRole():
                query = query.filter(cls.reagentrole.contains(reagentrole))
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

    def set_attribute(self, key, value):
        match key:
            case "lot":
                value = value.upper()
            case "reagentrole":
                match value:
                    case ReagentRole():
                        role = value
                    case str():
                        role = ReagentRole.query(name=value, limit=1)
                    case _:
                        return
                if role and role not in self.reagentrole:
                    self.reagentrole.append(role)
                return
            case "comment":
                return
            case _:
                pass
        try:
            self.__setattr__(key, value)
        except AttributeError as e:
            logger.error(f"Could not set {key} due to {e}")

    def details_dict(self, reagentrole: str | None = None, **kwargs):
        output = super().details_dict()
        if reagentrole:
            output['reagentrole'] = reagentrole
        else:
            output['reagentrole'] = self.reagentrole[0].name
        return output

    @property
    def lot_dicts(self):
        return [dict(name=self.name, lot=lot.lot, expiry=lot.expiry + self.eol_ext) for lot in self.reagentlot]


class ReagentLot(BaseClass):

    id = Column(INTEGER, primary_key=True)  #: primary key
    lot = Column(String(64), unique=True)  #: lot number of reagent
    expiry = Column(TIMESTAMP)  #: expiry date - extended by eol_ext of parent programmatically
    active = Column(INTEGER, default=1)
    reagent_id = Column(INTEGER, ForeignKey("_reagent.id", ondelete='SET NULL',
                                            name="fk_REGLOT_reagent_id"))  #: id of parent reagent type
    reagent = relationship("Reagent", back_populates="reagentlot")  #: joined parent reagent type

    reagentlotprocedureassociation = relationship(
        "ProcedureReagentLotAssociation",
        back_populates="reagentlot",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    procedures = association_proxy("reagentlotprocedureassociation", "procedure",
                                   creator=lambda procedure: ProcedureReagentLotAssociation(
                                       procedure=procedure))  #: Association proxy to ClientSubmissionSampleAssociation.sample

    @hybrid_property
    def name(self):
        return self.lot

    @classmethod
    def query(cls,
              lot: str | None = None,
              name: str | None = None,
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
        match name:
            case str():
                query = query.join(Reagent).filter(Reagent.name == name)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def __repr__(self):
        return f"<Lot({self.lot}-{self.expiry}>"

    def set_attribute(self, key, value):
        match key:
            case "expiry":
                if isinstance(value, str):
                    value = date(year=1970, month=1, day=1)
                # NOTE: if min time is used, any reagent set to expire today (Bac postive control, eg) will have expired at midnight and therefore be flagged.
                # NOTE: Make expiry at date given, plus maximum time = end of day
                value = datetime.combine(value, datetime.max.time())
                value = value.replace(tzinfo=timezone)
            case _:
                pass
        setattr(self, key, value)

    @check_authorization
    def edit_from_search(self, obj, **kwargs):
        from frontend.widgets.omni_add_edit import AddEdit
        from backend.validators.pydant import PydElastic
        dlg = AddEdit(parent=None, instance=self, disabled=['reagent'])
        if dlg.exec():
            pyd = dlg.parse_form()
            logger.debug(f"Pydantic returned: {type(pyd)} {pyd.model_fields}")
            fields = pyd.model_fields
            if isinstance(pyd, PydElastic):
                fields.update(pyd.model_extra)
            for field in fields:
                if field in ['instance']:
                    continue
                field_value = pyd.__getattribute__(field)
                logger.debug(f"Setting {field} in Reagent Lot to {field_value}")
                self.set_attribute(field, field_value)
            self.save()

    def details_dict(self, **kwargs) -> dict:
        output = super().details_dict(**kwargs)
        output['excluded'] += ["reagentlotprocedureassociation", "procedures"]
        output['reagent'] = output['reagent'].name
        return output


class Discount(BaseClass):
    """
    Relationship table for client labs for certain kits.
    """

    skip_on_edit = True

    id = Column(INTEGER, primary_key=True)  #: primary key
    proceduretype = relationship("ProcedureType")  #: joined parent proceduretype
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete='SET NULL',
                                                  name="fk_DIS_procedure_type_id"))  #: id of joined proceduretype
    clientlab = relationship("ClientLab")  #: joined client lab
    clientlab_id = Column(INTEGER,
                          ForeignKey("_clientlab.id", ondelete='SET NULL',
                                     name="fk_DIS_org_id"))  #: id of joined client
    description = Column(String(128))  #: Short description
    amount = Column(FLOAT(2))  #: Dollar amount of discount

    @hybrid_property
    def name(self) -> str:
        return self.description
    
    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object
        """
        return f"<Discount({self.name})>"

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
                query = query.filter(cls.clientlab == clientlab)
            case str():
                query = query.join(ClientLab).filter(ClientLab.name == clientlab)
            case int():
                query = query.join(ClientLab).filter(ClientLab.id == clientlab)
            case _:
                pass
        match proceduretype:
            case ProcedureType():
                query = query.filter(cls.proceduretype == proceduretype)
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
    clientsubmission = relationship("ClientSubmission",
                                    back_populates="submissiontype")  #: Instances of this submission type
    proceduretype = relationship("ProcedureType", back_populates="submissiontype",
                                 secondary=submissiontype_proceduretype)  #: Procedures associated with this submission type

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object.
        """
        return f"<SubmissionType({self.name})>"

    @classmethod
    @declared_attr
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
    # allowed_result_methods = Column(JSON)
    plate_cost = Column(FLOAT(2))

    procedure = relationship("Procedure",
                             back_populates="proceduretype")  #: Concrete control of this type.

    submissiontype = relationship("SubmissionType", back_populates="proceduretype",
                                  secondary=submissiontype_proceduretype)  #: run this kittype was used for

    resultstype = relationship("ResultsType", back_populates="proceduretype",
                                  secondary=proceduretype_resultstype)  #: run this kittype was used for
    
    proceduretypeequipmentroleassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="proceduretype",
        cascade="all, delete-orphan"
    )  #: Association of equipmentroles

    equipmentrole = association_proxy("proceduretypeequipmentroleassociation", "equipmentrole",
                                      creator=lambda eq: ProcedureTypeEquipmentRoleAssociation(
                                          equipmentrole=eq))  #: Proxy of equipmentrole associations

    proceduretypereagentroleassociation = relationship(
        "ProcedureTypeReagentRoleAssociation",
        back_populates="proceduretype",
        cascade="all, delete-orphan"
    )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes

    reagentrole = association_proxy("proceduretypereagentroleassociation", "reagentrole",
                                    creator=lambda reagentrole: ProcedureTypeReagentRoleAssociation(
                                        reagentrole=reagentrole))  #: Proxy of equipmentrole associations

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

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        output['reagentrole'] = [item.details_dict() for item in output['reagentrole']]
        output['equipment'] = [item.details_dict(proceduretype=self) for item in output['equipmentrole']]
        return output

    def construct_dummy_procedure(self, run: Run | None = None):
        from backend.validators.pydant import PydProcedure
        if run:
            samples = run.constuct_sample_dicts_for_proceduretype(proceduretype=self)
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
        # NOTE: An overly complicated list comprehension create a list of sample locations
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
    repeat_of = relationship("Procedure", remote_side=[id])
    started_date = Column(TIMESTAMP)
    completed_date = Column(TIMESTAMP)
    technician = Column(String(64))  #: name of processing tech(s)
    results = relationship("Results", back_populates="procedure", uselist=True)
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete="SET NULL",
                                                  name="fk_PRO_proceduretype_id"))  #: client lab id from _organizations))
    proceduretype = relationship("ProcedureType", back_populates="procedure")
    run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="SET NULL",
                                        name="fk_PRO_basicrun_id"))  #: client lab id from _organizations))
    run = relationship("Run", back_populates="procedure")
    # control = relationship("Control", back_populates="procedure", uselist=True)  #: A control sample added to procedure

    proceduresampleassociation = relationship(
        "ProcedureSampleAssociation",
        back_populates="procedure",
        cascade="all, delete-orphan",
    )

    sample = association_proxy("proceduresampleassociation",
                               "sample", creator=lambda sample: ProcedureSampleAssociation(sample=sample)
                               )

    procedurereagentlotassociation = relationship(
        "ProcedureReagentLotAssociation",
        back_populates="procedure",
        cascade="all, delete-orphan",
    )  #: Relation to ProcedureReagentAssociation

    reagentlot = association_proxy("procedurereagentlotassociation",
                                   "reagentlot", creator=lambda reg: ProcedureReagentLotAssociation(
            reagent=reg))  #: Association proxy to RunReagentAssociation.reagent

    procedureequipmentassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="procedure",
        cascade="all, delete-orphan"
    )  #: Relation to Equipment

    equipment = association_proxy("procedureequipmentassociation",
                                  "equipment")  #: Association proxy to RunEquipmentAssociation.equipment

    @hybrid_property
    def repeat(self) -> bool:
        return self.repeat_of is not None

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

    def details_dict(self, **kwargs):
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

    def create_proceduresampleassociations(self, sample):
        from backend.db.models import ProcedureSampleAssociation
        return ProcedureSampleAssociation(procedure=self, sample=sample)

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
    uses = Column(JSON)  #: map to location on excel sheets of different procedure types
    required = Column(INTEGER)  #: whether the reagent type is required for the kittype (Boolean 1 or 0)
    last_used = Column(String(32))  #: last used lot number of this type of reagent
    

    # NOTE: reference to the "ReagentType" object
    reagentrole = relationship(ReagentRole,
                               back_populates="reagentroleproceduretypeassociation")  #: relationship to associated ReagentType

    # NOTE: reference to the "SubmissionType" object
    proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypereagentroleassociation")  #: relationship to associated SubmissionType

    def __init__(self, proceduretype=None, reagentrole=None, uses=None, required=1):
        self.proceduretype = proceduretype
        self.reagentrole = reagentrole
        self.uses = uses
        self.required = required

    def __repr__(self) -> str:
        return f"<ProcedureTypeReagentRoleAssociation({self.proceduretype} & {self.reagentrole})>"

    @property
    def name(self):
        try:
            return f"{self.proceduretype.name} -> {self.reagentrole.name}"
        except AttributeError:
            return "Blank ProcedureTypeReagentRole"

    @validates('required')
    def validate_required(self, key, value):
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
        if isinstance(value, bool):
            value = int(value)
        if not 0 <= value < 2:
            raise ValueError(f'Invalid required value {value}. Must be 0 or 1.')
        return value

    @validates('reagentrole')
    def validate_reagentrole(self, key, value):
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
        if not isinstance(value, ReagentRole):
            raise ValueError(f'{value} is not a reagentrole')
        return value

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
            logger.debug(f"Key: {k} has value: {v}")
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
    # reagentrole = Column(String(64))  #: Name of associated reagentrole (for some reason can't be relationship).
    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id"), primary_key=True)
    comments = Column(String(1024))  #: Comments about reagents

    procedure = relationship("Procedure",
                             back_populates="procedurereagentlotassociation")  #: associated procedure

    reagentlot = relationship(ReagentLot, back_populates="reagentlotprocedureassociation")  #: associated reagent

    reagentrole = relationship(ReagentRole)

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this RunReagentAssociation
        """
        try:
            return f"<ProcedureReagentLotAssociation({self.procedure.name} & {self.reagent.lot})>"
        except AttributeError:
            try:
                logger.error(f"Reagent {self.reagent.lot} procedure association {self.reagent_id} has no procedure!")
            except AttributeError:
                return "<ProcedureReagentAssociation(Unknown Submission & Unknown Reagent)>"
            return f"<ProcedureReagentAssociation(Unknown Submission & {self.reagent.lot})>"

    def __init__(self, reagentlot=None, procedure=None, reagentrole=""):
        if isinstance(reagentlot, list):
            logger.warning(f"Got list for reagent. Likely no lot was provided. Using {reagentlot[0]}")
            reagentlot = reagentlot[0]
        self.reagentlot = reagentlot
        self.procedure = procedure
        self.reagentrole = reagentrole
        self.comments = ""

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
    # reagentrole = Column(String(64))  #: Name of associated reagentrole (for some reason can't be relationship).
    ml_used_per_sample = Column(FLOAT(3))  #: amount of reagent used for this role.
    
    reagent = relationship("Reagent", back_populates="reagentreagentroleassociation")  #: associated procedure

    reagentrole = relationship(ReagentRole, back_populates="reagentrolereagentassociation")  #: associated reagent


class EquipmentRole(BaseClass):
    """
    Abstract roles for equipment
    """

    id = Column(INTEGER, primary_key=True)  #: Role id, primary key
    name = Column(String(32))  #: Common name

    equipmentroleproceduretypeassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="equipmentrole",
        cascade="all, delete-orphan",
    )  #: relation to SubmissionTypes

    proceduretype = association_proxy("equipmentroleproceduretypeassociation",
                                      "proceduretype")  #: proxy to equipmentroleproceduretypeassociation.proceduretype

    equipmentroleequipmentassociation = relationship(
        "EquipmentRoleEquipmentAssociation",
        back_populates="equipmentrole",
        cascade="all, delete-orphan",
    )

    equipment = association_proxy("equipmentroleequipmentassociation",
                                  "equipmentrole", creator=lambda equipment: EquipmentRoleEquipmentAssociation(
            equipment=equipment))

    def to_dict(self) -> dict:
        """
        This EquipmentRole as a dictionary

        Returns:
            dict: This EquipmentRole dict
        """
        return {key: value for key, value in self.__dict__.items() if key != "process" and key != "equipment"}

    def to_pydantic(self, proceduretype: ProcedureType) -> PydEquipmentRole:
        """
        Creates a PydEquipmentRole of this EquipmentRole

        Args:
            proceduretype (SubmissionType): SubmissionType of interest
            kittype (str | KitType | None, optional): KitType of interest. Defaults to None.

        Returns:
            PydEquipmentRole: This EquipmentRole as PydEquipmentRole
        """
        from backend.validators.pydant import PydEquipmentRole
        equipment = [item.to_pydantic(proceduretype=proceduretype, equipmentrole=self) for item in
                     self.equipment]
        pyd_dict = self.to_dict()
        pyd_dict['process'] = self.get_processes(proceduretype=proceduretype)
        return PydEquipmentRole(equipment=equipment, **pyd_dict)

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

    def details_dict(self, **kwargs):
        if "proceduretype" in kwargs:
            proceduretype = kwargs['proceduretype']
        else:
            proceduretype = None
        match proceduretype:
            case ProcedureType():
                pass
            case str():
                proceduretype = ProcedureType.query(name=proceduretype, limit=1)
            case _:
                proceduretype = None
        output = super().details_dict(**kwargs)
        output['equipment'] = [item.details_dict()['equipment'] for item in self.equipmentroleequipmentassociation]
        equip = []
        for eq in output['equipment']:
            dicto = dict(name=eq['name'], asset_number=eq['asset_number'])
            dicto['process'] = [
                {'name': process['name'], 'tips': process['tips']}
                for process in eq['process']
            ]
            for process in dicto['process']:
                process['tips'] = [tr['name'] for tr in process['tips']]
            equip.append(dicto)
        output['equipment'] = equip
        return output


class Equipment(BaseClass, LogMixin):
    """
    A concrete instance of equipment
    """

    id = Column(INTEGER, primary_key=True)  #: id, primary key
    name = Column(String(64))  #: equipment name
    nickname = Column(String(64))  #: equipment nickname
    asset_number = Column(String(16))  #: Given asset number (corpo nickname if you will)

    equipmentprocedureassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="equipment",
        cascade="all, delete-orphan",
    )  #: Association with BasicRun

    procedure = association_proxy("equipmentprocedureassociation",
                                  "procedure")  #: proxy to equipmentprocedureassociation.procedure

    equipmentequipmentroleassociation = relationship(
        "EquipmentRoleEquipmentAssociation",
        back_populates="equipment",
        cascade="all, delete-orphan",
    )

    equipmentrole = association_proxy("equipmentequipmentroleassociation",
                                      "equipmentrole", creator=lambda equipmentrole: EquipmentRoleEquipmentAssociation(
            equipmentrole=equipmentrole)
                                      )

    def __init__(self, name: str, nickname: str | None = None, asset_number: str = ""):
        self.name = name
        if nickname:
            self.nickname = nickname
        else:
            self.nickname = self.name
        self.asset_number = asset_number

    def to_dict(self, processes: bool = False) -> dict:
        """
        This Equipment as a dictionary

        Args:
            processes (bool, optional): Whether to include process. Defaults to False.

        Returns:
            dict: Dictionary representation of this equipment
        """
        if not processes:
            return {k: v for k, v in self.__dict__.items() if k != 'process'}
        else:
            return {k: v for k, v in self.__dict__.items()}

    @classmethod
    @setup_lookup
    def query(cls,
              id: int | None = None,
              name: str | None = None,
              nickname: str | None = None,
              asset_number: str | None = None,
              limit: int = 0
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

    equipmentrole = relationship("EquipmentRole",
                                 back_populates="equipmentroleequipmentassociation")  #: associated procedure

    equipment = relationship("Equipment",
                             back_populates="equipmentequipmentroleassociation")  #: associated procedure

    process = relationship("Process",
                           back_populates="equipmentroleeequipmentassociation")  #: associated procedure

    def details_dict(self, **kwargs) -> dict:
        output = super().details_dict(**kwargs)
        output['equipment'] = self.equipment.details_dict()
        output['equipment']['process'] = [item.details_dict() for item in self.process.processversion if
                                          bool(item.active)]
        return output


class Process(BaseClass):
    """
    A Process is a method used by a piece of equipment.
    """

    id = Column(INTEGER, primary_key=True)  #: Process id, primary key
    name = Column(String(64), unique=True)  #: Process name
    tips = relationship("Tips", back_populates='process',
                        secondary=process_tips)  #: relation to KitType

    processversion = relationship("ProcessVersion", back_populates="process")

    equipmentroleeequipmentassociation = relationship("EquipmentRoleEquipmentAssociation", back_populates="process")

    def set_attribute(self, key, value):
        match key:
            case "name":
                self.name = value
            case _:
                field = getattr(self, key)
                if value not in field:
                    field.append(value)

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

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniProcess
        if expand:
            proceduretype = [item.to_omni() for item in self.proceduretype]
            equipmentrole = [item.to_omni() for item in self.equipmentrole]
            tiprole = [item.to_omni() for item in self.tiprole]
        else:
            proceduretype = [item.name for item in self.proceduretype]
            equipmentrole = [item.name for item in self.equipmentrole]
            tiprole = [item.name for item in self.tiprole]
        return OmniProcess(
            instance_object=self,
            name=self.name,
            proceduretype=proceduretype,
            equipmentrole=equipmentrole,
            tiprole=tiprole
        )

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        output['processversion'] = [item.details_dict() for item in self.processversion]
        tips = flatten_list([tipslot for tipslot in [tips.tipslot for tips in self.tips]])
        output['tips'] = [tipslot.details_dict() for tipslot in tips]
        return output

    def to_pydantic(self):
        output = super().to_pydantic()
        return output


class ProcessVersion(BaseClass):

    pyd_model_name = "ProcessVersion"

    id = Column(INTEGER, primary_key=True)  #: Process id, primary key
    version = Column(FLOAT(2), default=1.00)  #: Version number
    date_verified = Column(TIMESTAMP)  #: Date this version was deemed worthy
    project = Column(String(128))  #: Name of the project this belonds to.
    active = Column(INTEGER, default=1)  #: Is this version in use?
    process = relationship("Process", back_populates="processversion")
    process_id = Column(INTEGER, ForeignKey("_process.id", ondelete="SET NULL",
                                            name="fk_version_process_id"))
    procedureequipmentassociation = relationship("ProcedureEquipmentAssociation",
                                                 back_populates='processversion')  #: relation to RunEquipmentAssociation

    @property
    def name(self) -> str:
        return f"{self.process.name}-v{str(self.version)}"

    @validates('active')
    def validate_active(self, key, value):
        """
        Ensures only 1 & 0 used in 'active'

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

    def details_dict(self, **kwargs):
        output = super().details_dict(**kwargs)
        output['name'] = self.name
        if not output['project']:
            output['project'] = ""
        output['tips'] = flatten_list(
            [[lot.details_dict() for lot in tips.tipslot if bool(lot.active)] for tips in self.process.tips])
        return output

    def set_attribute(self, key, value):
        setattr(self, key, value)

    @classmethod
    def query(cls,
              version: str | float | None = None,
              name: str | None = None,
              limit: int = 0,
              **kwargs) -> ProcessVersion | List[ProcessVersion]:
        query: Query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.join(Process).filter(Process.name == name)
            case _:
                pass
        match version:
            case str() | float():
                query = query.filter(cls.version == float(version))
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    # def to_pydantic(self, pyd_model_name: str | None = None, **kwargs):
    #     output = super().to_pydantic(pyd_model_name=pyd_model_name, **kwargs)


class Tips(BaseClass):
    """
    An abstract reagentrole that a tip fills during a process
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    tipslot = relationship("TipsLot", back_populates="tips")  #: concrete instance of this tip type
    manufacturer = Column(String(64))  #: Name of manufacturer
    capacity = Column(INTEGER)  #: How many uL the tip can hold.
    ref = Column(String(64))  #: tip reference number
    process = relationship("Process", back_populates="tips", secondary=process_tips)  #: Associated process

    @hybrid_property
    def name(self):
        return f"{self.manufacturer}-{self.ref}"

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

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniTipRole
        if expand:
            tips = [item.to_omni() for item in self.tips]
        else:
            tips = [item.name for item in self.tips]
        return OmniTipRole(
            instance_object=self,
            name=self.name,
            tips=tips
        )


class TipsLot(BaseClass, LogMixin):
    """
    A concrete instance of tips.
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    tips = relationship("Tips", back_populates="tipslot")  #: joined parent tip type
    tips_id = Column(INTEGER, ForeignKey("_tips.id", ondelete='SET NULL',
                                         name="fk_tips_id"))  #: id of parent tip type
    lot = Column(String(64), unique=True)  #: lot number
    expiry = Column(TIMESTAMP)  #: date of expiry
    active = Column(INTEGER, default=1)  #: whether or not these tips are currently in use.

    @validates('active')
    def validate_active(self, key, value):
        """
        Ensures only 1 & 0 used in 'active'

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

    @property
    def size(self) -> str:
        return f"{self.capacity}ul"

    @property
    def name(self) -> str:
        return f"{self.tips.manufacturer}-{self.tips.ref}-{self.lot}"

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
                logger.debug(f"Looking for {manufacturer}")
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

    def to_omni(self, expand: bool = True):
        from backend.validators.omni_gui_objects import OmniTips
        return OmniTips(
            instance_object=self,
            name=self.name
        )

    def to_sub_dict(self, full_data: bool = False, **kwargs) -> dict:
        """
        dictionary containing values necessary for gui

        Args:
            full_data (bool, optional): Whether to include procedure in data for details. Defaults to False.

        Returns:
            dict: representation of the equipment's attributes
        """
        output = dict(
            name=self.name,
            lot=self.lot,
        )
        if full_data:
            subs = [
                dict(plate=item.procedure.procedure.rsl_plate_number, role=item.role_name,
                     sub_date=item.procedure.procedure.clientsubmission.submitted_date)
                for item in self.tipsprocedureassociation]
            output['procedure'] = sorted(subs, key=itemgetter("sub_date"), reverse=True)
            output['excluded'] = ['missing', 'procedure', 'excluded', 'editable']
        return output

    def details_dict(self, **kwargs) -> dict:
        output = super().details_dict()
        output['name'] = self.name
        return output


class ProcedureEquipmentAssociation(BaseClass):
    """
    Abstract association between BasicRun and Equipment
    """

    equipment_id = Column(INTEGER, ForeignKey("_equipment.id"), primary_key=True)  #: id of associated equipment
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    # equipmentrole = Column(String(64), primary_key=True)  #: name of the role the equipment fills
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)
    processversion_id = Column(INTEGER, ForeignKey("_processversion.id", ondelete="SET NULL",
                                                   name="SEA_Process_id"))  #: Foreign key of process id
    start_time = Column(TIMESTAMP)  #: start time of equipment use
    end_time = Column(TIMESTAMP)  #: end time of equipment use
    comments = Column(String(1024))  #: comments about equipment

    procedure = relationship(Procedure,
                             back_populates="procedureequipmentassociation")  #: associated procedure

    equipment = relationship(Equipment, back_populates="equipmentprocedureassociation")  #: associated equipment

    equipmentrole = relationship(EquipmentRole)

    processversion = relationship(ProcessVersion,
                                  back_populates="procedureequipmentassociation")  #: Associated process version

    tipslot_id = Column(INTEGER, ForeignKey("_tipslot.id", ondelete="SET NULL",
                                            name="SEA_Tipslot_id"))

    tipslot = relationship(TipsLot)

    def __repr__(self) -> str:
        try:
            return f"<ProcedureEquipmentAssociation({self.name})>"
        except AttributeError:
            return "<ProcedureEquipmentAssociation(Unknown)>"

    def __init__(self, procedure=None, equipment=None, procedure_id: int | None = None, equipment_id: int | None = None,
                 equipmentrole: str = "None"):
        if not procedure:
            if procedure_id:
                procedure = Procedure.query(id=procedure_id)
            else:
                logger.error("Creation error")
        self.procedure = procedure
        if not equipment:
            if equipment_id:
                equipment = Equipment.query(id=equipment_id)
            else:
                logger.error("Creation error")
        self.equipment = equipment
        if isinstance(equipmentrole, list):
            equipmentrole = equipmentrole[0]
        # if isinstance(equipmentrole, EquipmentRole):
        #     equipmentrole = equipmentrole.name
        self.equipmentrole = equipmentrole

    @property
    def name(self):
        return f"{self.procedure.name} & {self.equipment.name}"

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

    def to_pydantic(self) -> "PydEquipment":
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
    uses = Column(JSON)  #: locations of equipment on the procedure type excel sheet.
    static = Column(INTEGER,
                    default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?
    proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypeequipmentroleassociation",
                                 foreign_keys=[proceduretype_id])  #: associated procedure
    equipmentrole = relationship(EquipmentRole,
                                 back_populates="equipmentroleproceduretypeassociation",
                                 foreign_keys=[equipmentrole_id])  #: associated equipment

    @validates('static')
    def validate_static(self, key, value):
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

    @check_authorization
    def save(self):
        super().save()


class Results(BaseClass):
    id = Column(INTEGER, primary_key=True)  #: primary key
    result = Column(JSON)  #:
    date_analyzed = Column(TIMESTAMP)
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id", ondelete='SET NULL',
                                              name="fk_RES_procedure_id"))
    procedure = relationship("Procedure", back_populates="results")
    assoc_id = Column(INTEGER, ForeignKey("_proceduresampleassociation.id", ondelete='SET NULL',
                                          name="fk_RES_ASSOC_id"))
    sampleprocedureassociation = relationship("ProcedureSampleAssociation", back_populates="results")
    _img = Column(String(128))

    resultstype_id = Column(INTEGER, ForeignKey("_resultstype.id", ondelete='SET NULL',
                                              name="fk_RES_resultstype_id"))
    resultstype = relationship("ResultsType", back_populates="results")

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
            output.sample_id = self.sample_id
        return output


class ResultsType(BaseClass):

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = id = Column(String(64))  #: primary key
    results = relationship("Results", back_populates="resultstype")
    
