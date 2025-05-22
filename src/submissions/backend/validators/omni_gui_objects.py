"""
Collection of pydantic objects to be used in the Gui system.
"""

from __future__ import annotations
import logging
from pydantic import BaseModel, field_validator, Field
from typing import List, ClassVar
from backend.db.models import *
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.orm.relationships import _RelationshipDeclared

logger = logging.getLogger(f"submissions.{__name__}")


class BaseOmni(BaseModel):

    instance_object: Any | None = Field(default=None)

    def __repr__(self):
        try:
            return f"<{self.__class__.__name__}({self.name})>"
        except AttributeError:
            return f"<{self.__class__.__name__}({self.__repr_name__})>"

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names the sql object of this class might go by.

        Returns:
            List[str]: List of names
        """
        return cls.class_object.aliases

    def check_all_attributes(self, attributes: dict) -> bool:
        """
        Compares this pobject to dictionary of attributes to determine equality.

        Args:
            attributes (dict):

        Returns:
            bool: result
        """
        # logger.debug(f"Incoming attributes: {attributes}")
        attributes = {k : v for k, v in attributes.items() if k in self.list_searchables.keys()}
        for key, value in attributes.items():
            try:
                # logger.debug(f"Check if {value.__class__} is subclass of {BaseOmni}")
                check = issubclass(value.__class__, BaseOmni)
            except TypeError as e:
                logger.error(f"Couldn't check if {value.__class__} is subclass of {BaseOmni} due to {e}")
                check = False
            if check:
                # logger.debug(f"Checking for subclass name.")
                value = value.name
            self_value = self.list_searchables[key]
            if value != self_value:
                # logger.debug(f"Value {key} is False, these are not the same object.")
                return False
        # logger.debug("Everything checks out, these are the same object.")
        return True

    def __setattr__(self, key: str, value: Any):
        """
        Overrides built in dunder method

        Args:
            key (str):
            value (Any):
        """
        try:
            class_value = getattr(self.class_object, key)
        except AttributeError:
            return super().__setattr__(key, value)
        try:
            new_key = class_value.impl.key
        except AttributeError:
            new_key = None
        # logger.debug(f"Class value before new key: {class_value.property}")
        if new_key and new_key != key:
            class_value = getattr(self.class_object, new_key)
        # logger.debug(f"Class value after new key: {class_value.property}")
        if isinstance(class_value, InstrumentedAttribute):
            # logger.debug(f"{key} is an InstrumentedAttribute with class_value.property: {class_value.property}.")
            match class_value.property:
                case ColumnProperty():
                    # logger.debug(f"Setting ColumnProperty to {value}")
                    return super().__setattr__(key, value)
                case _RelationshipDeclared():
                    # logger.debug(f" {self.__class__.__name__} Setting _RelationshipDeclared for {key} to {value}")
                    if class_value.property.uselist:
                        # logger.debug(f"Setting {key} with uselist")
                        existing = self.__getattribute__(key)
                        if existing is not None:
                            # NOTE: Getting some really weird duplicates for OmniSubmissionTypeKitTypeAssociation here.
                            # logger.debug(f"Existing: {existing}, incoming: {value}")
                            if isinstance(value, list):
                                if value != existing:
                                    value = existing + value
                                else:
                                    value = existing
                            else:
                                if issubclass(value.__class__, self.__class__):
                                    value = value.to_sql()
                                value = existing + [value]
                        else:
                            if issubclass(value.__class__, self.__class__):
                                value = value.to_sql()
                            value = [value]
                        # logger.debug(f"Final value for {key}: {value}")
                        return super().__setattr__(key, value)
                    else:
                        if isinstance(value, list):
                            if len(value) == 1:
                                value = value[0]
                            else:
                                raise ValueError("Object is too long to parse a single value.")
                        return super().__setattr__(key, value)
                case _:
                    return super().__setattr__(key, value)
        else:
            return super().__setattr__(key, value)


class OmniSubmissionType(BaseOmni):

    class_object: ClassVar[Any] = SubmissionType

    name: str = Field(default="", description="property")
    info_map: dict = Field(default={}, description="property")
    defaults: dict = Field(default={}, description="property")
    template_file: bytes = Field(default=bytes(), description="property")
    sample_map: dict = Field(default={}, description="property")

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    @field_validator("sample_map", mode="before")
    @classmethod
    def rescue_sample_map_none(cls, value):
        if not value:
            return {}
        return value

    @field_validator("defaults", mode="before")
    @classmethod
    def rescue_defaults_none(cls, value):
        if not value:
            return {}
        return value

    @field_validator("info_map", mode="before")
    @classmethod
    def rescue_info_map_none(cls, value):
        if not value:
            return {}
        return value

    @field_validator("template_file", mode="before")
    @classmethod
    def provide_blank_template_file(cls, value):
        if value is None:
            value = bytes()
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """
        instance, new = self.class_object.query_or_create(name=self.name)
        instance.info_map = self.info_map
        instance.defaults = self.defaults
        instance.sample_map = self.sample_map
        if self.template_file:
            instance.template_file = self.template_file
        return instance


