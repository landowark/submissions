"""
All kit and reagent related models
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
from typing import List, Literal, Generator, Any, Tuple
from pandas import ExcelFile
from pathlib import Path
from . import Base, BaseClass, Organization, LogMixin
from io import BytesIO

logger = logging.getLogger(f'submissions.{__name__}')

reagentroles_reagents = Table(
    "_reagentroles_reagents",
    Base.metadata,
    Column("reagent_id", INTEGER, ForeignKey("_reagent.id")),
    Column("reagentrole_id", INTEGER, ForeignKey("_reagentrole.id")),
    extend_existing=True
)

equipmentroles_equipment = Table(
    "_equipmentroles_equipment",
    Base.metadata,
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_equipmentrole.id")),
    extend_existing=True
)

equipment_processes = Table(
    "_equipment_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    extend_existing=True
)

equipmentroles_processes = Table(
    "_equipmentroles_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentrole_id", INTEGER, ForeignKey("_equipmentrole.id")),
    extend_existing=True
)

submissiontypes_processes = Table(
    "_submissiontypes_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_submissiontype.id")),
    extend_existing=True
)

kittypes_processes = Table(
    "_kittypes_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("kit_id", INTEGER, ForeignKey("_kittype.id")),
    extend_existing=True
)

tiproles_tips = Table(
    "_tiproles_tips",
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

kittypes_submissions = Table(
    "_kittypes_submissions",
    Base.metadata,
    Column("_basicsubmission_id", INTEGER, ForeignKey("_basicsubmission.id")),
    Column("kittype_id", INTEGER, ForeignKey("_kittype.id")),
    extend_existing=True
)


class KitType(BaseClass):
    """
    Base of kits used in submission processing
    """

    omni_sort = BaseClass.omni_sort + ["kit_submissiontype_associations", "kit_reagentrole_associations", "processes"]

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), unique=True)  #: name of kit
    submissions = relationship("BasicSubmission", back_populates="kittypes",
                               secondary=kittypes_submissions)  #: submissions this kit was used for
    processes = relationship("Process", back_populates="kit_types",
                             secondary=kittypes_processes)  #: equipment processes used by this kit

    kit_reagentrole_associations = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="kit_type",
        cascade="all, delete-orphan",
    )

    # NOTE: creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    reagent_roles = association_proxy("kit_reagentrole_associations", "reagent_role",
                                      creator=lambda RT: KitTypeReagentRoleAssociation(
                                          reagent_role=RT))  #: Association proxy to KitTypeReagentRoleAssociation

    kit_submissiontype_associations = relationship(
        "SubmissionTypeKitTypeAssociation",
        back_populates="kit_type",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionType

    used_for = association_proxy("kit_submissiontype_associations", "submission_type",
                                 creator=lambda ST: SubmissionTypeKitTypeAssociation(
                                     submission_type=ST))  #: Association proxy to SubmissionTypeKitTypeAssociation

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.

        Returns:
            List[str]: List of names
        """
        return super().aliases + [cls.query_alias, "kit_types", "kit_type"]

    @hybrid_property
    def submissiontype(self):
        """Alias used_for field to allow query with SubmissionType query alias"""
        return self.used_for

    def get_reagents(self,
                     required_only: bool = False,
                     submission_type: str | SubmissionType | None = None
                     ) -> Generator[ReagentRole, None, None]:
        """
        Return ReagentTypes linked to kit through KitTypeReagentTypeAssociation.

        Args:
            required_only (bool, optional): If true only return required types. Defaults to False.
            submission_type (str | Submissiontype | None, optional): Submission type to narrow results. Defaults to None.

        Returns:
            Generator[ReagentRole, None, None]: List of reagent roles linked to this kit.
        """
        match submission_type:
            case SubmissionType():
                relevant_associations = [item for item in self.kit_reagentrole_associations if
                                         item.submission_type == submission_type]
            case str():
                relevant_associations = [item for item in self.kit_reagentrole_associations if
                                         item.submission_type.name == submission_type]
            case _:
                relevant_associations = [item for item in self.kit_reagentrole_associations]
        if required_only:
            return (item.reagent_role for item in relevant_associations if item.required == 1)
        else:
            return (item.reagent_role for item in relevant_associations)

    def construct_xl_map_for_use(self, submission_type: str | SubmissionType) -> Tuple[dict | None, KitType]:
        """
        Creates map of locations in Excel workbook for a SubmissionType

        Args:
            submission_type (str | SubmissionType): Submissiontype.name

        Returns:
            Generator[(str, str), None, None]: Tuple containing information locations.
        """
        new_kit = self
        # NOTE: Account for submission_type variable type.
        match submission_type:
            case str():
                # logger.debug(f"Query for {submission_type}")
                submission_type = SubmissionType.query(name=submission_type)
            case SubmissionType():
                pass
            case _:
                raise ValueError(f"Wrong variable type: {type(submission_type)} used!")
        # logger.debug(f"Submission type: {submission_type}, Kit: {self}")
        assocs = [item for item in self.kit_reagentrole_associations if item.submission_type == submission_type]
        # logger.debug(f"Associations: {assocs}")
        # NOTE: rescue with submission type's default kit.
        if not assocs:
            logger.error(
                f"No associations found with {self}. Attempting rescue with default kit: {submission_type.default_kit}")
            new_kit = submission_type.default_kit
            if not new_kit:
                from frontend.widgets.pop_ups import ObjectSelector
                dlg = ObjectSelector(
                    title="Select Kit",
                    message="Could not find reagents for this submission type/kit type combo.\nSelect new kit.",
                    obj_type=self.__class__,
                    values=[kit.name for kit in submission_type.kit_types]
                )
                if dlg.exec():
                    dlg_result = dlg.parse_form()
                    # logger.debug(f"Dialog result: {dlg_result}")
                    new_kit = self.__class__.query(name=dlg_result)
                    # logger.debug(f"Query result: {new_kit}")
                else:
                    return None, new_kit
            assocs = [item for item in new_kit.kit_reagentrole_associations if item.submission_type == submission_type]
        output = {assoc.reagent_role.name: assoc.uses for assoc in assocs}
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
              submissiontype: str | SubmissionType | None = None,
              id: int | None = None,
              limit: int = 0,
              **kwargs
              ) -> KitType | List[KitType]:
        """
        Lookup a list of or single KitType.

        Args:
            name (str, optional): Name of desired kit (returns single instance). Defaults to None.
            submissiontype (str | Submissiontype | None, optional): Submission type the kit is used for. Defaults to None.
            id (int | None, optional): Kit id in the database. Defaults to None.
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            KitType|List[KitType]: KitType(s) of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match submissiontype:
            case str():
                query = query.filter(cls.submissiontype.any(name=submissiontype))
            case SubmissionType():
                query = query.filter(cls.submissiontype.contains(submissiontype))
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

    # def to_export_dict(self, submission_type: SubmissionType) -> dict:
    #     """
    #     Creates dictionary for exporting to yml used in new SubmissionType Construction
    #
    #     Args:
    #         submission_type (SubmissionType): SubmissionType of interest.
    #
    #     Returns:
    #         dict: Dictionary containing relevant info for SubmissionType construction
    #     """
    #     base_dict = dict(name=self.name, reagent_roles=[], equipment_roles=[])
    #     for key, value in self.construct_xl_map_for_use(submission_type=submission_type):
    #         try:
    #             assoc = next(item for item in self.kit_reagentrole_associations if item.reagent_role.name == key)
    #         except StopIteration as e:
    #             continue
    #         for kk, vv in assoc.to_export_dict().items():
    #             value[kk] = vv
    #         base_dict['reagent_roles'].append(value)
    #     for key, value in submission_type.construct_field_map("equipment"):
    #         try:
    #             assoc = next(item for item in submission_type.submissiontype_equipmentrole_associations if
    #                          item.equipment_role.name == key)
    #         except StopIteration:
    #             continue
    #         for kk, vv in assoc.to_export_dict(extraction_kit=self).items():
    #             value[kk] = vv
    #         base_dict['equipment_roles'].append(value)
    #     return base_dict

    # @classmethod
    # def import_from_yml(cls, submission_type: str | SubmissionType, filepath: Path | str | None = None,
    #                     import_dict: dict | None = None) -> KitType:
    #     if isinstance(submission_type, str):
    #         submission_type = SubmissionType.query(name=submission_type)
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
    #     new_kit = KitType.query(name=import_dict['kit_type']['name'])
    #     if not new_kit:
    #         new_kit = KitType(name=import_dict['kit_type']['name'])
    #     for role in import_dict['kit_type']['reagent_roles']:
    #         new_role = ReagentRole.query(name=role['role'])
    #         if new_role:
    #             check = input(f"Found existing role: {new_role.name}. Use this? [Y/n]: ")
    #             if check.lower() == "n":
    #                 new_role = None
    #             else:
    #                 pass
    #         if not new_role:
    #             eol = timedelta(role['extension_of_life'])
    #             new_role = ReagentRole(name=role['role'], eol_ext=eol)
    #         uses = dict(expiry=role['expiry'], lot=role['lot'], name=role['name'], sheet=role['sheet'])
    #         ktrr_assoc = KitTypeReagentRoleAssociation(kit_type=new_kit, reagent_role=new_role, uses=uses)
    #         ktrr_assoc.submission_type = submission_type
    #         ktrr_assoc.required = role['required']
    #     ktst_assoc = SubmissionTypeKitTypeAssociation(
    #         kit_type=new_kit,
    #         submission_type=submission_type,
    #         mutable_cost_sample=import_dict['mutable_cost_sample'],
    #         mutable_cost_column=import_dict['mutable_cost_column'],
    #         constant_cost=import_dict['constant_cost']
    #     )
    #     for role in import_dict['kit_type']['equipment_roles']:
    #         new_role = EquipmentRole.query(name=role['role'])
    #         if new_role:
    #             check = input(f"Found existing role: {new_role.name}. Use this? [Y/n]: ")
    #             if check.lower() == "n":
    #                 new_role = None
    #             else:
    #                 pass
    #         if not new_role:
    #             new_role = EquipmentRole(name=role['role'])
    #             for equipment in Equipment.assign_equipment(equipment_role=new_role):
    #                 new_role.instances.append(equipment)
    #         ster_assoc = SubmissionTypeEquipmentRoleAssociation(submission_type=submission_type,
    #                                                             equipment_role=new_role)
    #         try:
    #             uses = dict(name=role['name'], process=role['process'], sheet=role['sheet'],
    #                         static=role['static'])
    #         except KeyError:
    #             uses = None
    #         ster_assoc.uses = uses
    #         for process in role['processes']:
    #             new_process = Process.query(name=process)
    #             if not new_process:
    #                 new_process = Process(name=process)
    #             new_process.submission_types.append(submission_type)
    #             new_process.kit_types.append(new_kit)
    #             new_process.equipment_roles.append(new_role)
    #     return new_kit

    def to_omni(self, expand: bool = False) -> "OmniKitType":
        from backend.validators.omni_gui_objects import OmniKitType
        if expand:
            processes = [item.to_omni() for item in self.processes]
            kit_reagentrole_associations = [item.to_omni() for item in self.kit_reagentrole_associations]
            kit_submissiontype_associations = [item.to_omni() for item in self.kit_submissiontype_associations]
        else:
            processes = [item.name for item in self.processes]
            kit_reagentrole_associations = [item.name for item in self.kit_reagentrole_associations]
            kit_submissiontype_associations = [item.name for item in self.kit_submissiontype_associations]
        data = dict(
            name=self.name,
            processes=processes,
            kit_reagentrole_associations=kit_reagentrole_associations,
            kit_submissiontype_associations=kit_submissiontype_associations
        )
        # logger.debug(f"Creating omni for {pformat(data)}")
        return OmniKitType(instance_object=self, **data)


