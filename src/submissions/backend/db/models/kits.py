"""
All kittype and reagent related models
"""
from __future__ import annotations
import json, zipfile, yaml, logging, re, sys
from operator import itemgetter
from pprint import pformat

from jinja2 import Template, TemplateNotFound
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, BLOB
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import date, datetime, timedelta
from tools import check_authorization, setup_lookup, Report, Result, check_regex_match, yaml_regex_creator, timezone, \
    jinja_template_loading
from typing import List, Literal, Generator, Any, Tuple, TYPE_CHECKING
from pandas import ExcelFile
from pathlib import Path
from . import Base, BaseClass, ClientLab, LogMixin
from io import BytesIO

if TYPE_CHECKING:
    from backend.db.models.submissions import Run

logger = logging.getLogger(f'procedure.{__name__}')

reagentrole_reagent = Table(
    "_reagentrole_reagent",
    Base.metadata,
    Column("reagent_id", INTEGER, ForeignKey("_reagent.id")),
    Column("reagentrole_id", INTEGER, ForeignKey("_reagentrole.id")),
    extend_existing=True
)

equipmentrole_equipment = Table(
    "_equipmentrole_equipment",
    Base.metadata,
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    Column("equipmentrole_id", INTEGER, ForeignKey("_equipmentrole.id")),
    extend_existing=True
)

equipment_process = Table(
    "_equipment_process",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    extend_existing=True
)

equipmentrole_process = Table(
    "_equipmentrole_process",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentrole_id", INTEGER, ForeignKey("_equipmentrole.id")),
    extend_existing=True
)

kittype_process = Table(
    "_kittype_process",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("kittype_id", INTEGER, ForeignKey("_kittype.id")),
    extend_existing=True
)

