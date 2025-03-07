from __future__ import annotations
import logging
import sys

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
            return f"<{self.__class__.__name__}(NO NAME)>"

    @classproperty
    def aliases(cls):
        return cls.class_object.aliases

    def check_all_attributes(self, attributes: dict) -> bool:
        """
        Checks this instance against a dictionary of attributes to determine if they are a match.

        Args:
            attributes (dict): A dictionary of attributes to be check for equivalence

        Returns:
            bool: If a single unequivocal value is found will be false, else true.
        """
        logger.debug(f"Incoming attributes: {attributes}")
        for key, value in attributes.items():
            # print(getattr(self.__class__, key).property)
            if value.lower() == "none":
                value = None
            logger.debug(f"Attempting to grab attribute: {key}")
            self_value = getattr(self, key)
            class_attr = getattr(self.class_object, key)
            # logger.debug(f"Self value: {self_value}, class attr: {class_attr} of type: {type(class_attr)}")
            if isinstance(class_attr, property):
                filter = "property"
            else:
                filter = class_attr.property
            match filter:
                case ColumnProperty():
                    match class_attr.type:
                        case INTEGER():
                            if value.lower() == "true":
                                value = 1
                            elif value.lower() == "false":
                                value = 0
                            else:
                                value = int(value)
                        case FLOAT():
                            value = float(value)
                case "property":
                    pass
                case _RelationshipDeclared():
                    logger.debug(f"Checking {self_value}")
                    try:
                        self_value = self_value.name
                    except AttributeError:
                        pass
                    if class_attr.property.uselist:
                        self_value = self_value.__str__()
            try:
                logger.debug(f"Check if {self_value.__class__} is subclass of {self.__class__}")
                check = issubclass(self_value.__class__, self.__class__)
            except TypeError as e:
                logger.error(f"Couldn't check if {self_value.__class__} is subclass of {self.__class__} due to {e}")
                check = False
            if check:
                logger.debug(f"Checking for subclass name.")
                self_value = self_value.name
            logger.debug(
                f"Checking self_value {self_value} of type {type(self_value)} against attribute {value} of type {type(value)}")
            if self_value != value:
                output = False
                logger.debug(f"Value {key} is False, returning.")
                return output
        return True

    def __setattr__(self, key, value):
        try:
            class_value = getattr(self.class_object, key)
        except AttributeError:
            return super().__setattr__(key, value)
        try:
            new_key = class_value.impl.key
        except AttributeError:
            new_key = None
        logger.debug(f"Class value before new key: {class_value.property}")
        if new_key and new_key != key:
            class_value = getattr(self.class_object, new_key)
        logger.debug(f"Class value after new key: {class_value.property}")
        if isinstance(class_value, InstrumentedAttribute):
            logger.debug(f"{key} is an InstrumentedAttribute with class_value.property: {class_value.property}.")
            match class_value.property:
                case ColumnProperty():
                    logger.debug(f"Setting ColumnProperty to {value}")
                    return super().__setattr__(key, value)
                case _RelationshipDeclared():
                    logger.debug(f" {self.__class__.__name__} Setting _RelationshipDeclared for {key} to {value}")
                    if class_value.property.uselist:
                        logger.debug(f"Setting {key} with uselist")
                        existing = self.__getattribute__(key)
                        if existing is not None:
                            # NOTE: Getting some really weird duplicates for OmniSubmissionTypeKitTypeAssociation here.
                            logger.debug(f"Existing: {existing}, incoming: {value}")
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
                        # value = list(set(value))
                        logger.debug(f"Final value for {key}: {value}")
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

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    def to_dataframe_dict(self):
        return dict(
            name=self.name
        )

    def to_sql(self):
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

    def to_dataframe_dict(self):
        return dict(
            name=self.name
        )

    def to_sql(self):
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
    # processes: List[OmniProcess] | List[str] = Field(default=[], description="relationship", title="Process")

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

    @field_validator("submissiontype", mode="before")
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

    def to_dataframe_dict(self):
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
        logger.debug(f"Self kittype: {self.submissiontype}")
        if issubclass(self.submissiontype.__class__, BaseOmni):
            submissiontype = SubmissionType.query(name=self.submissiontype.name)
        else:
            submissiontype = SubmissionType.query(name=self.submissiontype)
        if issubclass(self.kittype.__class__, BaseOmni):
            kittype = KitType.query(name=self.kittype.name)
        else:
            kittype = KitType.query(name=self.kittype)
        # logger.debug(f"Self kittype: {self.kittype}")
        # kittype = KitType.query(name=self.kittype)
        logger.debug(f"Query or create with {kittype}, {submissiontype}")
        instance, is_new = self.class_object.query_or_create(kittype=kittype, submissiontype=submissiontype)
        instance.mutable_cost_column = self.mutable_cost_column
        instance.mutable_cost_sample = self.mutable_cost_sample
        instance.constant_cost = self.constant_cost
        return instance