class ReagentRole(BaseClass):
    """
    Base of reagent type abstract
    """

    skip_on_edit = False
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: name of role reagent plays
    instances = relationship("Reagent", back_populates="role",
                             secondary=reagentroles_reagents)  #: concrete instances of this reagent type
    eol_ext = Column(Interval())  #: extension of life interval

    reagentrole_kit_associations = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="reagent_role",
        cascade="all, delete-orphan",
    )  #: Relation to KitTypeReagentTypeAssociation

    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
    kit_types = association_proxy("reagentrole_kit_associations", "kit_type",
                                  creator=lambda kit: KitTypeReagentRoleAssociation(
                                      kit_type=kit))  #: Association proxy to KitTypeReagentRoleAssociation

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
            ValueError: Raised if only kit_type or reagent, not both, given.

        Returns:
            ReagentRole|List[ReagentRole]: ReagentRole or list of ReagentRoles matching filter.
        """
        query: Query = cls.__database_session__.query(cls)
        if (kittype is not None and reagent is None) or (reagent is not None and kittype is None):
            raise ValueError("Cannot filter without both reagent and kit type.")
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
            # NOTE: Get all roles common to the reagent and the kit.
            result = set(kittype.reagent_roles).intersection(reagent.role)
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
        return PydReagent(lot=None, role=self.name, name=self.name, expiry=date.today())

    # def to_export_dict(self) -> dict:
    #     """
    #     Creates dictionary for exporting to yml used in new SubmissionType Construction
    #
    #     Returns:
    #         dict: Dictionary containing relevant info for SubmissionType construction
    #     """
    #     return dict(role=self.name, extension_of_life=self.eol_ext.days)

    @check_authorization
    def save(self):
        super().save()

    def to_omni(self, expand: bool=False):
        from backend.validators.omni_gui_objects import OmniReagentRole
        logger.debug(f"Constructing OmniReagentRole with name {self.name}")
        return OmniReagentRole(instance_object=self, name=self.name, eol_ext=self.eol_ext)