tiprole_tips = Table(
    "_tiprole_tips",
    Base.metadata,
    Column("tiprole_id", INTEGER, ForeignKey("_tiprole.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)

process_tiprole = Table(
    "_process_tiprole",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("tiprole_id", INTEGER, ForeignKey("_tiprole.id")),
    extend_existing=True
)

equipment_tips = Table(
    "_equipment_tips",
    Base.metadata,
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)

kittype_procedure = Table(
    "_kittype_procedure",
    Base.metadata,
    Column("procedure_id", INTEGER, ForeignKey("_procedure.id")),
    Column("kittype_id", INTEGER, ForeignKey("_kittype.id")),
    extend_existing=True
)

proceduretype_process = Table(
    "_proceduretype_process",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    extend_existing=True
)

submissiontype_proceduretype = Table(
    "_submissiontype_proceduretype",
    Base.metadata,
    Column("submissiontype_id", INTEGER, ForeignKey("_submissiontype.id")),
    Column("proceduretype_id", INTEGER, ForeignKey("_proceduretype.id")),
    extend_existing=True
)


class KitType(BaseClass):
    """
    Base of kits used in procedure processing
    """

    omni_sort = BaseClass.omni_sort + ["kittypesubmissiontypeassociations", "kittypereagentroleassociation",
                                       "process"]

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), unique=True)  #: name of kittype
    procedure = relationship("Procedure", back_populates="kittype",
                             secondary=kittype_procedure)  #: run this kittype was used for
    process = relationship("Process", back_populates="kittype",
                           secondary=kittype_process)  #: equipment process used by this kittype

    kittypereagentroleassociation = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="kittype",
        cascade="all, delete-orphan",
    )

    # NOTE: creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    reagentrole = association_proxy("kittypereagentroleassociation", "reagentrole",
                                    creator=lambda RT: KitTypeReagentRoleAssociation(
                                        reagentrole=RT))  #: Association proxy to KitTypeReagentRoleAssociation

    kittypeproceduretypeassociation = relationship(
        "ProcedureTypeKitTypeAssociation",
        back_populates="kittype",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionType

    proceduretype = association_proxy("kittypeproceduretypeassociation", "proceduretype",
                                      creator=lambda ST: ProcedureTypeKitTypeAssociation(
                                          submissiontype=ST))  #: Association proxy to SubmissionTypeKitTypeAssociation

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.

        Returns:
            List[str]: List of names
        """
        return super().aliases + [cls.query_alias, "kittype", "kittype"]

    def get_reagents(self,
                     required_only: bool = False,
                     proceduretype: str | ProcedureType | None = None
                     ) -> Generator[ReagentRole, None, None]:
        """
        Return ReagentTypes linked to kittype through KitTypeReagentTypeAssociation.

        Args:
            required_only (bool, optional): If true only return required types. Defaults to False.
            proceduretype (str | Submissiontype | None, optional): Submission type to narrow results. Defaults to None.

        Returns:
            Generator[ReagentRole, None, None]: List of reagent roles linked to this kittype.
        """
        match proceduretype:
            case ProcedureType():
                relevant_associations = [item for item in self.kittypereagentroleassociation if
                                         item.proceduretype == proceduretype]
            case str():
                relevant_associations = [item for item in self.kittypereagentroleassociation if
                                         item.proceduretype.name == proceduretype]
            case _:
                relevant_associations = [item for item in self.kittypereagentroleassociation]
        if required_only:
            return (item.reagentrole for item in relevant_associations if item.required == 1)
        else:
            return (item.reagentrole for item in relevant_associations)

    def construct_xl_map_for_use(self, proceduretype: str | SubmissionType) -> Tuple[dict | None, KitType]:
        """
        Creates map of locations in Excel workbook for a SubmissionType

        Args:
            proceduretype (str | SubmissionType): Submissiontype.name

        Returns:
            Generator[(str, str), None, None]: Tuple containing information locations.
        """
        new_kit = self
        # NOTE: Account for proceduretype variable type.
        match proceduretype:
            case str():
                # logger.debug(f"Query for {proceduretype}")
                proceduretype = ProcedureType.query(name=proceduretype)
            case SubmissionType():
                pass
            case _:
                raise ValueError(f"Wrong variable type: {type(proceduretype)} used!")
        # logger.debug(f"Submission type: {proceduretype}, Kit: {self}")
        assocs = [item for item in self.kittypereagentroleassociation if item.proceduretype == proceduretype]
        # logger.debug(f"Associations: {assocs}")
        # NOTE: rescue with procedure type's default kittype.
        if not assocs:
            logger.error(
                f"No associations found with {self}. Attempting rescue with default kittype: {proceduretype.default_kit}")
            new_kit = proceduretype.default_kit
            if not new_kit:
                from frontend.widgets.pop_ups import ObjectSelector
                dlg = ObjectSelector(
                    title="Select Kit",
                    message="Could not find reagents for this procedure type/kittype type combo.\nSelect new kittype.",
                    obj_type=self.__class__,
                    values=[kit.name for kit in proceduretype.kittype]
                )
                if dlg.exec():
                    dlg_result = dlg.parse_form()
                    # logger.debug(f"Dialog result: {dlg_result}")
                    new_kit = self.__class__.query(name=dlg_result)
                    # logger.debug(f"Query result: {new_kit}")
                else:
                    return None, new_kit
            assocs = [item for item in new_kit.kittypereagentroleassociation if item.proceduretype == proceduretype]
        output = {assoc.reagentrole.name: assoc.uses for assoc in assocs}
        # logger.debug(f"Output: {output}")
        return output, new_kit

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[KitType, bool]:
        from backend.validators.pydant import PydKitType
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = PydKitType(**kwargs)
            new = True
            instance = instance.to_sql()
        logger.info(f"Instance from query or create: {instance}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              name: str = None,
              proceduretype: str | ProcedureType | None = None,
              id: int | None = None,
              limit: int = 0,
              **kwargs
              ) -> KitType | List[KitType]:
        """
        Lookup a list of or single KitType.

        Args:
            name (str, optional): Name of desired kittype (returns single instance). Defaults to None.
            proceduretype (str | ProcedureType | None, optional): Submission type the kittype is used for. Defaults to None.
            id (int | None, optional): Kit id in the database. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            KitType|List[KitType]: KitType(s) of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match proceduretype:
            case str():
                query = query.filter(cls.proceduretype.any(name=proceduretype))
            case ProcedureType():
                query = query.filter(cls.proceduretype.contains(proceduretype))
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
            case str():
                query = query.filter(cls.id == int(id))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @check_authorization
    def save(self):
        super().save()

    # def to_export_dict(self, proceduretype: SubmissionType) -> dict:
    #     """
    #     Creates dictionary for exporting to yml used in new SubmissionType Construction
    #
    #     Args:
    #         proceduretype (SubmissionType): SubmissionType of interest.
    #
    #     Returns:
    #         dict: Dictionary containing relevant info for SubmissionType construction
    #     """
    #     base_dict = dict(name=self.name, reagent_roles=[], equipmentrole=[])
    #     for key, value in self.construct_xl_map_for_use(proceduretype=proceduretype):
    #         try:
    #             assoc = next(item for item in self.kit_reagentrole_associations if item.reagentrole.name == key)
    #         except StopIteration as e:
    #             continue
    #         for kk, vv in assoc.to_export_dict().items():
    #             value[kk] = vv
    #         base_dict['reagent_roles'].append(value)
    #     for key, value in proceduretype.construct_field_map("equipment"):
    #         try:
    #             assoc = next(item for item in proceduretype.proceduretypeequipmentroleassociation if
    #                          item.equipmentrole.name == key)
    #         except StopIteration:
    #             continue
    #         for kk, vv in assoc.to_export_dict(kittype=self).items():
    #             value[kk] = vv
    #         base_dict['equipmentrole'].append(value)
    #     return base_dict

    # @classmethod
    # def import_from_yml(cls, proceduretype: str | SubmissionType, filepath: Path | str | None = None,
    #                     import_dict: dict | None = None) -> KitType:
    #     if isinstance(proceduretype, str):
    #         proceduretype = SubmissionType.query(name=proceduretype)
    #     if filepath:
    #         yaml.add_constructor("!regex", yaml_regex_creator)
    #         if isinstance(filepath, str):
    #             filepath = Path(filepath)
    #         if not filepath.exists():
    #             logging.critical(f"Given file could not be found.")
    #             return None
    #         with open(filepath, "r") as f:
    #             if filepath.suffix == ".json":
    #                 import_dict = json.load(fp=f)
    #             elif filepath.suffix == ".yml":
    #                 import_dict = yaml.load(stream=f, Loader=yaml.Loader)
    #             else:
    #                 raise Exception(f"Filetype {filepath.suffix} not supported.")
    #     new_kit = KitType.query(name=import_dict['kittype']['name'])
    #     if not new_kit:
    #         new_kit = KitType(name=import_dict['kittype']['name'])
    #     for reagentrole in import_dict['kittype']['reagent_roles']:
    #         new_role = ReagentRole.query(name=reagentrole['reagentrole'])
    #         if new_role:
    #             check = input(f"Found existing reagentrole: {new_role.name}. Use this? [Y/n]: ")
    #             if check.lower() == "n":
    #                 new_role = None
    #             else:
    #                 pass
    #         if not new_role:
    #             eol = timedelta(reagentrole['extension_of_life'])
    #             new_role = ReagentRole(name=reagentrole['reagentrole'], eol_ext=eol)
    #         uses = dict(expiry=reagentrole['expiry'], lot=reagentrole['lot'], name=reagentrole['name'], sheet=reagentrole['sheet'])
    #         ktrr_assoc = KitTypeReagentRoleAssociation(kittype=new_kit, reagentrole=new_role, uses=uses)
    #         ktrr_assoc.proceduretype = proceduretype
    #         ktrr_assoc.required = reagentrole['required']
    #     ktst_assoc = SubmissionTypeKitTypeAssociation(
    #         kittype=new_kit,
    #         proceduretype=proceduretype,
    #         mutable_cost_sample=import_dict['mutable_cost_sample'],
    #         mutable_cost_column=import_dict['mutable_cost_column'],
    #         constant_cost=import_dict['constant_cost']
    #     )
    #     for reagentrole in import_dict['kittype']['equipmentrole']:
    #         new_role = EquipmentRole.query(name=reagentrole['reagentrole'])
    #         if new_role:
    #             check = input(f"Found existing reagentrole: {new_role.name}. Use this? [Y/n]: ")
    #             if check.lower() == "n":
    #                 new_role = None
    #             else:
    #                 pass
    #         if not new_role:
    #             new_role = EquipmentRole(name=reagentrole['reagentrole'])
    #             for equipment in Equipment.assign_equipment(equipmentrole=new_role):
    #                 new_role.control.append(equipment)
    #         ster_assoc = ProcedureTypeEquipmentRoleAssociation(proceduretype=proceduretype,
    #                                                             equipmentrole=new_role)
    #         try:
    #             uses = dict(name=reagentrole['name'], process=reagentrole['process'], sheet=reagentrole['sheet'],
    #                         static=reagentrole['static'])
    #         except KeyError:
    #             uses = None
    #         ster_assoc.uses = uses
    #         for process in reagentrole['process']:
    #             new_process = Process.query(name=process)
    #             if not new_process:
    #                 new_process = Process(name=process)
    #             new_process.proceduretype.append(proceduretype)
    #             new_process.kittype.append(new_kit)
    #             new_process.equipmentrole.append(new_role)
    #     return new_kit

    def to_omni(self, expand: bool = False) -> "OmniKitType":
        from backend.validators.omni_gui_objects import OmniKitType
        if expand:
            processes = [item.to_omni() for item in self.process]
            kittypereagentroleassociation = [item.to_omni() for item in self.kittypereagentroleassociation]
            kittypeproceduretypeassociation = [item.to_omni() for item in self.kittypeproceduretypeassociation]
        else:
            processes = [item.name for item in self.processes]
            kittypereagentroleassociation = [item.name for item in self.kittypereagentroleassociation]
            kittypeproceduretypeassociation = [item.name for item in self.kittypeproceduretypeassociation]
        data = dict(
            name=self.name,
            processes=processes,
            kit_reagentrole_associations=kittypereagentroleassociation,
            kit_submissiontype_associations=kittypeproceduretypeassociation
        )
        # logger.debug(f"Creating omni for {pformat(data)}")
        return OmniKitType(instance_object=self, **data)


class ReagentRole(BaseClass):
    """
    Base of reagent type abstract
    """

    skip_on_edit = False
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: name of reagentrole reagent plays
    reagent = relationship("Reagent", back_populates="reagentrole",
                           secondary=reagentrole_reagent)  #: concrete control of this reagent type
    eol_ext = Column(Interval())  #: extension of life interval

    reagentrolekittypeassociation = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="reagentrole",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation

    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    kittype = association_proxy("reagentrolekittypeassociation", "kittype",
                                creator=lambda kit: KitTypeReagentRoleAssociation(
                                    kittype=kit))  #: Association proxy to KitTypeReagentRoleAssociation

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
        logger.info(f"Instance from query or create: {instance}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              kittype: KitType | str | None = None,
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
            kittype (KitType | str | None, optional): Kit the type of interest belongs to. Defaults to None.
            reagent (Reagent | str | None, optional): Concrete instance of the type of interest. Defaults to None.
            limit (int, optional): maxmimum number of results to return (0 = all). Defaults to 0.

        Raises:
            ValueError: Raised if only kittype or reagent, not both, given.

        Returns:
            ReagentRole|List[ReagentRole]: ReagentRole or list of ReagentRoles matching filter.
        """
        query: Query = cls.__database_session__.query(cls)
        if (kittype is not None and reagent is None) or (reagent is not None and kittype is None):
            raise ValueError("Cannot filter without both reagent and kittype type.")
        elif kittype is None and reagent is None:
            pass
        else:
            match kittype:
                case str():
                    kittype = KitType.query(name=kittype)
                case _:
                    pass
            match reagent:
                case str():
                    reagent = Reagent.query(lot=reagent)
                case _:
                    pass
            assert reagent.role
            # NOTE: Get all roles common to the reagent and the kittype.
            result = set(kittype.reagentrole).intersection(reagent.role)
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

    def to_pydantic(self) -> "PydReagent":
        """
        Create default PydReagent from this object

        Returns:
            PydReagent: PydReagent representation of this object.
        """
        from backend.validators.pydant import PydReagent
        return PydReagent(lot=None, reagentrole=self.name, name=self.name, expiry=date.today())

    @check_authorization
    def save(self):
        super().save()

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniReagentRole
        logger.debug(f"Constructing OmniReagentRole with name {self.name}")
        return OmniReagentRole(instance_object=self, name=self.name, eol_ext=self.eol_ext)

    @property
    def reagents(self):
        return [f"{reagent.name} - {reagent.lot}" for reagent in self.reagent]

class Reagent(BaseClass, LogMixin):
    """
    Concrete reagent instance
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    reagentrole = relationship("ReagentRole", back_populates="reagent",
                               secondary=reagentrole_reagent)  #: joined parent reagent type
    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id", ondelete='SET NULL',
                                                name="fk_REG_reagent_role_id"))  #: id of parent reagent type
    name = Column(String(64))  #: reagent name
    lot = Column(String(64))  #: lot number of reagent
    expiry = Column(TIMESTAMP)  #: expiry date - extended by eol_ext of parent programmatically

    reagentprocedureassociation = relationship(
        "ProcedureReagentAssociation",
        back_populates="reagent",
        cascade="all, delete-orphan",
    )  #: Relation to ClientSubmissionSampleAssociation

    procedures = association_proxy("reagentprocedureassociation", "procedure",
                                   creator=lambda procedure: ProcedureReagentAssociation(
                                       procedure=procedure))  #: Association proxy to ClientSubmissionSampleAssociation.sample

    def __repr__(self):
        if self.name:
            name = f"<Reagent({self.name}-{self.lot})>"
        else:
            name = f"<Reagent({self.reagentrole.name}-{self.lot})>"
        return name

    @classproperty
    def searchables(cls):
        return [dict(label="Lot", field="lot")]

    def to_sub_dict(self, kittype: KitType = None, full_data: bool = False, **kwargs) -> dict:
        """
        dictionary containing values necessary for gui

        Args:
            kittype (KitType, optional): KitType to use to get reagent type. Defaults to None.
            full_data (bool, optional): Whether to include procedure in data for details. Defaults to False.

        Returns:
            dict: representation of the reagent's attributes
        """
        if kittype is not None:
            # NOTE: Get the intersection of this reagent's ReagentType and all ReagentTypes in KitType
            reagent_role = next((item for item in set(self.reagentrole).intersection(kittype.reagentrole)),
                                self.reagentrole[0])
        else:
            try:
                reagent_role = self.reagentrole[0]
            except IndexError:
                reagent_role = None
        try:
            rtype = reagent_role.name.replace("_", " ")
        except AttributeError:
            rtype = "Unknown"
        # NOTE: Calculate expiry with EOL from ReagentType
        try:
            place_holder = self.expiry + reagent_role.eol_ext
        except (TypeError, AttributeError) as e:
            place_holder = date.today()
            logger.error(f"We got a type error setting {self.lot} expiry: {e}. setting to today for testing")
        # NOTE: The notation for not having an expiry is 1970.01.01
        if self.expiry.year == 1970:
            place_holder = "NA"
        else:
            place_holder = place_holder.strftime("%Y-%m-%d")
        output = dict(
            name=self.name,
            reagentrole=rtype,
            lot=self.lot,
            expiry=place_holder,
            missing=False
        )
        if full_data:
            output['procedure'] = [sub.rsl_plate_num for sub in self.procedures]
            output['excluded'] = ['missing', 'procedure', 'excluded', 'editable']
            output['editable'] = ['lot', 'expiry']
        return output

    def update_last_used(self, kit: KitType) -> Report:
        """
        Updates last used reagent lot for ReagentType/KitType

        Args:
            kit (KitType): Kit this instance is used in.

        Returns:
            Report: Result of operation
        """
        report = Report()
        rt = ReagentRole.query(kittype=kit, reagent=self, limit=1)
        if rt is not None:
            assoc = KitTypeReagentRoleAssociation.query(kittype=kit, reagentrole=rt)
            if assoc is not None:
                if assoc.last_used != self.lot:
                    assoc.last_used = self.lot
                    result = assoc.save()
                    report.add_result(result)
                    return report
        report.add_result(Result(msg=f"Updating last used {rt} was not performed.", status="Information"))
        return report

    @classmethod
    def query_or_create(cls, **kwargs) -> Reagent:
        from backend.validators.pydant import PydReagent
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            if "reagentrole" not in kwargs:
                try:
                    kwargs['reagentrole'] = kwargs['name']
                except KeyError:
                    pass
            instance = PydReagent(**kwargs)
            new = True
            instance = instance.to_sql()
        logger.info(f"Instance from query or create: {instance}")
        return instance, new

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
            reagent_role (str | models.ReagentType | None, optional): Reagent type. Defaults to None.
            lot_number (str | None, optional): Reagent lot number. Defaults to None.
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
                if role and role not in self.role:
                    self.reagentrole.append(role)
                return
            case "comment":
                return
            case "expiry":
                if isinstance(value, str):
                    value = date(year=1970, month=1, day=1)
                # NOTE: if min time is used, any reagent set to expire today (Bac postive control, eg) will have expired at midnight and therefore be flagged.
                # NOTE: Make expiry at date given, plus maximum time = end of day
                value = datetime.combine(value, datetime.max.time())
                value = value.replace(tzinfo=timezone)
            case _:
                pass
                logger.debug(f"Role to be set to: {value}")
        try:
            self.__setattr__(key, value)
        except AttributeError as e:
            logger.error(f"Could not set {key} due to {e}")

    @check_authorization
    def edit_from_search(self, obj, **kwargs):
        from frontend.widgets.omni_add_edit import AddEdit
        # logger.debug(f"Calling edit_from_search for {self.name}")
        dlg = AddEdit(parent=None, instance=self)
        if dlg.exec():
            pyd = dlg.parse_form()
            for field in pyd.model_fields:
                self.set_attribute(field, pyd.__getattribute__(field))
            self.save()

    @classproperty
    def add_edit_tooltips(self):
        return dict(
            expiry="Use exact date on reagent.\nEOL will be calculated from kittype automatically"
        )


