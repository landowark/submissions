"""
All kit and reagent related models
"""
from __future__ import annotations

import datetime
import json
from pprint import pformat
import yaml
from sqlalchemy import Column, String, TIMESTAMP, JSON, INTEGER, ForeignKey, Interval, Table, FLOAT, BLOB
from sqlalchemy.orm import relationship, validates, Query
from sqlalchemy.ext.associationproxy import association_proxy
from datetime import date
import logging, re
from tools import check_authorization, setup_lookup, Report, Result, check_regex_match, yaml_regex_creator
from typing import List, Literal, Generator, Any
from pandas import ExcelFile
from pathlib import Path
from . import Base, BaseClass, Organization
from io import BytesIO

logger = logging.getLogger(f'submissions.{__name__}')

# logger.debug("Table for ReagentType/Reagent relations")
reagentroles_reagents = Table(
    "_reagentroles_reagents",
    Base.metadata,
    Column("reagent_id", INTEGER, ForeignKey("_reagent.id")),
    Column("reagentrole_id", INTEGER, ForeignKey("_reagentrole.id")),
    extend_existing=True
)

# logger.debug("Table for EquipmentRole/Equipment relations")
equipmentroles_equipment = Table(
    "_equipmentroles_equipment",
    Base.metadata,
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_equipmentrole.id")),
    extend_existing=True
)

# logger.debug("Table for Equipment/Process relations")
equipment_processes = Table(
    "_equipment_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    extend_existing=True
)

# logger.debug("Table for EquipmentRole/Process relations")
equipmentroles_processes = Table(
    "_equipmentroles_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentrole_id", INTEGER, ForeignKey("_equipmentrole.id")),
    extend_existing=True
)

# logger.debug("Table for SubmissionType/Process relations")
submissiontypes_processes = Table(
    "_submissiontypes_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("equipmentroles_id", INTEGER, ForeignKey("_submissiontype.id")),
    extend_existing=True
)

# logger.debug("Table for KitType/Process relations")
kittypes_processes = Table(
    "_kittypes_processes",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("kit_id", INTEGER, ForeignKey("_kittype.id")),
    extend_existing=True
)