class Reagent(BaseClass, LogMixin):
    """
    Concrete reagent instance
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    role = relationship("ReagentRole", back_populates="instances",
                        secondary=reagentroles_reagents)  #: joined parent reagent type
    role_id = Column(INTEGER, ForeignKey("_reagentrole.id", ondelete='SET NULL',
                                         name="fk_reagent_role_id"))  #: id of parent reagent type
    name = Column(String(64))  #: reagent name
    lot = Column(String(64))  #: lot number of reagent
    expiry = Column(TIMESTAMP)  #: expiry date - extended by eol_ext of parent programmatically

    reagent_submission_associations = relationship(
        "SubmissionReagentAssociation",
        back_populates="reagent",
        cascade="all, delete-orphan",
    )  #: Relation to SubmissionSampleAssociation

    submissions = association_proxy("reagent_submission_associations", "submission",
                                    creator=lambda sub: SubmissionReagentAssociation(
                                        submission=sub))  #: Association proxy to SubmissionSampleAssociation.samples

    def __repr__(self):
        if self.name:
            name = f"<Reagent({self.name}-{self.lot})>"
        else:
            name = f"<Reagent({self.role.name}-{self.lot})>"
        return name

    @classproperty
    def searchables(cls):
        return [dict(label="Lot", field="lot")]

    @hybrid_property
    def reagentrole(self):
        """Alias role field to allow query with ReagentRole query alias"""
        return self.role

    def to_sub_dict(self, extraction_kit: KitType = None, full_data: bool = False, **kwargs) -> dict:
        """
        dictionary containing values necessary for gui

        Args:
            extraction_kit (KitType, optional): KitType to use to get reagent type. Defaults to None.
            full_data (bool, optional): Whether to include submissions in data for details. Defaults to False.

        Returns:
            dict: representation of the reagent's attributes
        """
        if extraction_kit is not None:
            # NOTE: Get the intersection of this reagent's ReagentType and all ReagentTypes in KitType
            reagent_role = next((item for item in set(self.role).intersection(extraction_kit.reagent_roles)),
                                self.role[0])
        else:
            try:
                reagent_role = self.role[0]
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
            role=rtype,
            lot=self.lot,
            expiry=place_holder,
            missing=False
        )
        if full_data:
            output['submissions'] = [sub.rsl_plate_num for sub in self.submissions]
            output['excluded'] = ['missing', 'submissions', 'excluded', 'editable']
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
            if "role" not in kwargs:
                try:
                    kwargs['role'] = kwargs['name']
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
              role: str | ReagentRole | None = None,
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
        match role:
            case str():
                query = query.join(cls.role).filter(ReagentRole.name == role)
            case ReagentRole():
                query = query.filter(cls.role.contains(role))
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
            case "role":
                match value:
                    case ReagentRole():
                        role = value
                    case str():
                        role = ReagentRole.query(name=value, limit=1)
                    case _:
                        return
                if role and role not in self.role:
                    self.role.append(role)
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
            expiry="Use exact date on reagent.\nEOL will be calculated from kit automatically"
        )


class Discount(BaseClass):
    """
    Relationship table for client labs for certain kits.
    """

    skip_on_edit = True

    id = Column(INTEGER, primary_key=True)  #: primary key
    kit = relationship("KitType")  #: joined parent reagent type
    kit_id = Column(INTEGER, ForeignKey("_kittype.id", ondelete='SET NULL', name="fk_kit_type_id"))  #: id of joined kit
    client = relationship("Organization")  #: joined client lab
    client_id = Column(INTEGER,
                       ForeignKey("_organization.id", ondelete='SET NULL', name="fk_org_id"))  #: id of joined client
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
              organization: Organization | str | int | None = None,
              kittype: KitType | str | int | None = None,
              ) -> Discount | List[Discount]:
        """
        Lookup discount objects (union of kit and organization)

        Args:
            organization (models.Organization | str | int): Organization receiving discount.
            kit_type (models.KitType | str | int): Kit discount received on.

        Returns:
            models.Discount|List[models.Discount]: Discount(s) of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match organization:
            case Organization():
                query = query.filter(cls.client == Organization)
            case str():
                query = query.join(Organization).filter(Organization.name == organization)
            case int():
                query = query.join(Organization).filter(Organization.id == organization)
            case _:
                pass
        match kittype:
            case KitType():
                query = query.filter(cls.kit == kittype)
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
    Abstract of types of submissions.
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(128), unique=True)  #: name of submission type
    info_map = Column(JSON)  #: Where parsable information is found in the excel workbook corresponding to this type.
    defaults = Column(JSON)  #: Basic information about this submission type
    instances = relationship("ClientSubmission", back_populates="submission_type")  #: Concrete instances of this type.
    template_file = Column(BLOB)  #: Blank form for this type stored as binary.
    processes = relationship("Process", back_populates="submission_types",
                             secondary=submissiontypes_processes)  #: Relation to equipment processes used for this type.
    sample_map = Column(JSON)  #: Where sample information is found in the excel sheet corresponding to this type.

    """
    Example info_map (Bacterial Culture)
    NOTE: read locations will be appended to write locations. 
    
    {
        "comment": {
            "read": [
                {
                    "column": 2,
                    "row": 34,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "contact": {
            "read": [
                {
                    "column": 2,
                    "row": 4,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "contact_phone": {
            "read": [],
            "write": [
                {
                    "column": 2,
                    "row": 5,
                    "sheet": "Sample List"
                }
            ]
        },
        "cost_centre": {
            "read": [
                {
                    "column": 2,
                    "row": 6,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "custom": {},
        "extraction_kit": {
            "read": [
                {
                    "column": 4,
                    "row": 5,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "rsl_plate_num": {
            "read": [
                {
                    "column": 2,
                    "row": 13,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "sample_count": {
            "read": [
                {
                    "column": 4,
                    "row": 4,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "signed_by": {
            "read": [],
            "write": [
                {
                    "column": 2,
                    "row": 15,
                    "sheet": "Sample List"
                }
            ]
        },
        "submission_category": {
            "read": [
                {
                    "column": 4,
                    "row": 6,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "submission_type": {
            "read": [
                {
                    "column": 4,
                    "row": 3,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "submitted_date": {
            "read": [
                {
                    "column": 2,
                    "row": 3,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "submitter_plate_num": {
            "read": [
                {
                    "column": 2,
                    "row": 2,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "submitting_lab": {
            "read": [
                {
                    "column": 4,
                    "row": 2,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        },
        "technician": {
            "read": [
                {
                    "column": 2,
                    "row": 14,
                    "sheet": "Sample List"
                }
            ],
            "write": []
        }
    }
    """

    """
    Example defaults (for Bacterial Culture)
    
    {
        "abbreviation": "BC",
        "details_ignore": [
            "controls"
        ],
        "form_ignore": [
            "controls",
            "cost_centre"
        ],
        "regex": "(?P<Bacterial_Culture>RSL(?:-|_)?BC(?:-|_)?20\\d{2}-?\\d{2}-?\\d{2}(?:(_|-)?\\d?([^_0123456789\\sA-QS-Z]|$)?R?\\d?)?)",
        "sample_type": "Bacterial Culture Sample",
        "turnaround_time": 3
    }
    """

    """
    Example sample_map (Bacterial Culture)
    
    {
        "lookup_table": {
            "end_row": 132,
            "merge_on_id": "submitter_id",
            "sample_columns": {
                "column": 6,
                "concentration": 4,
                "organism": 3,
                "row": 5,
                "submitter_id": 2
            },
            "sheet": "Sample List",
            "start_row": 37
        },
        "plate_map": {
            "end_column": 13,
            "end_row": 14,
            "sheet": "Plate Map",
            "start_column": 2,
            "start_row": 7
        }
    }
    """

    submissiontype_kit_associations = relationship(
        "SubmissionTypeKitTypeAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan",
    )  #: Association of kittypes

    kit_types = association_proxy("submissiontype_kit_associations", "kit_type",
                                  creator=lambda kit: SubmissionTypeKitTypeAssociation(
                                      kit_type=kit))  #: Proxy of kittype association

    submissiontype_equipmentrole_associations = relationship(
        "SubmissionTypeEquipmentRoleAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan"
    )  #: Association of equipmentroles

    equipment = association_proxy("submissiontype_equipmentrole_associations", "equipment_role",
                                  creator=lambda eq: SubmissionTypeEquipmentRoleAssociation(
                                      equipment_role=eq))  #: Proxy of equipmentrole associations

    submissiontype_kit_rt_associations = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan"
    )  #: triple association of KitTypes, ReagentTypes, SubmissionTypes

    submissiontype_tiprole_associations = relationship(
        "SubmissionTypeTipRoleAssociation",
        back_populates="submission_type",
        cascade="all, delete-orphan"
    )  #: Association of tiproles

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object.
        """
        return f"<SubmissionType({self.name})>"

    @hybrid_property
    def kittype(self):
        return self.kit_types

    @hybrid_property
    def process(self):
        return self.processes

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.

        Returns:
            List[str]: List of names
        """
        return super().aliases + ["submission_types", "submission_type"]

    @classproperty
    def omni_removes(cls):
        return super().omni_removes + ["defaults", "instances"]

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

    @property
    def default_kit(self) -> KitType | None:
        """
        If only one kits exists for this Submission Type, return it.

        Returns:
            KitType | None:
        """
        if len(self.kit_types) == 1:
            return self.kit_types[0]
        else:
            return None

    def get_equipment(self, extraction_kit: str | KitType | None = None) -> Generator['PydEquipmentRole', None, None]:
        """
        Returns PydEquipmentRole of all equipment associated with this SubmissionType

        Returns:
            Generator['PydEquipmentRole', None, None]: List of equipment roles
        """
        return (item.to_pydantic(submission_type=self, extraction_kit=extraction_kit) for item in self.equipment)

    def get_processes_for_role(self, equipment_role: str | EquipmentRole, kit: str | KitType | None = None) -> list:
        """
        Get processes associated with this SubmissionType for an EquipmentRole

        Args:
            equipment_role (str | EquipmentRole): EquipmentRole of interest
            kit (str | KitType | None, optional): Kit of interest. Defaults to None.

        Raises:
            TypeError: Raised if wrong type given for equipmentrole

        Returns:
            list: list of associated processes
        """
        match equipment_role:
            case str():
                relevant = [item.get_all_processes(kit) for item in self.submissiontype_equipmentrole_associations if
                            item.equipment_role.name == equipment_role]
            case EquipmentRole():
                relevant = [item.get_all_processes(kit) for item in self.submissiontype_equipmentrole_associations if
                            item.equipment_role == equipment_role]
            case _:
                raise TypeError(f"Type {type(equipment_role)} is not allowed")
        return list(set([item for items in relevant for item in items if item is not None]))

    @property
    def submission_class(self) -> "BasicSubmission":
        """
        Gets submission class associated with this submission type.

        Returns:
            BasicSubmission: Submission class
        """
        from .submissions import BasicSubmission
        return BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.name)

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
        logger.info(f"Instance from submissiontype query or create: {instance}")
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
        Lookup submission type in the database by a number of parameters

        Args:
            name (str | None, optional): Name of submission type. Defaults to None.
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

    # def to_export_dict(self):
    #     """
    #     Creates dictionary for exporting to yml used in new SubmissionType Construction
    #
    #     Returns:
    #         dict: Dictionary containing relevant info for SubmissionType construction
    #     """
    #     base_dict = dict(name=self.name)
    #     base_dict['info'] = self.construct_info_map(mode='export')
    #     base_dict['defaults'] = self.defaults
    #     # base_dict['samples'] = self.construct_sample_map()
    #     base_dict['samples'] = self.sample_map
    #     base_dict['kits'] = [item.to_export_dict() for item in self.submissiontype_kit_associations]
    #     return base_dict

    @check_authorization
    def save(self):
        """
        Adds this instances to the database and commits.
        """
        super().save()

    @classmethod
    @check_authorization
    def import_from_json(cls, filepath: Path | str) -> SubmissionType:
        """
        Creates a new SubmissionType from a yml file

        Args:
            filepath (Path | str): Input yml file.

        Raises:
            Exception: Raised if filetype is not a yml or json

        Returns:
            SubmissionType: Created SubmissionType
        """
        full = True
        yaml.add_constructor("!regex", yaml_regex_creator)
        if isinstance(filepath, str):
            filepath = Path(filepath)
        with open(filepath, "r") as f:
            if filepath.suffix == ".json":
                import_dict = json.load(fp=f)
            elif filepath.suffix == ".yml":
                import_dict = yaml.load(stream=f, Loader=yaml.Loader)
            else:
                raise Exception(f"Filetype {filepath.suffix} not supported.")
        try:
            submission_type = cls.query(name=import_dict['name'])
        except KeyError:
            logger.error(f"Submission type has no name")
            submission_type = None
            full = False
        if full:
            if submission_type:
                return submission_type
            submission_type = cls()
            submission_type.name = import_dict['name']
            submission_type.info_map = import_dict['info']
            submission_type.sample_map = import_dict['samples']
            submission_type.defaults = import_dict['defaults']
            for kit in import_dict['kits']:
                new_kit = KitType.import_from_yml(submission_type=submission_type, import_dict=kit)
        if 'orgs' in import_dict.keys():
            logger.info("Found Organizations to be imported.")
            Organization.import_from_yml(filepath=filepath)
        return submission_type

    def to_omni(self, expand: bool = False):
        from backend.validators.omni_gui_objects import OmniSubmissionType
        try:
            template_file = self.template_file
        except AttributeError:
            template_file = bytes()
        if expand:
            try:
                processes = [item.to_omni() for item in self.processes]
            except AttributeError:
                processes = []
        else:
            processes = [item.name for item in self.processes]
        return OmniSubmissionType(
            instance_object=self,
            name=self.name,
            info_map=self.info_map,
            defaults=self.defaults,
            template_file=template_file,
            processes=processes,
            sample_map=self.sample_map
        )

    @classproperty
    def info_map_json_edit_fields(cls):
        dicto = dict()
        return dicto