class Discount(BaseClass):
    """
    Relationship table for client labs for certain kits.
    """

    skip_on_edit = True

    id = Column(INTEGER, primary_key=True)  #: primary key
    kittype = relationship("KitType")  #: joined parent reagent type
    kittype_id = Column(INTEGER, ForeignKey("_kittype.id", ondelete='SET NULL',
                                            name="fk_DIS_kit_type_id"))  #: id of joined kittype
    clientlab = relationship("ClientLab")  #: joined client lab
    clientlab_id = Column(INTEGER,
                          ForeignKey("_clientlab.id", ondelete='SET NULL',
                                     name="fk_DIS_org_id"))  #: id of joined client
    name = Column(String(128))  #: Short description
    amount = Column(FLOAT(2))  #: Dollar amount of discount

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
              kittype: KitType | str | int | None = None,
              ) -> Discount | List[Discount]:
        """
        Lookup discount objects (union of kittype and clientlab)

        Args:
            clientlab (models.ClientLab | str | int): ClientLab receiving discount.
            kittype (models.KitType | str | int): Kit discount received on.

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
        match kittype:
            case KitType():
                query = query.filter(cls.kittype == kittype)
            case str():
                query = query.join(KitType).filter(KitType.name == kittype)
            case int():
                query = query.join(KitType).filter(KitType.id == kittype)
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
    info_map = Column(JSON)  #: Where parsable information is found in the excel workbook corresponding to this type.
    defaults = Column(JSON)  #: Basic information about this procedure type
    clientsubmission = relationship("ClientSubmission",
                                    back_populates="submissiontype")  #: Concrete control of this type.
    template_file = Column(BLOB)  #: Blank form for this type stored as binary.
    sample_map = Column(JSON)  #: Where sample information is found in the excel sheet corresponding to this type.
    proceduretype = relationship("ProcedureType", back_populates="submissiontype",
                                 secondary=submissiontype_proceduretype)  #: run this kittype was used for

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object.
        """
        return f"<SubmissionType({self.name})>"

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.

        Returns:
            List[str]: List of names
        """
        return super().aliases + ["submissiontypes"]

    @classproperty
    def omni_removes(cls):
        return super().omni_removes + ["defaults"]

    @classproperty
    def basic_template(cls) -> bytes:
        """
        Grabs the default excel template file.

        Returns:
            bytes: The Excel sheet.
        """
        submission_type = cls.query(name="Bacterial Culture")
        return submission_type.template_file

    @property
    def template_file_sheets(self) -> List[str]:
        """
        Gets names of sheet in the stored blank form.

        Returns:
            List[str]: List of sheet names
        """
        try:
            return ExcelFile(BytesIO(self.template_file), engine="openpyxl").sheet_names
        except zipfile.BadZipfile:
            return []

    def set_template_file(self, filepath: Path | str):
        """

        Sets the binary store to an Excel file.

        Args:
            filepath (Path | str): Path to the template file.

        Raises:
            ValueError: Raised if file is not Excel file.
        """
        if isinstance(filepath, str):
            filepath = Path(filepath)
        try:
            ExcelFile(filepath)
        except ValueError:
            raise ValueError(f"File {filepath} is not of appropriate type.")
        with open(filepath, "rb") as f:
            data = f.read()
        self.template_file = data
        self.save()

    def construct_info_map(self, mode: Literal['read', 'write', 'export']) -> dict:
        """
        Make of map of where all fields are located in Excel sheet

        Args:
            mode (Literal["read", "write"]): Which mode to get locations for

        Returns:
            dict: Map of locations
        """
        info = {k: v for k, v in self.info_map.items() if k != "custom"}
        match mode:
            case "read":
                output = {k: v[mode] for k, v in info.items() if v[mode]}
            case "write":
                output = {k: v[mode] + v['read'] for k, v in info.items() if v[mode] or v['read']}
                output = {k: v for k, v in output.items() if all([isinstance(item, dict) for item in v])}
            case "export":
                return self.info_map
            case _:
                output = {}
        output['custom'] = self.info_map['custom']
        return output

    def construct_field_map(self, field: Literal['equipment', 'tip']) -> Generator[(str, dict), None, None]:
        """
        Make a map of all locations for tips or equipment.

        Args:
            field (Literal['equipment', 'tip']): the field to construct a map for

        Returns:
            Generator[(str, dict), None, None]: Generator composing key, locations for each item in the map
        """
        for item in self.__getattribute__(f"submissiontype_{field}role_associations"):
            fmap = item.uses
            if fmap is None:
                fmap = {}
            yield getattr(item, f"{field}_role").name, fmap

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
                logger.debug(f"querying with {name}")
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

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniSubmissionType
        try:
            template_file = self.template_file
        except AttributeError:
            template_file = bytes()
        return OmniSubmissionType(
            instance_object=self,
            name=self.name,
            info_map=self.info_map,
            defaults=self.defaults,
            template_file=template_file,
            sample_map=self.sample_map
        )

    @classproperty
    def info_map_json_edit_fields(cls):
        dicto = dict()
        return dicto


class ProcedureType(BaseClass):
    id = Column(INTEGER, primary_key=True)
    name = Column(String(64))
    reagent_map = Column(JSON)
    plate_columns = Column(INTEGER, default=0)
    plate_rows = Column(INTEGER, default=0)

    procedure = relationship("Procedure",
                             back_populates="proceduretype")  #: Concrete control of this type.

    process = relationship("Process", back_populates="proceduretype",
                           secondary=proceduretype_process)  #: Relation to equipment process used for this type.

    submissiontype = relationship("SubmissionType", back_populates="proceduretype",
                                  secondary=submissiontype_proceduretype)  #: run this kittype was used for

    proceduretypekittypeassociation = relationship(
        "ProcedureTypeKitTypeAssociation",
        back_populates="proceduretype",
        cascade="all, delete-orphan",
    )  #: Association of kittypes

    kittype = association_proxy("proceduretypekittypeassociation", "kittype",
                                creator=lambda kit: ProcedureTypeKitTypeAssociation(
                                    kittype=kit))  #: Proxy of kittype association

    proceduretypeequipmentroleassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="proceduretype",
        cascade="all, delete-orphan"
    )  #: Association of equipmentroles

    equipment = association_proxy("proceduretypeequipmentroleassociation", "equipmentrole",
                                  creator=lambda eq: ProcedureTypeEquipmentRoleAssociation(
                                      equipment_role=eq))  #: Proxy of equipmentrole associations

    kittypereagentroleassociation = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="proceduretype",
        cascade="all, delete-orphan"
    )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes

    proceduretypetiproleassociation = relationship(
        "ProcedureTypeTipRoleAssociation",
        back_populates="proceduretype",
        cascade="all, delete-orphan"
    )  #: Association of tiproles

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

    @property
    def default_kit(self) -> KitType | None:
        """
        If only one kits exists for this Submission Type, return it.

        Returns:
            KitType | None:
        """
        if len(self.kittype) == 1:
            return self.kittype[0]
        else:
            return None

    def get_equipment(self, kittype: str | KitType | None = None) -> Generator['PydEquipmentRole', None, None]:
        """
        Returns PydEquipmentRole of all equipment associated with this SubmissionType

        Returns:
            Generator['PydEquipmentRole', None, None]: List of equipment roles
        """
        return (item.to_pydantic(proceduretype=self, kittype=kittype) for item in self.equipment)

    def get_processes_for_role(self, equipmentrole: str | EquipmentRole, kittype: str | KitType | None = None) -> list:
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
                relevant = [item.get_all_processes(kittype) for item in self.proceduretypeequipmentroleassociation if
                            item.equipmentrole.name == equipmentrole]
            case EquipmentRole():
                relevant = [item.get_all_processes(kittype) for item in self.proceduretypeequipmentroleassociation if
                            item.equipmentrole == equipmentrole]
            case _:
                raise TypeError(f"Type {type(equipmentrole)} is not allowed")
        return list(set([item for items in relevant for item in items if item is not None]))

    @property
    def as_dict(self):
        return dict(
            name=self.name,
            kittype=[item.name for item in self.kittype]
        )

    def construct_dummy_procedure(self):
        from backend.validators.pydant import PydProcedure
        output = dict(
            proceduretype=self,
            #name=dict(value=self.name, missing=True),
            #possible_kits=[kittype.name for kittype in self.kittype],
            repeat=False,
            plate_map=self.construct_plate_map()
        )
        return PydProcedure(**output)

    def construct_plate_map(self) -> str:
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
        plate_rows = range(1, self.plate_rows + 1)
        plate_columns = range(1, self.plate_columns + 1)
        total_wells = self.plate_columns * self.plate_rows
        vw = round((-0.07 * total_wells) + 12.2, 1)


        wells = [dict(name="", row=row, column=column, background_color="#ffffff")
                          for row in plate_rows
                          for column in plate_columns]
        # NOTE: An overly complicated list comprehension create a list of sample locations
        # NOTE: next will return a blank cell if no value found for row/column
        env = jinja_template_loading()
        template = env.get_template("plate_map.html")
        html = template.render(plate_rows=self.plate_rows, plate_columns=self.plate_columns, samples=wells, vw=vw)
        return html + "<br/>"


class Procedure(BaseClass):
    id = Column(INTEGER, primary_key=True)
    name = Column(String, unique=True)
    repeat = Column(INTEGER, nullable=False)
    technician = Column(JSON)  #: name of processing tech(s)
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete="SET NULL",
                                                  name="fk_PRO_proceduretype_id"))  #: client lab id from _organizations))
    proceduretype = relationship("ProcedureType", back_populates="procedure")
    run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="SET NULL",
                                        name="fk_PRO_basicrun_id"))  #: client lab id from _organizations))
    run = relationship("Run", back_populates="procedure")
    kittype_id = Column(INTEGER, ForeignKey("_kittype.id", ondelete="SET NULL",
                                            name="fk_PRO_kittype_id"))  #: client lab id from _organizations))
    kittype = relationship("KitType", back_populates="procedure")
    control = relationship("Control", back_populates="procedure", uselist=True)  #: A control sample added to procedure

    procedurereagentassociation = relationship(
        "ProcedureReagentAssociation",
        back_populates="procedure",
        cascade="all, delete-orphan",
    )  #: Relation to ProcedureReagentAssociation

    reagents = association_proxy("procedurereagentassociation",
                                 "reagent", creator=lambda reg: ProcedureReagentAssociation(
            reagent=reg))  #: Association proxy to RunReagentAssociation.reagent

    procedureequipmentassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="procedure",
        cascade="all, delete-orphan"
    )  #: Relation to Equipment

    equipment = association_proxy("procedureequipmentassociation",
                                  "equipment")  #: Association proxy to RunEquipmentAssociation.equipment

    proceduretipsassociation = relationship(
        "ProcedureTipsAssociation",
        back_populates="procedure",
        cascade="all, delete-orphan")

    tips = association_proxy("proceduretipsassociation",
                             "tips")

    @validates('repeat')
    def validate_repeat(self, key, value):
        if value > 1:
            value = 1
        if value < 0:
            value = 0
        return value

    @classmethod
    @setup_lookup
    def query(cls, id: int | None = None, name: str | None = None, limit: int = 0, **kwargs) -> Procedure | List[
        Procedure]:
        query: Query = cls.__database_session__.query(cls)
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


class ProcedureTypeKitTypeAssociation(BaseClass):
    """
    Abstract of relationship between kits and their procedure type.
    """

    omni_removes = BaseClass.omni_removes + ["proceduretype_id", "kittype_id"]
    omni_sort = ["proceduretype", "kittype"]
    level = 2

    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"),
                              primary_key=True)  #: id of joined procedure type
    kittype_id = Column(INTEGER, ForeignKey("_kittype.id"), primary_key=True)  #: id of joined kittype
    mutable_cost_column = Column(
        FLOAT(2))  #: dollar amount per 96 well plate that can change with number of columns (reagents, tips, etc)
    mutable_cost_sample = Column(
        FLOAT(2))  #: dollar amount that can change with number of sample (reagents, tips, etc)
    constant_cost = Column(FLOAT(2))  #: dollar amount per plate that will remain constant (plates, man hours, etc)

    kittype = relationship(KitType, back_populates="kittypeproceduretypeassociation")  #: joined kittype

    # reference to the "SubmissionType" object
    proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypekittypeassociation")  #: joined procedure type

    def __init__(self, kittype=None, proceduretype=None,
                 mutable_cost_column: int = 0.00, mutable_cost_sample: int = 0.00, constant_cost: int = 0.00):
        self.kittype = kittype
        self.proceduretype = proceduretype
        self.mutable_cost_column = mutable_cost_column
        self.mutable_cost_sample = mutable_cost_sample
        self.constant_cost = constant_cost

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object
        """
        try:
            proceduretype_name = self.proceduretype.name
        except AttributeError:
            proceduretype_name = "None"
        try:
            kittype_name = self.kittype.name
        except AttributeError:
            kittype_name = "None"
        return f"<ProcedureTypeKitTypeAssociation({proceduretype_name}&{kittype_name})>"

    @property
    def name(self):
        try:
            return f"{self.proceduretype.name} -> {self.kittype.name}"
        except AttributeError:
            return "Blank SubmissionTypeKitTypeAssociation"

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[ProcedureTypeKitTypeAssociation, bool]:
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            setattr(instance, k, v)
        logger.info(f"Instance from ProcedureTypeKitTypeAssociation query or create: {instance}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              proceduretype: ProcedureType | str | int | None = None,
              kittype: KitType | str | int | None = None,
              limit: int = 0,
              **kwargs
              ) -> ProcedureTypeKitTypeAssociation | List[ProcedureTypeKitTypeAssociation]:
        """
        Lookup SubmissionTypeKitTypeAssociations of interest.

        Args:
            proceduretype (ProcedureType | str | int | None, optional): Identifier of procedure type. Defaults to None.
            kittype (KitType | str | int | None, optional): Identifier of kittype type. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            SubmissionTypeKitTypeAssociation|List[SubmissionTypeKitTypeAssociation]: SubmissionTypeKitTypeAssociation(s) of interest
        """
        query: Query = cls.__database_session__.query(cls)
        match proceduretype:
            case ProcedureType():
                query = query.filter(cls.proceduretype == proceduretype)
            case str():
                query = query.join(ProcedureType).filter(ProcedureType.name == proceduretype)
            case int():
                query = query.join(ProcedureType).filter(ProcedureType.id == proceduretype)
        match kittype:
            case KitType():
                query = query.filter(cls.kittype == kittype)
            case str():
                query = query.join(KitType).filter(KitType.name == kittype)
            case int():
                query = query.join(KitType).filter(KitType.id == kittype)
        if kittype is not None and proceduretype is not None:
            limit = 1
        return cls.execute_query(query=query, limit=limit)

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniSubmissionTypeKitTypeAssociation
        if expand:
            try:
                submissiontype = self.submission_type.to_omni()
            except AttributeError:
                submissiontype = ""
            try:
                kittype = self.kit_type.to_omni()
            except AttributeError:
                kittype = ""
        else:
            submissiontype = self.submission_type.name
            kittype = self.kit_type.name
        return OmniSubmissionTypeKitTypeAssociation(
            instance_object=self,
            submissiontype=submissiontype,
            kittype=kittype,
            mutable_cost_column=self.mutable_cost_column,
            mutable_cost_sample=self.mutable_cost_sample,
            constant_cost=self.constant_cost
        )