# logger.debug("Table for TipRole/Tips relations")
tiproles_tips = Table(
    "_tiproles_tips",
    Base.metadata,
    Column("tiprole_id", INTEGER, ForeignKey("_tiprole.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)

# logger.debug("Table for Process/TipRole relations")
process_tiprole = Table(
    "_process_tiprole",
    Base.metadata,
    Column("process_id", INTEGER, ForeignKey("_process.id")),
    Column("tiprole_id", INTEGER, ForeignKey("_tiprole.id")),
    extend_existing=True
)

# logger.debug("Table for Equipment/Tips relations")
equipment_tips = Table(
    "_equipment_tips",
    Base.metadata,
    Column("equipment_id", INTEGER, ForeignKey("_equipment.id")),
    Column("tips_id", INTEGER, ForeignKey("_tips.id")),
    extend_existing=True
)


class KitType(BaseClass):
    """
    Base of kits used in submission processing
    """

    id = Column(INTEGER, primary_key=True)  #: primary key
    name = Column(String(64), unique=True)  #: name of kit
    submissions = relationship("BasicSubmission", back_populates="extraction_kit")  #: submissions this kit was used for
    processes = relationship("Process", back_populates="kit_types",
                             secondary=kittypes_processes)  #: equipment processes used by this kit

    kit_reagentrole_associations = relationship(
        "KitTypeReagentRoleAssociation",
        back_populates="kit_type",
        cascade="all, delete-orphan",
    )

    # creator function: https://stackoverflow.com/questions/11091491/keyerror-when-adding-objects-to-sqlalchemy-association-object/11116291#11116291
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

    def __repr__(self) -> str:
        """
        Returns:
            str: A representation of the object.
        """
        return f"<KitType({self.name})>"

    def get_reagents(self, required: bool = False, submission_type: str | SubmissionType | None = None) -> Generator[
        ReagentRole, None, None]:
        """
        Return ReagentTypes linked to kit through KitTypeReagentTypeAssociation.

        Args:
            required (bool, optional): If true only return required types. Defaults to False.
            submission_type (str | Submissiontype | None, optional): Submission type to narrow results. Defaults to None.

        Returns:
            List[ReagentRole]: List of reagents linked to this kit.
        """
        match submission_type:
            case SubmissionType():
                # logger.debug(f"Getting reagents by SubmissionType {submission_type}")
                relevant_associations = [item for item in self.kit_reagentrole_associations if
                                         item.submission_type == submission_type]
            case str():
                # logger.debug(f"Getting reagents by str {submission_type}")
                relevant_associations = [item for item in self.kit_reagentrole_associations if
                                         item.submission_type.name == submission_type]
            case _:
                # logger.debug(f"Getting reagents")
                relevant_associations = [item for item in self.kit_reagentrole_associations]
        if required:
            # logger.debug(f"Filtering by required.")
            return (item.reagent_role for item in relevant_associations if item.required == 1)
        else:
            return (item.reagent_role for item in relevant_associations)

    # TODO: Move to BasicSubmission?
    def construct_xl_map_for_use(self, submission_type: str | SubmissionType) -> Generator[(str, str)]:
        """
        Creates map of locations in Excel workbook for a SubmissionType

        Args:
            submission_type (str | SubmissionType): Submissiontype.name

        Returns:
            dict: Dictionary containing information locations.
        """
        # info_map = {}
        # NOTE: Account for submission_type variable type.
        match submission_type:
            case str():
                # logger.debug(f"Constructing xl map with str {submission_type}")
                assocs = [item for item in self.kit_reagentrole_associations if
                          item.submission_type.name == submission_type]
            case SubmissionType():
                # logger.debug(f"Constructing xl map with SubmissionType {submission_type}")
                assocs = [item for item in self.kit_reagentrole_associations if item.submission_type == submission_type]
            case _:
                raise ValueError(f"Wrong variable type: {type(submission_type)} used!")
        # logger.debug("Get all KitTypeReagentTypeAssociation for SubmissionType")
        for assoc in assocs:
            try:
                # logger.debug(f"Yielding: {assoc.reagent_role.name}, {assoc.uses}")
                yield assoc.reagent_role.name, assoc.uses
            except TypeError:
                continue

    @classmethod
    @setup_lookup
    def query(cls,
              name: str = None,
              used_for: str | SubmissionType | None = None,
              id: int | None = None,
              limit: int = 0
              ) -> KitType | List[KitType]:
        """
        Lookup a list of or single KitType.

        Args:
        name (str, optional): Name of desired kit (returns single instance). Defaults to None.
        used_for (str | Submissiontype | None, optional): Submission type the kit is used for. Defaults to None.
        id (int | None, optional): Kit id in the database. Defaults to None.
        limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
        models.KitType|List[models.KitType]: KitType(s) of interest.
        """
        query: Query = cls.__database_session__.query(cls)
        match used_for:
            case str():
                # logger.debug(f"Looking up kit type by used_for str: {used_for}")
                query = query.filter(cls.used_for.any(name=used_for))
            case SubmissionType():
                # logger.debug(f"Looking up kit type by used_for SubmissionType: {used_for}")
                query = query.filter(cls.used_for.contains(used_for))
            case _:
                pass
        match name:
            case str():
                # logger.debug(f"Looking up kit type by name str: {name}")
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match id:
            case int():
                # logger.debug(f"Looking up kit type by id int: {id}")
                query = query.filter(cls.id == id)
                limit = 1
            case str():
                # logger.debug(f"Looking up kit type by id str: {id}")
                query = query.filter(cls.id == int(id))
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @check_authorization
    def save(self):
        super().save()

    def to_export_dict(self, submission_type: SubmissionType):
        base_dict = dict(name=self.name)
        base_dict['reagent roles'] = []
        base_dict['equipment roles'] = []
        for k, v in self.construct_xl_map_for_use(submission_type=submission_type):
            # logger.debug(f"Value: {v}")
            try:
                assoc = next(item for item in self.kit_reagentrole_associations if item.reagent_role.name == k)
            except StopIteration as e:
                continue
            for kk, vv in assoc.to_export_dict().items():
                v[kk] = vv
            base_dict['reagent roles'].append(v)
        for k, v in submission_type.construct_equipment_map():
            try:
                assoc = next(item for item in submission_type.submissiontype_equipmentrole_associations if
                             item.equipment_role.name == k)
            except StopIteration:
                continue
            for kk, vv in assoc.to_export_dict(kit_type=self).items():
                # logger.debug(f"{kk}:{vv}")
                v[kk] = vv
            base_dict['equipment roles'].append(v)
        # logger.debug(f"KT returning {base_dict}")
        return base_dict


class ReagentRole(BaseClass):
    """
    Base of reagent type abstract
    """

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

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of object
        """
        return f"<ReagentRole({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              kit_type: KitType | str | None = None,
              reagent: Reagent | str | None = None,
              limit: int = 0,
              ) -> ReagentRole | List[ReagentRole]:
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
            ReagentRole|List[ReagentRole]: ReagentRole or list of ReagentRoles matching filter.
        """
        query: Query = cls.__database_session__.query(cls)
        if (kit_type is not None and reagent is None) or (reagent is not None and kit_type is None):
            raise ValueError("Cannot filter without both reagent and kit type.")
        elif kit_type is None and reagent is None:
            pass
        else:
            match kit_type:
                case str():
                    # logger.debug(f"Lookup ReagentType by kittype str {kit_type}")
                    kit_type = KitType.query(name=kit_type)
                case _:
                    pass
            match reagent:
                case str():
                    # logger.debug(f"Lookup ReagentType by reagent str {reagent}")
                    reagent = Reagent.query(lot_number=reagent)
                case _:
                    pass
            assert reagent.role
            # logger.debug(f"Looking up reagent type for {type(kit_type)} {kit_type} and {type(reagent)} {reagent}")
            # logger.debug(f"Kit reagent types: {kit_type.reagent_types}")
            result = list(set(kit_type.reagent_roles).intersection(reagent.role))
            # logger.debug(f"Result: {result}")
            try:
                return result[0]
            except IndexError:
                return None
        match name:
            case str():
                # logger.debug(f"Looking up reagent type by name str: {name}")
                query = query.filter(cls.name == name)
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

    def to_export_dict(self):
        return dict(role=self.name, extension_of_life=self.eol_ext.days)

    @check_authorization
    def save(self):
        super().save()


class Reagent(BaseClass):
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
        if self.name is not None:
            return f"<Reagent({self.name}-{self.lot})>"
        else:
            return f"<Reagent({self.role.name}-{self.lot})>"

    def to_sub_dict(self, extraction_kit: KitType = None, full_data: bool = False) -> dict:
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
            try:
                reagent_role = list(set(self.role).intersection(extraction_kit.reagent_roles))[0]
            # NOTE: Most will be able to fall back to first ReagentType in itself because most will only have 1.
            except:
                reagent_role = self.role[0]
        else:
            reagent_role = self.role[0]
        try:
            rtype = reagent_role.name.replace("_", " ")
        except AttributeError:
            rtype = "Unknown"
        # logger.debug(f"Role for {self.name}: {rtype}")
        # NOTE: Calculate expiry with EOL from ReagentType
        try:
            place_holder = self.expiry + reagent_role.eol_ext
        except (TypeError, AttributeError) as e:
            place_holder = date.today()
            logger.error(f"We got a type error setting {self.lot} expiry: {e}. setting to today for testing")
        # NOTE: The notation for not having an expiry is 1970.1.1
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
            output['excluded'] = ['missing', 'submissions', 'excluded']
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
        # logger.debug(f"Attempting update of last used reagent type at intersection of ({self}), ({kit})")
        rt = ReagentRole.query(kit_type=kit, reagent=self, limit=1)
        if rt is not None:
            # logger.debug(f"got reagenttype {rt}")
            assoc = KitTypeReagentRoleAssociation.query(kit_type=kit, reagent_role=rt)
            if assoc is not None:
                if assoc.last_used != self.lot:
                    # logger.debug(f"Updating {assoc} last used to {self.lot}")
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
              reagent_role: str | ReagentRole | None = None,
              lot_number: str | None = None,
              name: str | None = None,
              limit: int = 0
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
        match reagent_role:
            case str():
                # logger.debug(f"Looking up reagents by reagent type str: {reagent_type}")
                query = query.join(cls.role).filter(ReagentRole.name == reagent_role)
            case ReagentRole():
                # logger.debug(f"Looking up reagents by reagent type ReagentType: {reagent_type}")
                query = query.filter(cls.role.contains(reagent_role))
            case _:
                pass
        match name:
            case str():
                # logger.debug(f"Looking up reagent by name str: {name}")
                # NOTE: Not limited due to multiple reagents having same name.
                query = query.filter(cls.name == name)
            case _:
                pass
        match lot_number:
            case str():
                # logger.debug(f"Looking up reagent by lot number str: {lot_number}")
                query = query.filter(cls.lot == lot_number)
                # NOTE: In this case limit number returned.
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)


class Discount(BaseClass):
    """
    Relationship table for client labs for certain kits.
    """

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
              kit_type: KitType | str | int | None = None,
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
                # logger.debug(f"Looking up discount with organization Organization: {organization}")
                query = query.filter(cls.client == Organization)
            case str():
                # logger.debug(f"Looking up discount with organization str: {organization}")
                query = query.join(Organization).filter(Organization.name == organization)
            case int():
                # logger.debug(f"Looking up discount with organization id: {organization}")
                query = query.join(Organization).filter(Organization.id == organization)
            case _:
                pass
        match kit_type:
            case KitType():
                # logger.debug(f"Looking up discount with kit type KitType: {kit_type}")
                query = query.filter(cls.kit == kit_type)
            case str():
                # logger.debug(f"Looking up discount with kit type str: {kit_type}")
                query = query.join(KitType).filter(KitType.name == kit_type)
            case int():
                # logger.debug(f"Looking up discount with kit type id: {kit_type}")
                query = query.join(KitType).filter(KitType.id == kit_type)
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
    info_map = Column(JSON)  #: Where basic information is found in the excel workbook corresponding to this type.
    defaults = Column(JSON)  #: Basic information about this submission type
    instances = relationship("BasicSubmission", backref="submission_type")  #: Concrete instances of this type.
    template_file = Column(BLOB)  #: Blank form for this type stored as binary.
    processes = relationship("Process", back_populates="submission_types",
                             secondary=submissiontypes_processes)  #: Relation to equipment processes used for this type.
    sample_map = Column(JSON)  #: Where sample information is found in the excel sheet corresponding to this type.

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
    )

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this object.
        """
        return f"<SubmissionType({self.name})>"

    def get_template_file_sheets(self) -> List[str]:
        """
        Gets names of sheet in the stored blank form.

        Returns:
            List[str]: List of sheet names
        """
        return ExcelFile(BytesIO(self.template_file), engine="openpyxl").sheet_names

    def set_template_file(self, filepath: Path | str):
        """

        Sets the binary store to an excel file.

        Args:
            filepath (Path | str): Path to the template file.

        Raises:
            ValueError: Raised if file is not excel file.
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
        logger.debug(f"Info map: {info}")
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

    def construct_sample_map(self) -> dict:
        """
        Returns sample map

        Returns:
            dict: sample location map
        """
        return self.sample_map

    def construct_equipment_map(self) -> Generator[str, dict]:
        """
        Constructs map of equipment to excel cells.

        Returns:
            dict: Map equipment locations in excel sheet
        """
        # logger.debug("Iterating through equipment roles")
        for item in self.submissiontype_equipmentrole_associations:
            emap = item.uses
            if emap is None:
                emap = {}
            yield item.equipment_role.name, emap

    def construct_tips_map(self) -> Generator[str, dict]:
        """
        Constructs map of tips to excel cells.

        Returns:
            dict: Tip locations in the excel sheet.
        """
        for item in self.submissiontype_tiprole_associations:
            tmap = item.uses
            if tmap is None:
                tmap = {}
            yield item.tip_role.name, tmap

    def get_equipment(self, extraction_kit: str | KitType | None = None) -> Generator['PydEquipmentRole', None, None]:
        """
        Returns PydEquipmentRole of all equipment associated with this SubmissionType

        Returns:
            List[PydEquipmentRole]: List of equipment roles
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
                # logger.debug(f"Getting processes for equipmentrole str {equipment_role}")
                relevant = [item.get_all_processes(kit) for item in self.submissiontype_equipmentrole_associations if
                            item.equipment_role.name == equipment_role]
            case EquipmentRole():
                # logger.debug(f"Getting processes for equipmentrole EquipmentRole {equipment_role}")
                relevant = [item.get_all_processes(kit) for item in self.submissiontype_equipmentrole_associations if
                            item.equipment_role == equipment_role]
            case _:
                raise TypeError(f"Type {type(equipment_role)} is not allowed")
        return list(set([item for items in relevant for item in items if item is not None]))

    def get_submission_class(self) -> "BasicSubmission":
        """
        Gets submission class associated with this submission type.

        Returns:
            BasicSubmission: Submission class
        """
        from .submissions import BasicSubmission
        return BasicSubmission.find_polymorphic_subclass(polymorphic_identity=self.name)

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              key: str | None = None,
              limit: int = 0
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
                # logger.debug(f"Looking up submission type by name str: {name}")
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match key:
            case str():
                # logger.debug(f"Looking up submission type by info-map key str: {key}")
                query = query.filter(cls.info_map.op('->')(key) is not None)
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def to_export_dict(self):
        base_dict = dict(name=self.name)
        base_dict['info'] = self.construct_info_map(mode='export')
        base_dict['defaults'] = self.defaults
        base_dict['samples'] = self.construct_sample_map()
        base_dict['kits'] = [item.to_export_dict() for item in self.submissiontype_kit_associations]
        return base_dict

    @check_authorization
    def save(self):
        """
        Adds this instances to the database and commits.
        """
        super().save()

    @classmethod
    @check_authorization
    def import_from_json(cls, filepath: Path | str):
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
        logger.debug(pformat(import_dict))
        submission_type = cls.query(name=import_dict['name'])
        if submission_type:
            return submission_type
        submission_type = cls()
        submission_type.name = import_dict['name']
        submission_type.info_map = import_dict['info']
        submission_type.sample_map = import_dict['samples']
        submission_type.defaults = import_dict['defaults']
        for kit in import_dict['kits']:
            new_kit = KitType.query(name=kit['kit_type']['name'])
            if not new_kit:
                new_kit = KitType(name=kit['kit_type']['name'])
            for role in kit['kit_type']['reagent roles']:
                new_role = ReagentRole.query(name=role['role'])
                if new_role:
                    check = input(f"Found existing role: {new_role.name}. Use this? [Y/n]: ")
                    if check.lower() == "n":
                        new_role = None
                    else:
                        pass
                if not new_role:
                    eol = datetime.timedelta(role['extension_of_life'])
                    new_role = ReagentRole(name=role['role'], eol_ext=eol)
                uses = dict(expiry=role['expiry'], lot=role['lot'], name=role['name'], sheet=role['sheet'])
                ktrr_assoc = KitTypeReagentRoleAssociation(kit_type=new_kit, reagent_role=new_role, uses=uses)
                ktrr_assoc.submission_type = submission_type
                ktrr_assoc.required = role['required']
            ktst_assoc = SubmissionTypeKitTypeAssociation(
                kit_type=new_kit,
                submission_type=submission_type,
                mutable_cost_sample=kit['mutable_cost_sample'],
                mutable_cost_column=kit['mutable_cost_column'],
                constant_cost=kit['constant_cost']
            )
            for role in kit['kit_type']['equipment roles']:
                new_role = EquipmentRole.query(name=role['role'])
                if new_role:
                    check = input(f"Found existing role: {new_role.name}. Use this? [Y/n]: ")
                    if check.lower() == "n":
                        new_role = None
                    else:
                        pass
                if not new_role:
                    new_role = EquipmentRole(name=role['role'])
                    for equipment in Equipment.assign_equipment(equipment_role=new_role):
                        new_role.instances.append(equipment)
                ster_assoc = SubmissionTypeEquipmentRoleAssociation(submission_type=submission_type,
                                                                    equipment_role=new_role)
                try:
                    uses = dict(name=role['name'], process=role['process'], sheet=role['sheet'], static=role['static'])
                except KeyError:
                    uses = None
                ster_assoc.uses = uses
                for process in role['processes']:
                    new_process = Process.query(name=process)
                    if not new_process:
                        new_process = Process(name=process)
                    new_process.submission_types.append(submission_type)
                    new_process.kit_types.append(new_kit)
                    new_process.equipment_roles.append(new_role)
            if 'orgs' in import_dict.keys():
                logger.info("Found Organizations to be imported.")
                Organization.import_from_yml(filepath=filepath)
            return submission_type


class SubmissionTypeKitTypeAssociation(BaseClass):
    """
    Abstract of relationship between kits and their submission type.
    """

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
        return f"<SubmissionTypeKitTypeAssociation({self.submission_type.name}&{self.kit_type.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
              submission_type: SubmissionType | str | int | None = None,
              kit_type: KitType | str | int | None = None,
              limit: int = 0
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
        match submission_type:
            case SubmissionType():
                # logger.debug(f"Looking up {cls.__name__} by SubmissionType {submission_type}")
                query = query.filter(cls.submission_type == submission_type)
            case str():
                # logger.debug(f"Looking up {cls.__name__} by name {submission_type}")
                query = query.join(SubmissionType).filter(SubmissionType.name == submission_type)
            case int():
                # logger.debug(f"Looking up {cls.__name__} by id {submission_type}")
                query = query.join(SubmissionType).filter(SubmissionType.id == submission_type)
        match kit_type:
            case KitType():
                # logger.debug(f"Looking up {cls.__name__} by KitType {kit_type}")
                query = query.filter(cls.kit_type == kit_type)
            case str():
                # logger.debug(f"Looking up {cls.__name__} by name {kit_type}")
                query = query.join(KitType).filter(KitType.name == kit_type)
            case int():
                # logger.debug(f"Looking up {cls.__name__} by id {kit_type}")
                query = query.join(KitType).filter(KitType.id == kit_type)
        limit = query.count()
        return cls.execute_query(query=query, limit=limit)

    def to_export_dict(self):
        """
        Creates a dictionary of relevant values in this object.

        Returns:
            dict: dictionary of Association and related kittype
        """
        exclude = ['_sa_instance_state', 'submission_types_id', 'kits_id', 'submission_type', 'kit_type']
        base_dict = {k: v for k, v in self.__dict__.items() if k not in exclude}
        base_dict['kit_type'] = self.kit_type.to_export_dict(submission_type=self.submission_type)
        # logger.debug(f"STKTA returning: {base_dict}")
        return base_dict


class KitTypeReagentRoleAssociation(BaseClass):
    """
    table containing reagenttype/kittype associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

    reagent_roles_id = Column(INTEGER, ForeignKey("_reagentrole.id"),
                              primary_key=True)  #: id of associated reagent type
    kits_id = Column(INTEGER, ForeignKey("_kittype.id"), primary_key=True)  #: id of associated reagent type
    submission_type_id = Column(INTEGER, ForeignKey("_submissiontype.id"), primary_key=True)
    uses = Column(JSON)  #: map to location on excel sheets of different submission types
    required = Column(INTEGER)  #: whether the reagent type is required for the kit (Boolean 1 or 0)
    last_used = Column(String(32))  #: last used lot number of this type of reagent

    kit_type = relationship(KitType,
                            back_populates="kit_reagentrole_associations")  #: relationship to associated KitType

    # reference to the "ReagentType" object
    reagent_role = relationship(ReagentRole,
                                back_populates="reagentrole_kit_associations")  #: relationship to associated ReagentType

    submission_type = relationship(SubmissionType,
                                   back_populates="submissiontype_kit_rt_associations")  #: relationship to associated SubmissionType

    def __init__(self, kit_type=None, reagent_role=None, uses=None, required=1):
        self.kit_type = kit_type
        self.reagent_role = reagent_role
        self.uses = uses
        self.required = required

    def __repr__(self) -> str:
        return f"<KitTypeReagentRoleAssociation({self.kit_type} & {self.reagent_role})>"

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
    @setup_lookup
    def query(cls,
              kit_type: KitType | str | None = None,
              reagent_role: ReagentRole | str | None = None,
              limit: int = 0
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
        match kit_type:
            case KitType():
                # logger.debug(f"Lookup KitTypeReagentTypeAssociation by kit_type KitType {kit_type}")
                query = query.filter(cls.kit_type == kit_type)
            case str():
                # logger.debug(f"Lookup KitTypeReagentTypeAssociation by kit_type str {kit_type}")
                query = query.join(KitType).filter(KitType.name == kit_type)
            case _:
                pass
        match reagent_role:
            case ReagentRole():
                # logger.debug(f"Lookup KitTypeReagentTypeAssociation by reagent_type ReagentType {reagent_type}")
                query = query.filter(cls.reagent_role == reagent_role)
            case str():
                # logger.debug(f"Lookup KitTypeReagentTypeAssociation by reagent_type ReagentType {reagent_type}")
                query = query.join(ReagentRole).filter(ReagentRole.name == reagent_role)
            case _:
                pass
        if kit_type is not None and reagent_role is not None:
            limit = 1
        return cls.execute_query(query=query, limit=limit)

    def to_export_dict(self) -> dict:
        """
        Creates a dictionary of relevant values in this object.

        Returns:
            dict: dictionary of Association and related reagent role
        """
        base_dict = {}
        base_dict['required'] = self.required
        for k, v in self.reagent_role.to_export_dict().items():
            base_dict[k] = v
        return base_dict

    def get_all_relevant_reagents(self, override:Reagent|None=None) -> Generator[Reagent, None, None]:
        """
        Creates a generator that will resolve in to a list filling the role associated with this object.

        Returns:
            Generator: Generates of reagents.
        """
        # logger.debug(f"Attempting lookup of reagents by type: {reagent.type}")
        reagents = self.reagent_role.instances
        try:
            regex = self.uses['exclude_regex']
        except KeyError:
            regex = "^$"
        relevant_reagents = [reagent for reagent in reagents if
                             not check_regex_match(pattern=regex, check=str(reagent.lot))]
        for rel_reagent in relevant_reagents:
            yield rel_reagent


class SubmissionReagentAssociation(BaseClass):
    """
    table containing submission/reagent associations
    DOC: https://docs.sqlalchemy.org/en/14/orm/extensions/associationproxy.html
    """

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
        return f"<{self.submission.rsl_plate_num} & {self.reagent.lot}>"

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
                # logger.debug(f"Lookup SubmissionReagentAssociation by reagent Reagent {reagent}")
                if isinstance(reagent, str):
                    reagent = Reagent.query(lot_number=reagent)
                query = query.filter(cls.reagent == reagent)
            case _:
                pass
        match submission:
            case BasicSubmission() | str():
                if isinstance(submission, str):
                    submission = BasicSubmission.query(rsl_plate_num=submission)
                # logger.debug(f"Lookup SubmissionReagentAssociation by submission BasicSubmission {submission}")
                query = query.filter(cls.submission == submission)
            case int():
                # logger.debug(f"Lookup SubmissionReagentAssociation by submission id {submission}")
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


class Equipment(BaseClass):
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

    def __repr__(self) -> str:
        """
        Returns:
            str: represenation of this Equipment
        """
        return f"<Equipment({self.name})>"

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

    def get_processes(self, submission_type: SubmissionType, extraction_kit: str | KitType | None = None) -> List[str]:
        """
        Get all processes associated with this Equipment for a given SubmissionType

        Args:
            submission_type (SubmissionType): SubmissionType of interest
            extraction_kit (str | KitType | None, optional): KitType to filter by. Defaults to None.

        Returns:
            List[Process]: List of process names
        """
        processes = [process for process in self.processes if submission_type in process.submission_types]
        match extraction_kit:
            case str():
                # logger.debug(f"Filtering processes by extraction_kit str {extraction_kit}")
                processes = [process for process in processes if
                             extraction_kit in [kit.name for kit in process.kit_types]]
            case KitType():
                # logger.debug(f"Filtering processes by extraction_kit KitType {extraction_kit}")
                processes = [process for process in processes if extraction_kit in process.kit_types]
            case _:
                pass
        # NOTE: Convert to strings
        processes = [process.name for process in processes]
        assert all([isinstance(process, str) for process in processes])
        if len(processes) == 0:
            processes = ['']
        return processes

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
                # logger.debug(f"Lookup Equipment by name str {name}")
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        match nickname:
            case str():
                # logger.debug(f"Lookup Equipment by nickname str {nickname}")
                query = query.filter(cls.nickname == nickname)
                limit = 1
            case _:
                pass
        match asset_number:
            case str():
                # logger.debug(f"Lookup Equipment by asset_number str {asset_number}")
                query = query.filter(cls.asset_number == asset_number)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def to_pydantic(self, submission_type: SubmissionType,
                    extraction_kit: str | KitType | None = None,
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
        return PydEquipment(
            processes=self.get_processes(submission_type=submission_type, extraction_kit=extraction_kit), role=role,
            **self.to_dict(processes=False))

    @classmethod
    def get_regex(cls) -> re.Pattern:
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
        choices = input(f"Enter equipment numbers to add to {equipment_role.name} (space seperated):\n{options}\n\n")
        output = []
        for choice in choices.split(" "):
            try:
                choice = int(choice)
            except (AttributeError, ValueError):
                continue
            output.append(equipment[choice])
        return output


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

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this EquipmentRole
        """
        return f"<EquipmentRole({self.name})>"

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
        # logger.debug("Creating list of PydEquipment in this role")
        equipment = [item.to_pydantic(submission_type=submission_type, extraction_kit=extraction_kit) for item in
                     self.instances]
        pyd_dict = self.to_dict()
        # logger.debug("Creating list of Processes in this role")
        pyd_dict['processes'] = self.get_processes(submission_type=submission_type, extraction_kit=extraction_kit)
        return PydEquipmentRole(equipment=equipment, **pyd_dict)

    @classmethod
    @setup_lookup
    def query(cls, name: str | None = None, id: int | None = None, limit: int = 0) -> EquipmentRole | List[
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
                # logger.debug(f"Lookup EquipmentRole by id {id}")
                query = query.filter(cls.id == id)
                limit = 1
            case _:
                pass
        match name:
            case str():
                # logger.debug(f"Lookup EquipmentRole by name str {name}")
                query = query.filter(cls.name == name)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    def get_processes(self, submission_type: str | SubmissionType | None,
                      extraction_kit: str | KitType | None = None) -> List[Process]:
        """
        Get processes used by this EquipmentRole

        Args:
            submission_type (str | SubmissionType | None): SubmissionType of interest
            extraction_kit (str | KitType | None, optional): KitType of interest. Defaults to None.

        Returns:
            List[Process]: _description_
        """
        if isinstance(submission_type, str):
            # logger.debug(f"Checking if str {submission_type} exists")
            submission_type = SubmissionType.query(name=submission_type)
        if submission_type is not None:
            # logger.debug("Getting all processes for this EquipmentRole")
            processes = [process for process in self.processes if submission_type in process.submission_types]
        else:
            processes = self.processes
        match extraction_kit:
            case str():
                # logger.debug(f"Filtering processes by extraction_kit str {extraction_kit}")
                processes = [item for item in processes if extraction_kit in [kit.name for kit in item.kit_types]]
            case KitType():
                # logger.debug(f"Filtering processes by extraction_kit KitType {extraction_kit}")
                processes = [item for item in processes if extraction_kit in [kit for kit in item.kit_types]]
            case _:
                pass
        output = [item.name for item in processes]
        if len(output) == 0:
            return ['']
        else:
            return output

    def to_export_dict(self, submission_type: SubmissionType, kit_type: KitType):
        """
        Creates a dictionary of relevant values in this object.

        Returns:
            dict: dictionary of Association and related reagent role
        """
        return dict(role=self.name,
                    processes=self.get_processes(submission_type=submission_type, extraction_kit=kit_type))
        # base_dict['role'] = self.name
        # base_dict['processes'] = self.get_processes(submission_type=submission_type, extraction_kit=kit_type)
        # return base_dict


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

    def __repr__(self):
        return f"<SubmissionEquipmentAssociation({self.submission.rsl_plate_num} & {self.equipment.name})>"

    def __init__(self, submission, equipment, role: str = "None"):
        self.submission = submission
        self.equipment = equipment
        self.role = role

    def to_sub_dict(self) -> dict:
        """
        This SubmissionEquipmentAssociation as a dictionary

        Returns:
            dict: This SubmissionEquipmentAssociation as a dictionary
        """
        # TODO: Currently this will only fetch a single process, even if multiple are selectable.
        try:
            process = self.process.name
        except AttributeError:
            process = "No process found"
        output = dict(name=self.equipment.name, asset_number=self.equipment.asset_number, comment=self.comments,
                      processes=[process], role=self.role, nickname=self.equipment.nickname)
        return output

    @classmethod
    @setup_lookup
    def query(cls, equipment_id: int, submission_id: int, role: str | None = None, limit: int = 0, **kwargs) -> Any | \
                                                                                                                List[
                                                                                                                    Any]:
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

    def get_all_processes(self, extraction_kit: KitType | str | None = None) -> List[Process]:
        """
        Get all processes associated with this SubmissionTypeEquipmentRole

        Args:
            extraction_kit (KitType | str | None, optional): KitType of interest. Defaults to None.

        Returns:
            List[Process]: All associated processes
        """
        processes = [equipment.get_processes(self.submission_type) for equipment in self.equipment_role.instances]
        # NOTE: flatten list
        processes = [item for items in processes for item in items if item is not None]
        match extraction_kit:
            case str():
                # logger.debug(f"Filtering Processes by extraction_kit str {extraction_kit}")
                processes = [item for item in processes if extraction_kit in [kit.name for kit in item.kit_type]]
            case KitType():
                # logger.debug(f"Filtering Processes by extraction_kit KitType {extraction_kit}")
                processes = [item for item in processes if extraction_kit in [kit for kit in item.kit_type]]
            case _:
                pass
        return processes

    @check_authorization
    def save(self):
        super().save()

    def to_export_dict(self, kit_type: KitType):
        base_dict = {k: v for k, v in self.equipment_role.to_export_dict(submission_type=self.submission_type,
                                                                         kit_type=kit_type).items()}
        base_dict['static'] = self.static
        return base_dict


class Process(BaseClass):
    """
    A Process is a method used by a piece of equipment.
    """

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

    def __repr__(self) -> str:
        """
        Returns:
            str: Representation of this Process
        """
        return f"<Process({self.name})>"

    @classmethod
    @setup_lookup
    def query(cls,
              name: str | None = None,
              id: int | None = None,
              limit: int = 0) -> Process | List[Process]:
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
        match name:
            case str():
                # logger.debug(f"Lookup Process with name str {name}")
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

    def __repr__(self):
        return f"<TipRole({self.name})>"

    @check_authorization
    def save(self):
        super().save()


class Tips(BaseClass):
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

    def __repr__(self):
        return f"<Tips({self.name})>"

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
                # logger.debug(f"Lookup Equipment by name str {name}")
                query = query.filter(cls.name == name)
            case _:
                pass
        match lot:
            case str():
                # logger.debug(f"Lookup Equipment by nickname str {nickname}")
                query = query.filter(cls.lot == lot)
                limit = 1
            case _:
                pass
        return cls.execute_query(query=query, limit=limit)

    @check_authorization
    def save(self):
        super().save()


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

    @check_authorization
    def save(self):
        super().save()


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
    def query(cls, tip_id: int, role: str, submission_id: int | None = None, limit: int = 0, **kwargs) -> Any | List[
        Any]:
        query: Query = cls.__database_session__.query(cls)
        query = query.filter(cls.tip_id == tip_id)
        if submission_id is not None:
            query = query.filter(cls.submission_id == submission_id)
        query = query.filter(cls.role_name == role)
        return cls.execute_query(query=query, limit=limit, **kwargs)