class SubmissionTypeKitTypeAssociation(BaseClass):
    """
    Abstract of relationship between kits and their submission type.
    """

    omni_removes = BaseClass.omni_removes + ["submission_types_id", "kits_id"]
    omni_sort = ["submission_type", "kit_type"]
    level = 2

    submission_types_id = Column(INTEGER, ForeignKey("_submissiontype.id"),
                                 primary_key=True)  #: id of joined submission type
    kits_id = Column(INTEGER, ForeignKey("_kittype.id"), primary_key=True)  #: id of joined kit
    mutable_cost_column = Column(
        FLOAT(2))  #: dollar amount per 96 well plate that can change with number of columns (reagents, tips, etc)
    mutable_cost_sample = Column(
        FLOAT(2))  #: dollar amount that can change with number of samples (reagents, tips, etc)
    constant_cost = Column(FLOAT(2))  #: dollar amount per plate that will remain constant (plates, man hours, etc)

    kit_type = relationship(KitType, back_populates="kit_submissiontype_associations")  #: joined kittype

    # reference to the "SubmissionType" object
    submission_type = relationship(SubmissionType,
                                   back_populates="submissiontype_kit_associations")  #: joined submission type

    def __init__(self, kit_type=None, submission_type=None,
                 mutable_cost_column: int = 0.00, mutable_cost_sample: int = 0.00, constant_cost: int = 0.00):
        self.kit_type = kit_type
        self.submission_type = submission_type
        self.mutable_cost_column = mutable_cost_column
        self.mutable_cost_sample = mutable_cost_sample
        self.constant_cost = constant_cost

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object
        """
        try:
            submission_type_name = self.submission_type.name
        except AttributeError:
            submission_type_name = "None"
        try:
            kit_type_name = self.kit_type.name
        except AttributeError:
            kit_type_name = "None"
        return f"<SubmissionTypeKitTypeAssociation({submission_type_name}&{kit_type_name})>"

    @hybrid_property
    def kittype(self):
        return self.kit_type

    @kittype.setter
    def kittype(self, value):
        self.kit_type = value

    @hybrid_property
    def submissiontype(self):
        return self.submission_type

    @submissiontype.setter
    def submissiontype(self, value):
        self.submission_type = value

    @property
    def name(self):
        try:
            return f"{self.submission_type.name} -> {self.kit_type.name}"
        except AttributeError:
            return "Blank SubmissionTypeKitTypeAssociation"

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[SubmissionTypeKitTypeAssociation, bool]:
        new = False
        disallowed = ['expiry']
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k not in disallowed}
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            setattr(instance, k, v)
        logger.info(f"Instance from SubmissionTypeKitTypeAssociation query or create: {instance}")
        return instance, new

    @classmethod
    @setup_lookup
    def query(cls,
              submissiontype: SubmissionType | str | int | None = None,
              kittype: KitType | str | int | None = None,
              limit: int = 0,
              **kwargs
              ) -> SubmissionTypeKitTypeAssociation | List[SubmissionTypeKitTypeAssociation]:
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
        match submissiontype:
            case SubmissionType():
                query = query.filter(cls.submission_type == submissiontype)
            case str():
                query = query.join(SubmissionType).filter(SubmissionType.name == submissiontype)
            case int():
                query = query.join(SubmissionType).filter(SubmissionType.id == submissiontype)
        match kittype:
            case KitType():
                query = query.filter(cls.kit_type == kittype)
            case str():
                query = query.join(KitType).filter(KitType.name == kittype)
            case int():
                query = query.join(KitType).filter(KitType.id == kittype)
        if kittype is not None and submissiontype is not None:
            limit = 1
        # limit = query.count()
        return cls.execute_query(query=query, limit=limit)

    # def to_export_dict(self):
    #     """
    #     Creates a dictionary of relevant values in this object.
    #
    #     Returns:
    #         dict: dictionary of Association and related kittype
    #     """
    #     exclude = ['_sa_instance_state', 'submission_types_id', 'kits_id', 'submission_type', 'kit_type']
    #     base_dict = {k: v for k, v in self.__dict__.items() if k not in exclude}
    #     base_dict['kit_type'] = self.kit_type.to_export_dict(submission_type=self.submission_type)
    #     return base_dict

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
    omni_sort = ["submission_type", "kit_type", "reagent_role", "required", "uses"]
    omni_inheritable = ["submission_type", "kit_type"]

    reagent_roles_id = Column(INTEGER, ForeignKey("_reagentrole.id"),
                              primary_key=True)  #: id of associated reagent type
    kits_id = Column(INTEGER, ForeignKey("_kittype.id"), primary_key=True)  #: id of associated reagent type
    submission_type_id = Column(INTEGER, ForeignKey("_submissiontype.id"), primary_key=True)
    uses = Column(JSON)  #: map to location on excel sheets of different submission types
    required = Column(INTEGER)  #: whether the reagent type is required for the kit (Boolean 1 or 0)
    last_used = Column(String(32))  #: last used lot number of this type of reagent

    kit_type = relationship(KitType,
                            back_populates="kit_reagentrole_associations")  #: relationship to associated KitType

    # NOTE: reference to the "ReagentType" object
    reagent_role = relationship(ReagentRole,
                                back_populates="reagentrole_kit_associations")  #: relationship to associated ReagentType

    # NOTE: reference to the "SubmissionType" object
    submission_type = relationship(SubmissionType,
                                   back_populates="submissiontype_kit_rt_associations")  #: relationship to associated SubmissionType

    def __init__(self, kit_type=None, reagent_role=None, uses=None, required=1):
        self.kit_type = kit_type
        self.reagent_role = reagent_role
        self.uses = uses
        self.required = required

    def __repr__(self) -> str:
        return f"<KitTypeReagentRoleAssociation({self.kit_type} & {self.reagent_role})>"

    @property
    def name(self):
        try:
            return f"{self.kit_type.name} -> {self.reagent_role.name}"
        except AttributeError:
            return "Blank KitTypeReagentRole"

    @hybrid_property
    def submissiontype(self):
        return self.submission_type

    @submissiontype.setter
    def submissiontype(self, value):
        self.submission_type = value

    @hybrid_property
    def kittype(self):
        return self.kit_type

    @kittype.setter
    def kittype(self, value):
        self.kit_type = value

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
                case "kittype" | "kit_type":
                    k = "kit_type"
                    if isinstance(v, str):
                        v = KitType.query(name=v)
                    else:
                        v = v.instance_object
                case "submissiontype" | "submission_type":
                    k = "submission_type"
                    if isinstance(v, str):
                        v = SubmissionType.query(name=v)
                    else:
                        v = v.instance_object
                case "reagentrole" | "reagent_role":
                    k = "reagent_role"
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
              submissiontype: SubmissionType | str | None = None,
              limit: int = 0,
              **kwargs
              ) -> KitTypeReagentRoleAssociation | List[KitTypeReagentRoleAssociation]:
        """
        Lookup junction of ReagentType and KitType

        Args:
            kit_type (models.KitType | str | None): KitType of interest.
            reagent_role (models.ReagentType | str | None): ReagentType of interest.
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
        match submissiontype:
            case SubmissionType():
                query = query.filter(cls.submission_type == submissiontype)
            case str():
                query = query.join(SubmissionType).filter(SubmissionType.name == submissiontype)
            case _:
                pass
        pass
        if kittype is not None and reagentrole is not None:
            limit = 1
        return cls.execute_query(query=query, limit=limit)

    # def to_export_dict(self) -> dict:
    #     """
    #     Creates a dictionary of relevant values in this object.
    #
    #     Returns:
    #         dict: dictionary of Association and related reagent role
    #     """
    #     base_dict = dict(required=self.required)
    #     for k, v in self.reagent_role.to_export_dict().items():
    #         base_dict[k] = v
    #     return base_dict

    def get_all_relevant_reagents(self) -> Generator[Reagent, None, None]:
        """
        Creates a generator that will resolve in to a list filling the role associated with this object.

        Returns:
            Generator: Generates of reagents.
        """
        reagents = self.reagent_role.instances
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
            eol_ext = self.reagent_role.eol_ext
        except AttributeError:
            eol_ext = timedelta(days=0)
        if expand:
            try:
                submission_type = self.submission_type.to_omni()
            except AttributeError:
                submission_type = ""
            try:
                kit_type = self.kit_type.to_omni()
            except AttributeError:
                kit_type = ""
            try:
                reagent_role = self.reagent_role.to_omni()
            except AttributeError:
                reagent_role = ""
        else:
            submission_type = self.submission_type.name
            kit_type = self.kit_type.name
            reagent_role = self.reagent_role.name
        return OmniKitTypeReagentRoleAssociation(
            instance_object=self,
            reagent_role=reagent_role,
            eol_ext=eol_ext,
            required=self.required,
            submission_type=submission_type,
            kit_type=kit_type,
            uses=self.uses
        )