class KitTypeReagentRoleAssociation(BaseClass):
    """
    table containing reagenttype/kittype associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    omni_removes = BaseClass.omni_removes + ["submission_type_id", "kits_id", "reagent_roles_id", "last_used"]
    omni_sort = ["proceduretype", "kittype", "reagentrole", "required", "uses"]
    omni_inheritable = ["proceduretype", "kittype"]

    reagentrole_id = Column(INTEGER, ForeignKey("_reagentrole.id"),
                            primary_key=True)  #: id of associated reagent type
    kittype_id = Column(INTEGER, ForeignKey("_kittype.id"), primary_key=True)  #: id of associated reagent type
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"), primary_key=True)
    uses = Column(JSON)  #: map to location on excel sheets of different procedure types
    required = Column(INTEGER)  #: whether the reagent type is required for the kittype (Boolean 1 or 0)
    last_used = Column(String(32))  #: last used lot number of this type of reagent

    kittype = relationship(KitType,
                           back_populates="kittypereagentroleassociation")  #: relationship to associated KitType

    # NOTE: reference to the "ReagentType" object
    reagentrole = relationship(ReagentRole,
                               back_populates="reagentrolekittypeassociation")  #: relationship to associated ReagentType

    # NOTE: reference to the "SubmissionType" object
    proceduretype = relationship(ProcedureType,
                                 back_populates="kittypereagentroleassociation")  #: relationship to associated SubmissionType

    def __init__(self, kittype=None, reagentrole=None, uses=None, required=1):
        self.kittype = kittype
        self.reagentrole = reagentrole
        self.uses = uses
        self.required = required

    def __repr__(self) -> str:
        return f"<KitTypeReagentRoleAssociation({self.kittype} & {self.reagentrole})>"

    @property
    def name(self):
        try:
            return f"{self.kittype.name} -> {self.reagentrole.name}"
        except AttributeError:
            return "Blank KitTypeReagentRole"

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
    def query_or_create(cls, **kwargs) -> Tuple[KitTypeReagentRoleAssociation, bool]:
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
                case "kittype":
                    if isinstance(v, str):
                        v = KitType.query(name=v)
                    else:
                        v = v.instance_object
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
        logger.info(f"Instance from query or create: {instance.__dict__}\nis new: {new}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              kittype: KitType | str | None = None,
              reagentrole: ReagentRole | str | None = None,
              proceduretype: ProcedureType | str | None = None,
              limit: int = 0,
              **kwargs
              ) -> KitTypeReagentRoleAssociation | List[KitTypeReagentRoleAssociation]:
        """
        Lookup junction of ReagentType and KitType

        Args:
            kittype (models.KitType | str | None): KitType of interest.
            reagentrole (models.ReagentType | str | None): ReagentType of interest.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            models.KitTypeReagentTypeAssociation|List[models.KitTypeReagentTypeAssociation]: Junction of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match kittype:
            case KitType():
                query = query.filter(cls.kit_type == kittype)
            case str():
                query = query.join(KitType).filter(KitType.name == kittype)
            case _:
                pass
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
        if kittype is not None and reagentrole is not None:
            limit = 1
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

    @property
    def omnigui_instance_dict(self) -> dict:
        dicto = super().omnigui_instance_dict
        dicto['required']['instance_attr'] = bool(dicto['required']['instance_attr'])
        return dicto

    @classproperty
    def json_edit_fields(cls) -> dict:
        dicto = dict(
            sheet="str",
            expiry=dict(column="int", row="int"),
            lot=dict(column="int", row="int"),
            name=dict(column="int", row="int")
        )
        return dicto

    def to_omni(self, expand: bool = False) -> "OmniReagentRole":
        from backend.validators.omni_gui_objects import OmniKitTypeReagentRoleAssociation
        try:
            eol_ext = self.reagentrole.eol_ext
        except AttributeError:
            eol_ext = timedelta(days=0)
        if expand:
            try:
                submission_type = self.proceduretype.to_omni()
            except AttributeError:
                submission_type = ""
            try:
                kit_type = self.kittype.to_omni()
            except AttributeError:
                kit_type = ""
            try:
                reagent_role = self.reagentrole.to_omni()
            except AttributeError:
                reagent_role = ""
        else:
            submission_type = self.proceduretype.name
            kit_type = self.kittype.name
            reagent_role = self.reagentrole.name
        return OmniKitTypeReagentRoleAssociation(
            instance_object=self,
            reagent_role=reagent_role,
            eol_ext=eol_ext,
            required=self.required,
            submission_type=submission_type,
            kit_type=kit_type,
            uses=self.uses
        )