class OmniKitTypeReagentRoleAssociation(BaseOmni):
    class_object: ClassVar[Any] = KitTypeReagentRoleAssociation

    reagent_role: str | OmniReagentRole = Field(default="", description="relationship", title="ReagentRole")
    uses: dict = Field(default={}, description="property")
    required: bool = Field(default=True, description="property")
    submission_type: str | OmniSubmissionType = Field(default="", description="relationship", title="SubmissionType")
    kit_type: str | OmniKitType = Field(default="", description="relationship", title="KitType")


    @field_validator("uses", mode="before")
    @classmethod
    def rescue_uses_none(cls, value):
        if not value:
            return {}
        return value

    def __init__(self, instance_object: Any, **data):
        super().__init__(**data)
        self.instance_object = instance_object

    def to_dataframe_dict(self):
        if isinstance(self.submission_type, OmniSubmissionType):
            submission_type = self.submission_type.name
        else:
            submission_type = self.submission_type
        if isinstance(self.kit_type, OmniKitType):
            kit_type = self.kit_type.name
        else:
            kit_type = self.kit_type
        # name = f"{kit_type} -> {self.reagent_role}"
        # logger.debug(f"Using name: {name}")
        if isinstance(self.reagent_role, OmniReagentRole):
            reagent_role = self.reagent_role.name
        else:
            reagent_role = self.reagent_role
        return dict(
            reagent_role=reagent_role,
            # name=self.reagent_role.name,
            submission_type=submission_type,
            kit_type=kit_type
        )

    def to_sql(self):
        if isinstance(self.reagent_role, OmniReagentRole):
            reagent_role = self.reagent_role.name
        else:
            reagent_role = self.reagent_role
        instance, new = self.class_object.query_or_create(
            reagentrole=reagent_role,
            kittype=self.kit_type,
            submissiontype=self.submission_type
        )
        if new:
            reagent_role = self.reagent_role.to_sql()
            instance.reagent_role = reagent_role
        logger.debug(f"KTRRAssoc uses: {self.uses}")
        instance.uses = self.uses
        logger.debug(f"KitTypeReagentRoleAssociation: {pformat(instance.__dict__)}")

        return instance


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

    def to_dataframe_dict(self):
        return dict(
            name=self.name
        )

    def to_sql(self):
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

    def to_dataframe_dict(self):
        return dict(
            name=self.name
        )

    def to_sql(self):
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

    def to_dataframe_dict(self):
        return dict(
            name=self.name,
            tips=[item.name for item in self.tips]
        )

    def to_sql(self):
        instance, new = self.class_object.query_or_create(name=self.name)
        for tips in self.tips:
            tips.to_sql()
            # if new_assoc not in instance.instances:
            #     instance.instances.append(new_assoc)
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

    def to_dataframe_dict(self):
        submissiontypes = [item.name for item in self.submission_types]
        logger.debug(f"Submission Types: {submissiontypes}")
        equipmentroles = [item.name for item in self.equipment_roles]
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
        instance, new = self.class_object.query_or_create(name=self.name)
        for st in self.submission_types:
            new_assoc = st.to_sql()
            if new_assoc not in instance.submission_types:
                instance.submission_types.append(new_assoc)
        for er in self.equipment_roles:
            new_assoc = er.to_sql()
            if new_assoc not in instance.equipment_roles:
                instance.equipment_roles.append(new_assoc)
        for tr in self.tip_roles:
            new_assoc = tr.to_sql()
            if new_assoc not in instance.tip_roles:
                instance.tip_roles.append(new_assoc)
        return instance


class OmniKitType(BaseOmni):
    class_object: ClassVar[Any] = KitType

    name: str = Field(default="", description="property")
    kit_submissiontype_associations: List[OmniSubmissionTypeKitTypeAssociation] | List[str] = Field(default=[],
                                                                                        description="relationship",
                                                                                        title="SubmissionTypeKitTypeAssociation")
    kit_reagentrole_associations: List[OmniKitTypeReagentRoleAssociation] | List[str] = Field(default=[],
                                                                                  description="relationship",
                                                                                  title="KitTypeReagentRoleAssociation")
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

    def to_dataframe_dict(self):
        return dict(
            name=self.name
        )

    def to_sql(self) -> KitType:
        kit, is_new = KitType.query_or_create(name=self.name)
        if is_new:
            logger.debug(f"New kit made: {kit}")
        else:
            logger.debug(f"Kit retrieved: {kit}")
        new_rr = []
        for rr_assoc in self.kit_reagentrole_associations:
            new_assoc = rr_assoc.to_sql()
            if new_assoc not in new_rr:
                logger.debug(f"Adding {new_assoc} to kit_reagentrole_associations")
                new_rr.append(new_assoc)
        logger.debug(f"Setting kit_reagentrole_associations to {new_rr}")
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
        logger.debug(f"Kit: {pformat(kit.__dict__)}")
        for item in kit.kit_reagentrole_associations:
            logger.debug(f"KTRRassoc: {item.__dict__}")
        return kit