class SubmissionReagentAssociation(BaseClass):
    """
    table containing submission/reagent associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    skip_on_edit = True

    reagent_id = Column(INTEGER, ForeignKey("_reagent.id"), primary_key=True)  #: id of associated reagent
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"), primary_key=True)  #: id of associated submission
    comments = Column(String(1024))  #: Comments about reagents

    submission = relationship("BasicSubmission",
                              back_populates="submission_reagent_associations")  #: associated submission

    reagent = relationship(Reagent, back_populates="reagent_submission_associations")  #: associated reagent

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this SubmissionReagentAssociation
        """
        try:
            return f"<SubmissionReagentAssociation({self.submission.rsl_plate_num} & {self.reagent.lot})>"
        except AttributeError:
            logger.error(f"Reagent {self.reagent.lot} submission association {self.reagent_id} has no submissions!")
            return f"<SubmissionReagentAssociation(Unknown Submission & {self.reagent.lot})>"

    def __init__(self, reagent=None, submission=None):
        if isinstance(reagent, list):
            logger.warning(f"Got list for reagent. Likely no lot was provided. Using {reagent[0]}")
            reagent = reagent[0]
        self.reagent = reagent
        self.submission = submission
        self.comments = ""

    @classmethod
    @setup_lookup
    def query(cls,
              submission: "BasicSubmission" | str | int | None = None,
              reagent: Reagent | str | None = None,
              limit: int = 0) -> SubmissionReagentAssociation | List[SubmissionReagentAssociation]:
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
            case Reagent() | str():
                if isinstance(reagent, str):
                    reagent = Reagent.query(lot=reagent)
                query = query.filter(cls.reagent == reagent)
            case _:
                pass
        match submission:
            case BasicSubmission() | str():
                if isinstance(submission, str):
                    submission = BasicSubmission.query(rsl_plate_num=submission)
                query = query.filter(cls.submission == submission)
            case int():
                submission = BasicSubmission.query(id=submission)
                query = query.join(BasicSubmission).filter(BasicSubmission.id == submission)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def to_sub_dict(self, extraction_kit) -> dict:
        """
        Converts this SubmissionReagentAssociation (and associated Reagent) to dict

        Args:
            extraction_kit (_type_): Extraction kit of interest

        Returns:
            dict: This SubmissionReagentAssociation as dict
        """
        output = self.reagent.to_sub_dict(extraction_kit)
        output['comments'] = self.comments
        return output

    def to_pydantic(self, extraction_kit: KitType):
        from backend.validators import PydReagent
        return PydReagent(**self.to_sub_dict(extraction_kit=extraction_kit))