class ProcedureReagentAssociation(BaseClass):
    """
    table containing procedure/reagent associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    skip_on_edit = True

    reagent_id = Column(INTEGER, ForeignKey("_reagent.id"), primary_key=True)  #: id of associated reagent
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    comments = Column(String(1024))  #: Comments about reagents

    procedure = relationship("Procedure",
                             back_populates="procedurereagentassociation")  #: associated procedure

    reagent = relationship(Reagent, back_populates="reagentprocedureassociation")  #: associated reagent

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this RunReagentAssociation
        """
        try:
            return f"<ProcedureReagentAssociation({self.procedure.procedure.rsl_plate_num} & {self.reagent.lot})>"
        except AttributeError:
            logger.error(f"Reagent {self.reagent.lot} procedure association {self.reagent_id} has no procedure!")
            return f"<ProcedureReagentAssociation(Unknown Submission & {self.reagent.lot})>"

    def __init__(self, reagent=None, procedure=None):
        if isinstance(reagent, list):
            logger.warning(f"Got list for reagent. Likely no lot was provided. Using {reagent[0]}")
            reagent = reagent[0]
        self.reagent = reagent
        self.procedure = procedure
        self.comments = ""

    @classmethod
    @setup_lookup
    def query(cls,
              procedure: Procedure | str | int | None = None,
              reagent: Reagent | str | None = None,
              limit: int = 0) -> ProcedureReagentAssociation | List[ProcedureReagentAssociation]:
        """
        Lookup SubmissionReagentAssociations of interest.

        Args:
            procedure (Procedure | str | int | None, optional): Identifier of joined procedure. Defaults to None.
            reagent (Reagent | str | None, optional): Identifier of joined reagent. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            RunReagentAssociation|List[RunReagentAssociation]: SubmissionReagentAssociation(s) of interest
        """
        query: Query = cls.__database_session__.query(cls)
        match reagent:
            case Reagent() | str():
                if isinstance(reagent, str):
                    reagent = Reagent.query(lot=reagent)
                query = query.filter(cls.reagent == reagent)
            case _:
                pass
        match procedure:
            case Procedure() | str():
                if isinstance(procedure, str):
                    procedure = Procedure.query(name=procedure)
                query = query.filter(cls.procedure == procedure)
            case int():
                # procedure = Procedure.query(id=procedure)
                query = query.join(Procedure).filter(Procedure.id == procedure)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def to_sub_dict(self, kittype) -> dict:
        """
        Converts this RunReagentAssociation (and associated Reagent) to dict

        Args:
            kittype (_type_): Extraction kittype of interest

        Returns:
            dict: This RunReagentAssociation as dict
        """
        output = self.reagent.to_sub_dict(kittype)
        output['comments'] = self.comments
        return output

    def to_pydantic(self, kittype: KitType):
        from backend.validators import PydReagent
        return PydReagent(**self.to_sub_dict(kittype=kittype))