class OmniReagentRole(BaseOmni):

    class_object: ClassVar[Any] = ReagentRole

    name: str = Field(default="", description="property")
    eol_ext: timedelta = Field(default=timedelta(days=0), description="property")

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    @field_validator("eol_ext", mode="before")
    @classmethod
    def rescue_eol_ext(cls, value):
        if not value:
            value = timedelta(days=0)
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        instance, new = self.class_object.query_or_create(name=self.name)
        if new:
            instance.eol_ext = self.eol_ext
        return instance


class OmniSubmissionTypeKitTypeAssociation(BaseOmni):

    class_object: ClassVar[Any] = SubmissionTypeKitTypeAssociation

    submissiontype: str | OmniSubmissionType = Field(default="", description="relationship", title="SubmissionType")
    kittype: str | OmniKitType = Field(default="", description="relationship", title="KitType")
    mutable_cost_column: float = Field(default=0.0, description="property")
    mutable_cost_sample: float = Field(default=0.0, description="property")
    constant_cost: float = Field(default=0.0, description="property")

    def __repr__(self):
        if isinstance(self.submissiontype, str):
            submissiontype = self.submissiontype
        else:
            submissiontype = self.submissiontype.name
        if isinstance(self.kittype, str):
            kittype = self.kittype
        else:
            kittype = self.kittype.name
        try:
            return f"<{self.__class__.__name__}({submissiontype}&{kittype})>"
        except AttributeError:
            return f"<{self.__class__.__name__}(NO NAME)>"

    @field_validator("proceduretype", mode="before")
    @classmethod
    def rescue_submissiontype_none(cls, value):
        if not value:
            return ""
        return value

    @field_validator("kittype", mode="before")
    @classmethod
    def rescue_kittype_none(cls, value):
        if not value:
            return ""
        return value

    @field_validator("kittype")
    @classmethod
    def no_list_please(cls, value):
        if isinstance(value, list):
            raise ValueError("List is not allowed for kittype.")
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        if isinstance(self.submissiontype, OmniSubmissionType):
            submissiontype = self.submissiontype.name
        else:
            submissiontype = self.submissiontype
        if isinstance(self.kittype, OmniKitType):
            kittype = self.kittype.name
        else:
            kittype = self.kittype
        return dict(
            submissiontype=submissiontype,
            kittype=kittype,
            mutable_cost_column=self.mutable_cost_column,
            mutable_cost_sample=self.mutable_cost_sample,
            constant_cost=self.constant_cost
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        # logger.debug(f"Self kittype: {self.proceduretype}")
        if issubclass(self.submissiontype.__class__, BaseOmni):
            submissiontype = SubmissionType.query(name=self.submissiontype.name)
        else:
            submissiontype = SubmissionType.query(name=self.submissiontype)
        if issubclass(self.kittype.__class__, BaseOmni):
            kittype = KitType.query(name=self.kittype.name)
        else:
            kittype = KitType.query(name=self.kittype)
        # logger.debug(f"Self kittype: {self.kittype}")
        # logger.debug(f"Query or create with {kittype}, {proceduretype}")
        instance, is_new = self.class_object.query_or_create(kittype=kittype, submissiontype=submissiontype)
        instance.mutable_cost_column = self.mutable_cost_column
        instance.mutable_cost_sample = self.mutable_cost_sample
        instance.constant_cost = self.constant_cost
        return instance

    @property
    def list_searchables(self) -> dict:
        """
        Provides attributes for checking this object against a dictionary.

        Returns:
            dict: result
        """
        if isinstance(self.kittype, OmniKitType):
            kit = self.kittype.name
        else:
            kit = self.kittype
        if isinstance(self.submissiontype, OmniSubmissionType):
            subtype = self.submissiontype.name
        else:
            subtype = self.submissiontype
        return dict(kittype=kit, submissiontype=subtype)


class OmniKitTypeReagentRoleAssociation(BaseOmni):

    class_object: ClassVar[Any] = KitTypeReagentRoleAssociation

    reagent_role: str | OmniReagentRole = Field(default="", description="relationship", title="ReagentRole")
    uses: dict = Field(default={}, description="property")
    required: bool = Field(default=True, description="property")
    submission_type: str | OmniSubmissionType = Field(default="", description="relationship", title="SubmissionType")
    kit_type: str | OmniKitType = Field(default="", description="relationship", title="KitType")

    def __repr__(self):
        try:
            return f"<OmniKitTypeReagentRoleAssociation({self.kit_type.name}&{self.reagent_role.name})>"
        except AttributeError:
            return f"<OmniKitTypeReagentRoleAssociation(NO NAME)>"

    @field_validator("uses", mode="before")
    @classmethod
    def rescue_uses_none(cls, value):
        if not value:
            return {}
        return value

    @field_validator("required", mode="before")
    @classmethod
    def rescue_required_none(cls, value):
        if not value:
            value = 1
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        if isinstance(self.submission_type, OmniSubmissionType):
            submission_type = self.submission_type.name
        else:
            submission_type = self.submission_type
        if isinstance(self.kit_type, OmniKitType):
            kit_type = self.kit_type.name
        else:
            kit_type = self.kit_type
        # logger.debug(f"Using name: {name}")
        if isinstance(self.reagent_role, OmniReagentRole):
            reagent_role = self.reagent_role.name
        else:
            reagent_role = self.reagent_role
        return dict(
            reagentrole=reagent_role,
            submissiontype=submission_type,
            kittype=kit_type
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        if isinstance(self.reagent_role, OmniReagentRole):
            reagent_role = self.reagent_role.name
        else:
            reagent_role = self.reagent_role
        if issubclass(self.submission_type.__class__, BaseOmni):
            submissiontype = self.submission_type.name
        else:
            submissiontype = self.submission_type
        if issubclass(self.kit_type.__class__, BaseOmni):
            kittype = self.kit_type.name
        else:
            kittype = self.kit_type
        instance, new = self.class_object.query_or_create(
            reagentrole=reagent_role,
            kittype=kittype,
            submissiontype=submissiontype
        )
        # logger.debug(f"KitTypeReagentRoleAssociation coming out of query_or_create: {instance.__dict__}\nnew: {new}")
        if new:
            logger.warning(f"This is a new instance: {instance.__dict__}")
            try:
                reagent_role = self.reagent_role.to_sql()
            except AttributeError:
                reagent_role = ReagentRole.query(name=self.reagent_role)
            instance.reagent_role = reagent_role
        # logger.debug(f"KTRRAssoc uses: {self.uses}")
        instance.uses = self.uses
        instance.required = int(self.required)
        # logger.debug(f"KitTypeReagentRoleAssociation: {pformat(instance.__dict__)}")
        return instance

    @property
    def list_searchables(self) -> dict:
        """
        Provides attributes for checking this object against a dictionary.

        Returns:
            dict: result
        """
        if isinstance(self.kit_type, OmniKitType):
            kit = self.kit_type.name
        else:
            kit = self.kit_type
        if isinstance(self.submission_type, OmniSubmissionType):
            subtype = self.submission_type.name
        else:
            subtype = self.submission_type
        if isinstance(self.reagent_role, OmniReagentRole):
            reagentrole = self.reagent_role.name
        else:
            reagentrole = self.reagent_role
        return dict(kit_type=kit, submission_type=subtype, reagent_role=reagentrole)


class OmniEquipmentRole(BaseOmni):

    class_object: ClassVar[Any] = EquipmentRole

    name: str = Field(default="", description="property")

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        instance, new = self.class_object.query_or_create(name=self.name)
        return instance


class OmniTips(BaseOmni):

    class_object: ClassVar[Any] = Tips

    name: str = Field(default="", description="property")

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        instance, new = self.class_object.query_or_create(name=self.name)
        return instance


class OmniTipRole(BaseOmni):

    class_object: ClassVar[Any] = TipRole

    name: str = Field(default="", description="property")
    tips: List[OmniTips] = Field(default=[], description="relationship", title="Tips")

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name,
            tips=[item.name for item in self.tips]
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        instance, new = self.class_object.query_or_create(name=self.name)
        for tips in self.tips:
            tips.to_sql()
        return instance


class OmniProcess(BaseOmni):

    class_object: ClassVar[Any] = Process

    # NOTE: How am I going to figure out relatioinships without getting into recursion issues?
    name: str = Field(default="", description="property")  #: Process name
    submission_types: List[OmniSubmissionType] | List[str] = Field(default=[], description="relationship",
                                                                   title="SubmissionType")
    equipment_roles: List[OmniEquipmentRole] | List[str] = Field(default=[], description="relationship",
                                                                 title="EquipmentRole")
    tip_roles: List[OmniTipRole] | List[str] = Field(default=[], description="relationship", title="TipRole")

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        submissiontypes = [item if isinstance(item, str) else item.name for item in self.submission_types]
        logger.debug(f"Submission Types: {submissiontypes}")
        equipmentroles = [item if isinstance(item, str) else item.name for item in self.equipment_roles]
        logger.debug(f"Equipment Roles: {equipmentroles}")
        return dict(
            name=self.name,
            submission_types=submissiontypes,
            equipment_roles=equipmentroles
        )

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        instance, new = self.class_object.query_or_create(name=self.name)
        for st in self.submission_types:
            try:
                new_assoc = st.to_sql()
            except AttributeError:
                new_assoc = SubmissionType.query(name=st)
            if new_assoc not in instance.proceduretype:
                instance.proceduretype.append(new_assoc)
        for er in self.equipment_roles:
            try:
                new_assoc = er.to_sql()
            except AttributeError:
                new_assoc = EquipmentRole.query(name=er)
            if new_assoc not in instance.equipmentrole:
                instance.equipmentrole.append(new_assoc)
        for tr in self.tip_roles:
            try:
                new_assoc = tr.to_sql()
            except AttributeError:
                new_assoc = TipRole.query(name=tr)
            if new_assoc not in instance.tiprole:
                instance.tiprole.append(new_assoc)
        return instance

    @property
    def list_searchables(self) -> dict:
        """
        Provides attributes for checking this object against a dictionary.

        Returns:
            dict: result
        """
        return dict(name=self.name)


class OmniKitType(BaseOmni):

    class_object: ClassVar[Any] = KitType

    name: str = Field(default="", description="property")
    kit_submissiontype_associations: List[OmniSubmissionTypeKitTypeAssociation] | List[str] = Field(default=[], description="relationship", title="SubmissionTypeKitTypeAssociation")
    kit_reagentrole_associations: List[OmniKitTypeReagentRoleAssociation] | List[str] = Field(default=[], description="relationship", title="KitTypeReagentRoleAssociation")
    processes: List[OmniProcess] | List[str] = Field(default=[], description="relationship", title="Process")

    @field_validator("name", mode="before")
    @classmethod
    def rescue_name_none(cls, value):
        if not value:
            return ""
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name
        )

    def to_sql(self) -> KitType:
        """
        Convert this object to an instance of its class object.
        """

        kit, is_new = KitType.query_or_create(name=self.name)
        new_rr = []
        for rr_assoc in self.kit_reagentrole_associations:
            new_assoc = rr_assoc.to_sql()
            if new_assoc not in new_rr:
                # logger.debug(f"Adding {new_assoc} to kit_reagentrole_associations")
                new_rr.append(new_assoc)
        # logger.debug(f"Setting kit_reagentrole_associations to {pformat([item.__dict__ for item in new_rr])}")
        kit.kit_reagentrole_associations = new_rr
        new_st = []
        for st_assoc in self.kit_submissiontype_associations:
            new_assoc = st_assoc.to_sql()
            if new_assoc not in new_st:
                new_st.append(new_assoc)
        kit.kit_submissiontype_associations = new_st
        new_processes = []
        for process in self.processes:
            new_process = process.to_sql()
            if new_process not in new_processes:
                new_processes.append(new_process)
        kit.processes = new_processes
        return kit


class OmniOrganization(BaseOmni):

    class_object: ClassVar[Any] = Organization

    name: str = Field(default="", description="property")
    cost_centre: str = Field(default="", description="property")
    contact: List[str] | List[OmniContact] = Field(default=[], description="relationship", title="Contact")

    def __init__(self, instance_object: Any, **data):
        # logger.debug(f"Incoming data: {data}")
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name,
            cost_centre=self.cost_centre,
            contacts=self.contact
        )


class OmniContact(BaseOmni):

    class_object: ClassVar[Any] = Contact

    name: str = Field(default="", description="property")
    email: str = Field(default="", description="property")
    phone: str = Field(default="", description="property")

    @property
    def list_searchables(self) -> dict:
        """
        Provides attributes for checking this object against a dictionary.

        Returns:
            dict: result
        """
        return dict(name=self.name, email=self.email)

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    @property
    def dataframe_dict(self) -> dict:
        """
        Dictionary of gui relevant values.

        Returns:
            dict: result
        """
        return dict(
            name=self.name,
            email=self.email,
            phone=self.phone
        )

    def to_sql(self):
        """
        Convert this object to an instance of its class object.
        """

        contact, is_new = Contact.query_or_create(name=self.name, email=self.email, phone=self.phone)
        return contact