class Equipment(BaseClass, LogMixin):
    """
    A concrete instance of equipment
    """

    id = Column(INTEGER, primary_key=True)  #: id, primary key
    name = Column(String(64))  #: equipment name
    nickname = Column(String(64))  #: equipment nickname
    asset_number = Column(String(16))  #: Given asset number (corpo nickname if you will)
    roles = relationship("EquipmentRole", back_populates="instances",
                         secondary=equipmentroles_equipment)  #: relation to EquipmentRoles
    processes = relationship("Process", back_populates="equipment",
                             secondary=equipment_processes)  #: relation to Processes
    tips = relationship("Tips", back_populates="equipment",
                        secondary=equipment_tips)  #: relation to Processes
    equipment_submission_associations = relationship(
        "SubmissionEquipmentAssociation",
        back_populates="equipment",
        cascade="all, delete-orphan",
    )  #: Association with BasicSubmission

    submissions = association_proxy("equipment_submission_associations",
                                    "submission")  #: proxy to equipment_submission_associations.submission

    def to_dict(self, processes: bool = False) -> dict:
        """
        This Equipment as a dictionary

        Args:
            processes (bool, optional): Whether to include processes. Defaults to False.

        Returns:
            dict: Dictionary representation of this equipment
        """
        if not processes:
            return {k: v for k, v in self.__dict__.items() if k != 'processes'}
        else:
            return {k: v for k, v in self.__dict__.items()}

    def get_processes(self, submission_type: str | SubmissionType | None = None,
                      extraction_kit: str | KitType | None = None,
                      equipment_role: str | EquipmentRole | None = None) -> Generator[Process, None, None]:
        """
        Get all processes associated with this Equipment for a given SubmissionType

        Args:
            submission_type (SubmissionType): SubmissionType of interest
            extraction_kit (str | KitType | None, optional): KitType to filter by. Defaults to None.

        Returns:
            List[Process]: List of process names
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if isinstance(extraction_kit, str):
            extraction_kit = KitType.query(name=extraction_kit)
        for process in self.processes:
            if submission_type not in process.submission_types:
                continue
            if extraction_kit and extraction_kit not in process.kit_types:
                continue
            if equipment_role and equipment_role not in process.equipment_roles:
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

    def to_pydantic(self, submission_type: SubmissionType, extraction_kit: str | KitType | None = None,
                    role: str = None) -> "PydEquipment":
        """
        Creates PydEquipment of this Equipment

        Args:
            submission_type (SubmissionType): Relevant SubmissionType
            extraction_kit (str | KitType | None, optional): Relevant KitType. Defaults to None.

        Returns:
            PydEquipment: pydantic equipment object
        """
        from backend.validators.pydant import PydEquipment
        processes = self.get_processes(submission_type=submission_type, extraction_kit=extraction_kit,
                                       equipment_role=role)
        return PydEquipment(processes=processes, role=role,
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
    def assign_equipment(cls, equipment_role: EquipmentRole | str) -> List[Equipment]:
        """
        Creates a list of equipment from user input to be used in Submission Type creation

        Args:
            equipment_role (EquipmentRole): Equipment role to be added to.

        Returns:
            List[Equipment]: User selected equipment.
        """
        if isinstance(equipment_role, str):
            equipment_role = EquipmentRole.query(name=equipment_role)
        equipment = cls.query()
        options = "\n".join([f"{ii}. {item.name}" for ii, item in enumerate(equipment)])
        choices = input(f"Enter equipment numbers to add to {equipment_role.name} (space separated):\n{options}\n\n")
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
            full_data (bool, optional): Whether to include submissions in data for details. Defaults to False.

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
            subs = [dict(plate=item.submission.rsl_plate_num, process=item.process.name, sub_date=item.submission.submitted_date)
                                     if item.process else dict(plate=item.submission.rsl_plate_num, process="NA")
                                     for item in self.equipment_submission_associations]
            output['submissions'] = sorted(subs, key=itemgetter("sub_date"), reverse=True)
            output['excluded'] = ['missing', 'submissions', 'excluded', 'editable']
        return output

    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template {e}")
            template = env.get_template("equipment_details.html")
        return template


class EquipmentRole(BaseClass):
    """
    Abstract roles for equipment
    """

    id = Column(INTEGER, primary_key=True)  #: Role id, primary key
    name = Column(String(32))  #: Common name
    instances = relationship("Equipment", back_populates="roles",
                             secondary=equipmentroles_equipment)  #: Concrete instances (Equipment) of role
    processes = relationship("Process", back_populates='equipment_roles',
                             secondary=equipmentroles_processes)  #: Associated Processes

    equipmentrole_submissiontype_associations = relationship(
        "SubmissionTypeEquipmentRoleAssociation",
        back_populates="equipment_role",
        cascade="all, delete-orphan",
    )  #: relation to SubmissionTypes

    submission_types = association_proxy("equipmentrole_submissiontype_associations",
                                         "submission_type")  #: proxy to equipmentrole_submissiontype_associations.submission_type

    def to_dict(self) -> dict:
        """
        This EquipmentRole as a dictionary

        Returns:
            dict: This EquipmentRole dict
        """
        return {key: value for key, value in self.__dict__.items() if key != "processes"}

    def to_pydantic(self, submission_type: SubmissionType,
                    extraction_kit: str | KitType | None = None) -> "PydEquipmentRole":
        """
        Creates a PydEquipmentRole of this EquipmentRole

        Args:
            submission_type (SubmissionType): SubmissionType of interest
            extraction_kit (str | KitType | None, optional): KitType of interest. Defaults to None.

        Returns:
            PydEquipmentRole: This EquipmentRole as PydEquipmentRole
        """
        from backend.validators.pydant import PydEquipmentRole
        equipment = [item.to_pydantic(submission_type=submission_type, extraction_kit=extraction_kit) for item in
                     self.instances]
        pyd_dict = self.to_dict()
        pyd_dict['processes'] = self.get_processes(submission_type=submission_type, extraction_kit=extraction_kit)
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
              ) -> EquipmentRole | List[
        EquipmentRole]:
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

    def get_processes(self, submission_type: str | SubmissionType | None,
                      extraction_kit: str | KitType | None = None) -> Generator[Process, None, None]:
        """
        Get processes used by this EquipmentRole

        Args:
            submission_type (str | SubmissionType | None): SubmissionType of interest
            extraction_kit (str | KitType | None, optional): KitType of interest. Defaults to None.

        Returns:
            List[Process]: List of processes
        """
        if isinstance(submission_type, str):
            submission_type = SubmissionType.query(name=submission_type)
        if isinstance(extraction_kit, str):
            extraction_kit = KitType.query(name=extraction_kit)
        for process in self.processes:
            if submission_type and submission_type not in process.submission_types:
                continue
            if extraction_kit and extraction_kit not in process.kit_types:
                continue
            yield process.name

    def to_omni(self, expand: bool = False) -> "OmniEquipmentRole":
        from backend.validators.omni_gui_objects import OmniEquipmentRole
        return OmniEquipmentRole(instance_object=self, name=self.name)


class SubmissionEquipmentAssociation(BaseClass):
    """
    Abstract association between BasicSubmission and Equipment
    """

    equipment_id = Column(INTEGER, ForeignKey("_equipment.id"), primary_key=True)  #: id of associated equipment
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"), primary_key=True)  #: id of associated submission
    role = Column(String(64), primary_key=True)  #: name of the role the equipment fills
    process_id = Column(INTEGER, ForeignKey("_process.id", ondelete="SET NULL",
                                            name="SEA_Process_id"))  #: Foreign key of process id
    start_time = Column(TIMESTAMP)  #: start time of equipment use
    end_time = Column(TIMESTAMP)  #: end time of equipment use
    comments = Column(String(1024))  #: comments about equipment

    submission = relationship("BasicSubmission",
                              back_populates="submission_equipment_associations")  #: associated submission

    equipment = relationship(Equipment, back_populates="equipment_submission_associations")  #: associated equipment

    def __repr__(self) -> str:
        return f"<SubmissionEquipmentAssociation({self.submission.rsl_plate_num} & {self.equipment.name})>"

    def __init__(self, submission, equipment, role: str = "None"):
        self.submission = submission
        self.equipment = equipment
        self.role = role

    @property
    def process(self):
        return Process.query(id=self.process_id)

    def to_sub_dict(self) -> dict:
        """
        This SubmissionEquipmentAssociation as a dictionary

        Returns:
            dict: This SubmissionEquipmentAssociation as a dictionary
        """
        try:
            process = self.process.name
        except AttributeError:
            process = "No process found"
        output = dict(name=self.equipment.name, asset_number=self.equipment.asset_number, comment=self.comments,
                      processes=[process], role=self.role, nickname=self.equipment.nickname)
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
    def query(cls, equipment_id: int | None = None, submission_id: int | None = None, role: str | None = None,
              limit: int = 0, **kwargs) \
            -> Any | List[Any]:
        query: Query = cls.__database_session__.query(cls)
        query = query.filter(cls.equipment_id == equipment_id)
        query = query.filter(cls.submission_id == submission_id)
        if role is not None:
            query = query.filter(cls.role == role)
        return cls.execute_query(query=query, limit=limit, **kwargs)


class SubmissionTypeEquipmentRoleAssociation(BaseClass):
    """
    Abstract association between SubmissionType and EquipmentRole
    """
    equipmentrole_id = Column(INTEGER, ForeignKey("_equipmentrole.id"), primary_key=True)  #: id of associated equipment
    submissiontype_id = Column(INTEGER, ForeignKey("_submissiontype.id"),
                               primary_key=True)  #: id of associated submission
    uses = Column(JSON)  #: locations of equipment on the submission type excel sheet.
    static = Column(INTEGER,
                    default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?

    submission_type = relationship(SubmissionType,
                                   back_populates="submissiontype_equipmentrole_associations")  #: associated submission

    equipment_role = relationship(EquipmentRole,
                                  back_populates="equipmentrole_submissiontype_associations")  #: associated equipment

    @hybrid_property
    def submissiontype(self):
        return self.submission_type

    @hybrid_property
    def equipmentrole(self):
        return self.equipment_role

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
    submission_types = relationship("SubmissionType", back_populates='processes',
                                    secondary=submissiontypes_processes)  #: relation to SubmissionType
    equipment = relationship("Equipment", back_populates='processes',
                             secondary=equipment_processes)  #: relation to Equipment
    equipment_roles = relationship("EquipmentRole", back_populates='processes',
                                   secondary=equipmentroles_processes)  #: relation to EquipmentRoles
    submissions = relationship("SubmissionEquipmentAssociation",
                               backref='process')  #: relation to SubmissionEquipmentAssociation
    kit_types = relationship("KitType", back_populates='processes',
                             secondary=kittypes_processes)  #: relation to KitType
    tip_roles = relationship("TipRole", back_populates='processes',
                             secondary=process_tiprole)  #: relation to KitType

    def set_attribute(self, key, value):
        match key:
            case "name":
                self.name = value
            case _:
                field = getattr(self, key)
                if value not in field:
                    field.append(value)

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[Process, bool]:
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
              submissiontype: str | SubmissionType | None = None,
              kittype: str | KitType | None = None,
              equipmentrole: str | KitType | None = None,
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
        match submissiontype:
            case str():
                submissiontype = SubmissionType.query(name=submissiontype)
                query = query.filter(cls.submission_types.contains(submissiontype))
            case SubmissionType():
                query = query.filter(cls.submission_types.contains(submissiontype))
            case _:
                pass
        match kittype:
            case str():
                kittype = KitType.query(name=kittype)
                query = query.filter(cls.kit_types.contains(kittype))
            case KitType():
                query = query.filter(cls.kit_types.contains(kittype))
            case _:
                pass
        match equipmentrole:
            case str():
                equipmentrole = EquipmentRole.query(name=equipmentrole)
                query = query.filter(cls.equipment_roles.contains(equipmentrole))
            case EquipmentRole():
                query = query.filter(cls.equipment_roles.contains(equipmentrole))
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
            submission_types = [item.to_omni() for item in self.submission_types]
            equipment_roles = [item.to_omni() for item in self.equipment_roles]
            tip_roles = [item.to_omni() for item in self.tip_roles]
        else:
            submission_types = [item.name for item in self.submission_types]
            equipment_roles = [item.name for item in self.equipment_roles]
            tip_roles = [item.name for item in self.tip_roles]
        return OmniProcess(
            instance_object=self,
            name=self.name,
            submission_types=submission_types,
            equipment_roles=equipment_roles,
            tip_roles=tip_roles
        )

    def to_sub_dict(self, full_data: bool = False, **kwargs) -> dict:
        """
        dictionary containing values necessary for gui

        Args:
            full_data (bool, optional): Whether to include submissions in data for details. Defaults to False.

        Returns:
            dict: representation of the equipment's attributes
        """
        output = dict(
            name=self.name,
        )
        if full_data:
            subs = [dict(plate=sub.submission.rsl_plate_num, equipment=sub.equipment.name, sub_date=sub.submission.submitted_date) for sub in self.submissions]
            output['submissions'] = sorted(subs, key=itemgetter("sub_date"), reverse=True)
            output['excluded'] = ['missing', 'submissions', 'excluded', 'editable']
        return output

    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template {e}")
            template = env.get_template("process_details.html")
        return template


class TipRole(BaseClass):
    """
    An abstract role that a tip fills during a process
    """
    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64))  #: name of reagent type
    instances = relationship("Tips", back_populates="role",
                             secondary=tiproles_tips)  #: concrete instances of this reagent type
    processes = relationship("Process", back_populates="tip_roles", secondary=process_tiprole)

    tiprole_submissiontype_associations = relationship(
        "SubmissionTypeTipRoleAssociation",
        back_populates="tip_role",
        cascade="all, delete-orphan"
    )  #: associated submission

    submission_types = association_proxy("tiprole_submissiontype_associations", "submission_type")

    @hybrid_property
    def tips(self):
        return self.instances

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[TipRole, bool]:
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
    role = relationship("TipRole", back_populates="instances",
                        secondary=tiproles_tips)  #: joined parent reagent type
    role_id = Column(INTEGER, ForeignKey("_tiprole.id", ondelete='SET NULL',
                                         name="fk_tip_role_id"))  #: id of parent reagent type
    name = Column(String(64))  #: tip common name
    lot = Column(String(64))  #: lot number of tips
    equipment = relationship("Equipment", back_populates="tips",
                             secondary=equipment_tips)  #: associated submission
    tips_submission_associations = relationship(
        "SubmissionTipsAssociation",
        back_populates="tips",
        cascade="all, delete-orphan"
    )  #: associated submission

    submissions = association_proxy("tips_submission_associations", 'submission')

    @hybrid_property
    def tiprole(self):
        return self.role

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[Tips, bool]:
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
            full_data (bool, optional): Whether to include submissions in data for details. Defaults to False.

        Returns:
            dict: representation of the equipment's attributes
        """
        output = dict(
            name=self.name,
            lot=self.lot,
        )
        if full_data:
            subs = [dict(plate=item.submission.rsl_plate_num, role=item.role_name, sub_date=item.submission.submitted_date)
                                     for item in self.tips_submission_associations]
            output['submissions'] = sorted(subs, key=itemgetter("sub_date"), reverse=True)
            output['excluded'] = ['missing', 'submissions', 'excluded', 'editable']
        return output

    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template {e}")
            template = env.get_template("tips_details.html")
        return template