class Equipment(BaseClass, LogMixin):
    """
    A concrete instance of equipment
    """

    id = Column(INTEGER, primary_key=True)  #: id, primary key
    name = Column(String(64))  #: equipment name
    nickname = Column(String(64))  #: equipment nickname
    asset_number = Column(String(16))  #: Given asset number (corpo nickname if you will)
    equipmentrole = relationship("EquipmentRole", back_populates="equipment",
                                 secondary=equipmentrole_equipment)  #: relation to EquipmentRoles
    process = relationship("Process", back_populates="equipment",
                           secondary=equipment_process)  #: relation to Processes
    tips = relationship("Tips", back_populates="equipment",
                        secondary=equipment_tips)  #: relation to Processes
    equipmentprocedureassociation = relationship(
        "ProcedureEquipmentAssociation",
        back_populates="equipment",
        cascade="all, delete-orphan",
    )  #: Association with BasicRun

    procedure = association_proxy("equipmentprocedureassociation",
                                  "procedure")  #: proxy to equipmentprocedureassociation.procedure

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

    def get_processes(self, proceduretype: str | ProcedureType | None = None,
                      kittype: str | KitType | None = None,
                      equipmentrole: str | EquipmentRole | None = None) -> Generator[Process, None, None]:
        """
        Get all process associated with this Equipment for a given SubmissionType

        Args:
            proceduretype (ProcedureType): SubmissionType of interest
            kittype (str | KitType | None, optional): KitType to filter by. Defaults to None.

        Returns:
            List[Process]: List of process names
        """
        if isinstance(proceduretype, str):
            proceduretype = ProcedureType.query(name=proceduretype)
        if isinstance(kittype, str):
            kittype = KitType.query(name=kittype)
        for process in self.processes:
            if proceduretype not in process.proceduretype:
                continue
            if kittype and kittype not in process.kittype:
                continue
            if equipmentrole and equipmentrole not in process.equipmentrole:
                continue
            yield process

    @classmethod
    @setup_lookup
    def query(cls,
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

    def to_pydantic(self, proceduretype: ProcedureType, kittype: str | KitType | None = None,
                    equipmentrole: str = None) -> "PydEquipment":
        """
        Creates PydEquipment of this Equipment

        Args:
            proceduretype (ProcedureType): Relevant SubmissionType
            kittype (str | KitType | None, optional): Relevant KitType. Defaults to None.

        Returns:
            PydEquipment: pydantic equipment object
        """
        from backend.validators.pydant import PydEquipment
        processes = self.get_processes(proceduretype=proceduretype, kittype=kittype,
                                       equipmentrole=equipmentrole)
        return PydEquipment(processes=processes, role=equipmentrole,
                            **self.to_dict(processes=False))

    @classproperty
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

    def to_sub_dict(self, full_data: bool = False, **kwargs) -> dict:
        """
        dictionary containing values necessary for gui

        Args:
            full_data (bool, optional): Whether to include procedure in data for details. Defaults to False.

        Returns:
            dict: representation of the equipment's attributes
        """
        if self.nickname:
            nickname = self.nickname
        else:
            nickname = self.name
        output = dict(
            name=self.name,
            nickname=nickname,
            asset_number=self.asset_number
        )
        if full_data:
            subs = [dict(plate=item.procedure.procedure.rsl_plate_num, process=item.process.name,
                         sub_date=item.procedure.procedure.start_date)
                    if item.process else dict(plate=item.procedure.procedure.rsl_plate_num, process="NA")
                    for item in self.equipmentprocedureassociation]
            output['procedure'] = sorted(subs, key=itemgetter("sub_date"), reverse=True)
            output['excluded'] = ['missing', 'procedure', 'excluded', 'editable']
        return output

    # @classproperty
    # def details_template(cls) -> Template:
    #     """
    #     Get the details jinja template for the correct class
    #
    #     Args:
    #         base_dict (dict): incoming dictionary of Submission fields
    #
    #     Returns:
    #         Tuple(dict, Template): (Updated dictionary, Template to be rendered)
    #     """
    #     env = jinja_template_loading()
    #     temp_name = f"{cls.__name__.lower()}_details.html"
    #     try:
    #         template = env.get_template(temp_name)
    #     except TemplateNotFound as e:
    #         logger.error(f"Couldn't find template {e}")
    #         template = env.get_template("equipment_details.html")
    #     return template


class EquipmentRole(BaseClass):
    """
    Abstract roles for equipment
    """

    id = Column(INTEGER, primary_key=True)  #: Role id, primary key
    name = Column(String(32))  #: Common name
    equipment = relationship("Equipment", back_populates="equipmentrole",
                             secondary=equipmentrole_equipment)  #: Concrete control (Equipment) of reagentrole
    process = relationship("Process", back_populates='equipmentrole',
                           secondary=equipmentrole_process)  #: Associated Processes

    equipmentroleproceduretypeassociation = relationship(
        "ProcedureTypeEquipmentRoleAssociation",
        back_populates="equipmentrole",
        cascade="all, delete-orphan",
    )  #: relation to SubmissionTypes

    proceduretype = association_proxy("equipmentroleproceduretypeassociation",
                                      "proceduretype")  #: proxy to equipmentroleproceduretypeassociation.proceduretype

    def to_dict(self) -> dict:
        """
        This EquipmentRole as a dictionary

        Returns:
            dict: This EquipmentRole dict
        """
        return {key: value for key, value in self.__dict__.items() if key != "process"}

    def to_pydantic(self, proceduretype: ProcedureType,
                    kittype: str | KitType | None = None) -> "PydEquipmentRole":
        """
        Creates a PydEquipmentRole of this EquipmentRole

        Args:
            proceduretype (SubmissionType): SubmissionType of interest
            kittype (str | KitType | None, optional): KitType of interest. Defaults to None.

        Returns:
            PydEquipmentRole: This EquipmentRole as PydEquipmentRole
        """
        from backend.validators.pydant import PydEquipmentRole
        equipment = [item.to_pydantic(proceduretype=proceduretype, kittype=kittype) for item in
                     self.equipment]
        pyd_dict = self.to_dict()
        pyd_dict['process'] = self.get_processes(proceduretype=proceduretype, kittype=kittype)
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
        logger.info(f"Instance from query or create: {instance}")
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

    def get_processes(self, proceduretype: str | ProcedureType | None,
                      kittype: str | KitType | None = None) -> Generator[Process, None, None]:
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
        if isinstance(kittype, str):
            kittype = KitType.query(name=kittype)
        for process in self.processes:
            if proceduretype and proceduretype not in process.proceduretype:
                continue
            if kittype and kittype not in process.kittype:
                continue
            yield process.name

    def to_omni(self, expand: bool = False) -> "OmniEquipmentRole":
        from backend.validators.omni_gui_objects import OmniEquipmentRole
        return OmniEquipmentRole(instance_object=self, name=self.name)


class ProcedureEquipmentAssociation(BaseClass):
    """
    Abstract association between BasicRun and Equipment
    """

    equipment_id = Column(INTEGER, ForeignKey("_equipment.id"), primary_key=True)  #: id of associated equipment
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    equipmentrole = Column(String(64), primary_key=True)  #: name of the reagentrole the equipment fills
    process_id = Column(INTEGER, ForeignKey("_process.id", ondelete="SET NULL",
                                            name="SEA_Process_id"))  #: Foreign key of process id
    start_time = Column(TIMESTAMP)  #: start time of equipment use
    end_time = Column(TIMESTAMP)  #: end time of equipment use
    comments = Column(String(1024))  #: comments about equipment

    procedure = relationship(Procedure,
                             back_populates="procedureequipmentassociation")  #: associated procedure

    equipment = relationship(Equipment, back_populates="equipmentprocedureassociation")  #: associated equipment

    def __repr__(self) -> str:
        return f"<ProcedureEquipmentAssociation({self.procedure.name} & {self.equipment.name})>"

    def __init__(self, procedure, equipment, equipmentrole: str = "None"):
        self.run = procedure
        self.equipment = equipment
        self.equipmentrole = equipmentrole

    @property
    def process(self):
        return Process.query(id=self.process_id)

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
        return PydEquipment(**self.to_sub_dict())

    @classmethod
    @setup_lookup
    def query(cls, equipment_id: int | None = None, run_id: int | None = None, equipmentrole: str | None = None,
              limit: int = 0, **kwargs) \
            -> Any | List[Any]:
        query: Query = cls.__database_session__.query(cls)
        query = query.filter(cls.equipment_id == equipment_id)
        query = query.filter(cls.run_id == run_id)
        if equipmentrole is not None:
            query = query.filter(cls.equipmentrole == equipmentrole)
        return cls.execute_query(query=query, limit=limit, **kwargs)


class ProcedureTypeEquipmentRoleAssociation(BaseClass):
    """
    Abstract association between SubmissionType and EquipmentRole
    """
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)  #: id of associated equipment
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"),
                              primary_key=True)  #: id of associated procedure
    uses = Column(JSON)  #: locations of equipment on the procedure type excel sheet.
    static = Column(INTEGER,
                    default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?

    proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypeequipmentroleassociation")  #: associated procedure

    equipmentrole = relationship(EquipmentRole,
                                 back_populates="equipmentroleproceduretypeassociation")  #: associated equipment

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


class Process(BaseClass):
    """
    A Process is a method used by a piece of equipment.
    """

    level = 2

    id = Column(INTEGER, primary_key=True)  #: Process id, primary key
    name = Column(String(64), unique=True)  #: Process name
    proceduretype = relationship("ProcedureType", back_populates='process',
                                 secondary=proceduretype_process)  #: relation to SubmissionType
    equipment = relationship("Equipment", back_populates='process',
                             secondary=equipment_process)  #: relation to Equipment
    equipmentrole = relationship("EquipmentRole", back_populates='process',
                                 secondary=equipmentrole_process)  #: relation to EquipmentRoles
    procedure = relationship("ProcedureEquipmentAssociation",
                             backref='process')  #: relation to RunEquipmentAssociation
    kittype = relationship("KitType", back_populates='process',
                           secondary=kittype_process)  #: relation to KitType
    tiprole = relationship("TipRole", back_populates='process',
                           secondary=process_tiprole)  #: relation to KitType

    def set_attribute(self, key, value):
        match key:
            case "name":
                self.name = value
            case _:
                field = getattr(self, key)
                if value not in field:
                    field.append(value)

    # @classmethod
    # def query_or_create(cls, **kwargs) -> Tuple[Process, bool]:
    #     new = False
    #     disallowed = ['expiry']
    #     sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
    #     instance = cls.query(**sanitized_kwargs)
    #     if not instance or isinstance(instance, list):
    #         instance = cls()
    #         new = True
    #     for k, v in sanitized_kwargs.items():
    #         setattr(instance, k, v)
    #     logger.info(f"Instance from query or create: {instance}")
    #     return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              id: int | None = None,
              proceduretype: str | ProcedureType | None = None,
              kittype: str | KitType | None = None,
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
        match kittype:
            case str():
                kittype = KitType.query(name=kittype)
                query = query.filter(cls.kittype.contains(kittype))
            case KitType():
                query = query.filter(cls.kittype.contains(kittype))
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
        )
        if full_data:
            subs = [dict(plate=sub.run.rsl_plate_num, equipment=sub.equipment.name,
                         submitted_date=sub.run.clientsubmission.submitted_date) for sub in self.procedure]
            output['procedure'] = sorted(subs, key=itemgetter("submitted_date"), reverse=True)
            output['excluded'] = ['missing', 'procedure', 'excluded', 'editable']
        return output

    # @classproperty
    # def details_template(cls) -> Template:
    #     """
    #     Get the details jinja template for the correct class
    #
    #     Args:
    #         base_dict (dict): incoming dictionary of Submission fields
    #
    #     Returns:
    #         Tuple(dict, Template): (Updated dictionary, Template to be rendered)
    #     """
    #     env = jinja_template_loading()
    #     temp_name = f"{cls.__name__.lower()}_details.html"
    #     try:
    #         template = env.get_template(temp_name)
    #     except TemplateNotFound as e:
    #         logger.error(f"Couldn't find template {e}")
    #         template = env.get_template("process_details.html")
    #     return template


class TipRole(BaseClass):
    """
    An abstract reagentrole that a tip fills during a process
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: name of reagent type
    tips = relationship("Tips", back_populates="tiprole",
                        secondary=tiprole_tips)  #: concrete control of this reagent type
    process = relationship("Process", back_populates="tiprole", secondary=process_tiprole)

    tiproleproceduretypeassociation = relationship(
        "ProcedureTypeTipRoleAssociation",
        back_populates="tiprole",
        cascade="all, delete-orphan"
    )  #: associated procedure

    proceduretype = association_proxy("tiproleproceduretypeassociation", "proceduretype")

    # @classmethod
    # def query_or_create(cls, **kwargs) -> Tuple[TipRole, bool]:
    #     new = False
    #     disallowed = ['expiry']
    #     sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
    #     instance = cls.query(**sanitized_kwargs)
    #     if not instance or isinstance(instance, list):
    #         instance = cls()
    #         new = True
    #     for k, v in sanitized_kwargs.items():
    #         setattr(instance, k, v)
    #     logger.info(f"Instance from query or create: {instance}")
    #     return instance, new

    @classmethod
    @setup_lookup
    def query(cls, name: str | None = None, limit: int = 0, **kwargs) -> TipRole | List[TipRole]:
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
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


class Tips(BaseClass, LogMixin):
    """
    A concrete instance of tips.
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    tiprole = relationship("TipRole", back_populates="tips",
                           secondary=tiprole_tips)  #: joined parent reagent type
    tiprole_id = Column(INTEGER, ForeignKey("_tiprole.id", ondelete='SET NULL',
                                            name="fk_tip_role_id"))  #: id of parent reagent type
    name = Column(String(64))  #: tip common name
    lot = Column(String(64))  #: lot number of tips
    equipment = relationship("Equipment", back_populates="tips",
                             secondary=equipment_tips)  #: associated procedure
    tipsprocedureassociation = relationship(
        "ProcedureTipsAssociation",
        back_populates="tips",
        cascade="all, delete-orphan"
    )  #: associated procedure

    procedure = association_proxy("tipsprocedureassociation", 'procedure')

    # @classmethod
    # def query_or_create(cls, **kwargs) -> Tuple[Tips, bool]:
    #     new = False
    #     disallowed = ['expiry']
    #     sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
    #     instance = cls.query(**sanitized_kwargs)
    #     if not instance or isinstance(instance, list):
    #         instance = cls()
    #         new = True
    #     for k, v in sanitized_kwargs.items():
    #         setattr(instance, k, v)
    #     logger.info(f"Instance from query or create: {instance}")
    #     return instance, new

    @classmethod
    def query(cls, name: str | None = None, lot: str | None = None, limit: int = 0, **kwargs) -> Tips | List[Tips]:
        """
        Lookup tips

        Args:
            name (str | None, optional): Informal name of tips. Defaults to None.
            lot (str | None, optional): Lot number. Defaults to None.
            limit (int, optional): Maximum number of results to return (0=all). Defaults to 0.

        Returns:
            Tips | List[Tips]: Tips matching criteria
        """
        query = cls.__database_session__.query(cls)
        match name:
            case str():
                query = query.filter(cls.name == name)
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
                dict(plate=item.procedure.procedure.rsl_plate_num, role=item.role_name,
                     sub_date=item.procedure.procedure.clientsubmission.submitted_date)
                for item in self.tipsprocedureassociation]
            output['procedure'] = sorted(subs, key=itemgetter("sub_date"), reverse=True)
            output['excluded'] = ['missing', 'procedure', 'excluded', 'editable']
        return output

    # @classproperty
    # def details_template(cls) -> Template:
    #     """
    #     Get the details jinja template for the correct class
    #
    #     Args:
    #         base_dict (dict): incoming dictionary of Submission fields
    #
    #     Returns:
    #         Tuple(dict, Template): (Updated dictionary, Template to be rendered)
    #     """
    #     env = jinja_template_loading()
    #     temp_name = f"{cls.__name__.lower()}_details.html"
    #     try:
    #         template = env.get_template(temp_name)
    #     except TemplateNotFound as e:
    #         logger.error(f"Couldn't find template {e}")
    #         template = env.get_template("tips_details.html")
    #     return template