class SubmissionTypeTipRoleAssociation(BaseClass):
    """
   Abstract association between SubmissionType and TipRole
   """
    tiprole_id = Column(INTEGER, ForeignKey("_tiprole.id"), primary_key=True)  #: id of associated equipment
    submissiontype_id = Column(INTEGER, ForeignKey("_submissiontype.id"),
                               primary_key=True)  #: id of associated submission
    uses = Column(JSON)  #: locations of equipment on the submission type excel sheet.
    static = Column(INTEGER,
                    default=1)  #: if 1 this piece of equipment will always be used, otherwise it will need to be selected from list?
    submission_type = relationship(SubmissionType,
                                   back_populates="submissiontype_tiprole_associations")  #: associated submission
    tip_role = relationship(TipRole,
                            back_populates="tiprole_submissiontype_associations")  #: associated equipment

    @hybrid_property
    def submissiontype(self):
        return self.submission_type

    @hybrid_property
    def tiprole(self):
        return self.tip_role

    @check_authorization
    def save(self):
        super().save()

    def to_omni(self):
        pass


class SubmissionTipsAssociation(BaseClass):
    """
    Association between a concrete submission instance and concrete tips
    """
    tip_id = Column(INTEGER, ForeignKey("_tips.id"), primary_key=True)  #: id of associated equipment
    submission_id = Column(INTEGER, ForeignKey("_basicsubmission.id"), primary_key=True)  #: id of associated submission
    submission = relationship("BasicSubmission",
                              back_populates="submission_tips_associations")  #: associated submission
    tips = relationship(Tips,
                        back_populates="tips_submission_associations")  #: associated equipment
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
    def query(cls, tip_id: int, role: str, submission_id: int | None = None, limit: int = 0, **kwargs) \
            -> Any | List[Any]:
        query: Query = cls.__database_session__.query(cls)
        query = query.filter(cls.tip_id == tip_id)
        if submission_id is not None:
            query = query.filter(cls.submission_id == submission_id)
        query = query.filter(cls.role_name == role)
        return cls.execute_query(query=query, limit=limit, **kwargs)

    @classmethod
    def query_or_create(cls, tips, submission, role: str, **kwargs):
        kwargs['limit'] = 1
        instance = cls.query(tip_id=tips.id, role=role, submission_id=submission.id, **kwargs)
        if instance is None:
            instance = SubmissionTipsAssociation(submission=submission, tips=tips, role_name=role)
        return instance

    def to_pydantic(self):
        from backend.validators import PydTips
        return PydTips(name=self.tips.name, lot=self.tips.lot, role=self.role_name)