class ProcedureTypeTipRoleAssociation(BaseClass):
    """
   Abstract association between SubmissionType and TipRole
   """
    tiprole_id = Column(INTEGER, ForeignKey("_tiprole.id"), primary_key=True)  #: id of associated equipment
    proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id"),
                              primary_key=True)  #: id of associated procedure
    uses = Column(JSON)  #: locations of equipment on the procedure type excel sheet.
    static = Column(INTEGER,
                    default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?
    proceduretype = relationship(ProcedureType,
                                 back_populates="proceduretypetiproleassociation")  #: associated procedure
    tiprole = relationship(TipRole,
                           back_populates="tiproleproceduretypeassociation")  #: associated equipment

    @check_authorization
    def save(self):
        super().save()

    def to_omni(self):
        pass


class ProcedureTipsAssociation(BaseClass):
    """
    Association between a concrete procedure instance and concrete tips
    """
    tips_id = Column(INTEGER, ForeignKey("_tips.id"), primary_key=True)  #: id of associated equipment
    procedure_id = Column(INTEGER, ForeignKey("_procedure.id"), primary_key=True)  #: id of associated procedure
    procedure = relationship("Procedure",
                             back_populates="proceduretipsassociation")  #: associated procedure
    tips = relationship(Tips,
                        back_populates="tipsprocedureassociation")  #: associated equipment
    role_name = Column(String(32), primary_key=True)  #, ForeignKey("_tiprole.name"))

    def to_sub_dict(self) -> dict:
        """
        This item as a dictionary

        Returns:
            dict: Values of this object
        """
        return dict(role=self.role_name, name=self.tips.name, lot=self.tips.lot)

    @classmethod
    @setup_lookup
    def query(cls, tips_id: int, role_name: str, procedure_id: int | None = None, limit: int = 0, **kwargs) \
            -> Any | List[Any]:
        query: Query = cls.__database_session__.query(cls)
        query = query.filter(cls.tips_id == tips_id)
        if procedure_id is not None:
            query = query.filter(cls.procedure_id == procedure_id)
        query = query.filter(cls.role_name == role_name)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    # TODO: fold this into the BaseClass.query_or_create ?
    @classmethod
    def query_or_create(cls, tips, run, role: str, **kwargs):
        kwargs['limit'] = 1
        instance = cls.query(tips_id=tips.id, role_name=role, procedure_id=run.id, **kwargs)
        if instance is None:
            instance = cls(run=run, tips=tips, role_name=role)
        return instance

    def to_pydantic(self):
        from backend.validators import PydTips
        return PydTips(name=self.tips.name, lot=self.tips.lot, role=self.role_name)

#
# class ProcedureType(BaseClass):
#     id = Column(INTEGER, primary_key=True)
#     name = Column(String(64))
#     reagent_map = Column(JSON)
#
#     procedure = relationship("Procedure",
#                              back_populates="proceduretype")  #: Concrete control of this type.
#
#     process = relationship("Process", back_populates="proceduretype",
#                            secondary=proceduretype_process)  #: Relation to equipment process used for this type.
#
#     proceduretypekittypeassociation = relationship(
#         "ProcedureTypeKitTypeAssociation",
#         back_populates="proceduretype",
#         cascade="all, delete-orphan",
#     )  #: Association of kittypes
#
#     kittype = association_proxy("proceduretypekittypeassociation", "kittype",
#                                 creator=lambda kit: ProcedureTypeKitTypeAssociation(
#                                     kittype=kit))  #: Proxy of kittype association
#
#     proceduretypeequipmentroleassociation = relationship(
#         "ProcedureTypeEquipmentRoleAssociation",
#         back_populates="proceduretype",
#         cascade="all, delete-orphan"
#     )  #: Association of equipmentroles
#
#     equipment = association_proxy("proceduretypeequipmentroleassociation", "equipmentrole",
#                                   creator=lambda eq: ProcedureTypeEquipmentRoleAssociation(
#                                       equipment_role=eq))  #: Proxy of equipmentrole associations
#
#     kittypereagentroleassociation = relationship(
#         "KitTypeReagentRoleAssociation",
#         back_populates="proceduretype",
#         cascade="all, delete-orphan"
#     )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes
#
#     proceduretypetiproleassociation = relationship(
#         "ProcedureTypeTipRoleAssociation",
#         back_populates="proceduretype",
#         cascade="all, delete-orphan"
#     )  #: Association of tiproles
#
#     def construct_field_map(self, field: Literal['equipment', 'tip']) -> Generator[(str, dict), None, None]:
#         """
#         Make a map of all locations for tips or equipment.
#
#         Args:
#             field (Literal['equipment', 'tip']): the field to construct a map for
#
#         Returns:
#             Generator[(str, dict), None, None]: Generator composing key, locations for each item in the map
#         """
#         for item in self.__getattribute__(f"proceduretype{field}role_associations"):
#             fmap = item.uses
#             if fmap is None:
#                 fmap = {}
#             yield getattr(item, f"{field}_role").name, fmap
#
#     @property
#     def default_kit(self) -> KitType | None:
#         """
#         If only one kits exists for this Submission Type, return it.
#
#         Returns:
#             KitType | None:
#         """
#         if len(self.kittype) == 1:
#             return self.kittype[0]
#         else:
#             return None
#
#     def get_equipment(self, kittype: str | KitType | None = None) -> Generator['PydEquipmentRole', None, None]:
#         """
#         Returns PydEquipmentRole of all equipment associated with this SubmissionType
#
#         Returns:
#             Generator['PydEquipmentRole', None, None]: List of equipment roles
#         """
#         return (item.to_pydantic(proceduretype=self, kittype=kittype) for item in self.equipment)
#
#     def get_processes_for_role(self, equipmentrole: str | EquipmentRole, kittype: str | KitType | None = None) -> list:
#         """
#         Get process associated with this SubmissionType for an EquipmentRole
#
#         Args:
#             equipmentrole (str | EquipmentRole): EquipmentRole of interest
#             kittype (str | KitType | None, optional): Kit of interest. Defaults to None.
#
#         Raises:
#             TypeError: Raised if wrong type given for equipmentrole
#
#         Returns:
#             list: list of associated process
#         """
#         match equipmentrole:
#             case str():
#                 relevant = [item.get_all_processes(kittype) for item in self.proceduretypeequipmentroleassociation if
#                             item.equipmentrole.name == equipmentrole]
#             case EquipmentRole():
#                 relevant = [item.get_all_processes(kittype) for item in self.proceduretypeequipmentroleassociation if
#                             item.equipmentrole == equipmentrole]
#             case _:
#                 raise TypeError(f"Type {type(equipmentrole)} is not allowed")
#         return list(set([item for items in relevant for item in items if item is not None]))
#
#
# class Procedure(BaseClass):
#     id = Column(INTEGER, primary_key=True)
#     name = Column(String, unique=True)
#     technician = Column(JSON)  #: name of processing tech(s)
#     proceduretype_id = Column(INTEGER, ForeignKey("_proceduretype.id", ondelete="SET NULL",
#                                                   name="fk_PRO_proceduretype_id"))  #: client lab id from _organizations))
#     proceduretype = relationship("ProcedureType", back_populates="procedure")
#     run_id = Column(INTEGER, ForeignKey("_run.id", ondelete="SET NULL",
#                                         name="fk_PRO_basicrun_id"))  #: client lab id from _organizations))
#     run = relationship("Run", back_populates="procedure")
#     kittype_id = Column(INTEGER, ForeignKey("_kittype.id", ondelete="SET NULL",
#                                             name="fk_PRO_kittype_id"))  #: client lab id from _organizations))
#     kittype = relationship("KitType", back_populates="procedure")
#
#     control = relationship("Control", back_populates="procedure",
#                             uselist=True)  #: A control sample added to procedure
#
#     procedurereagentassociations = relationship(
#         "ProcedureReagentAssociation",
#         back_populates="procedure",
#         cascade="all, delete-orphan",
#     )  #: Relation to ProcedureReagentAssociation
#
#     reagents = association_proxy("procedurereagentassociations",
#                                  "reagent")  #: Association proxy to RunReagentAssociation.reagent
#
#     procedureequipmentassociations = relationship(
#         "ProcedureEquipmentAssociation",
#         back_populates="procedure",
#         cascade="all, delete-orphan"
#     )  #: Relation to Equipment
#
#     equipment = association_proxy("procedureequipmentassociations",
#                                   "equipment")  #: Association proxy to RunEquipmentAssociation.equipment
#
#     proceduretipsassociations = relationship(
#         "ProcedureTipsAssociation",
#         back_populates="procedure",
#         cascade="all, delete-orphan")
#
#     tips = association_proxy("proceduretipsassociations",
#                              "tips")
#
#     @classmethod
#     @setup_lookup
#     def query(cls, id: int|None = None, name: str | None = None, limit: int = 0, **kwargs) -> Procedure | List[Procedure]:
#         query: Query = cls.__database_session__.query(cls)
#         match id:
#             case int():
#                 query = query.filter(cls.id == id)
#                 limit = 1
#             case _:
#                 pass
#         match name:
#             case str():
#                 query = query.filter(cls.name == name)
#                 limit = 1
#             case _:
#                 pass
#         return cls.execute_query(query=query, limit=limit)
