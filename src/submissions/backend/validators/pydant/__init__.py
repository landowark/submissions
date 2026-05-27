"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
from pathlib import Path
import logging, sys, string, inspect, re
from pprint import pformat
from jinja2 import Template, TemplateNotFound
from pydantic import BaseModel, Field, ValidationError, ValidationInfo, model_validator, ConfigDict, field_validator
from pydantic_core import core_schema
from pydantic.fields import FieldInfo
from datetime import date, datetime
from typing import Any, Generator, List, Generic, TypeVar, Annotated, get_args, get_origin
from types import UnionType
from tools import classproperty, jinja_template_loading, row_keys, DotDict
from backend.db import models
# NOTE: Below is necessary for test environment
from backend.db.models import BaseClass
from dateutil.parser import parse
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.ext.associationproxy import _AssociationList
from PyQt6.QtWidgets import QDialog

logger = logging.getLogger(f"submission.{__name__}")

T = TypeVar("T")


class SourcedField(BaseModel, Generic[T]):
    """
    Wraps a field value with a flag recording whether the value was
    parsed from the source document (missing=False) or generated as a
    fallback default (missing=True).
 
    Replaces the ad-hoc  {value: ..., missing: bool}  dict pattern
    used throughout PydClientSubmission and PydRun.
 
    Usage
    -----
    # Construct directly
    sf = SourcedField(value="RSL-WW-20240101-1", missing=False)
 
    # Coerce from any raw input (str, scalar, existing dict, or None)
    sf = SourcedField.from_raw("RSL-WW-20240101-1")    # missing=False
    sf = SourcedField.from_raw(None)                   # missing=True
    sf = SourcedField.from_raw({"value": "x", "missing": False})
 
    # Unwrap
    sf.value     # "RSL-WW-20240101-1"
    sf.missing   # False
    """
 
    value: T | None = None
    missing: bool = True
 
    @classmethod
    def from_raw(cls, raw: Any, missing_if_none: bool = True) -> "SourcedField[T]":
        """
        Coerce a raw value into a SourcedField.
 
        Handles every input shape that currently exists in the codebase:
          - Already a SourcedField  → returned as-is
          - A {value, missing} dict → unpacked
          - None                    → SourcedField(value=None, missing=True)
          - Any scalar              → SourcedField(value=raw, missing=False)
        """
        if isinstance(raw, SourcedField):
            return raw
        if isinstance(raw, dict) and "value" in raw:
            return cls(value=raw.get("value"), missing=raw.get("missing", True))
        if raw is None:
            return cls(value=None, missing=missing_if_none)
        return cls(value=raw, missing=False)
    
    def get(self, attribute_name:str, default: Any | None=  None):
        try:
            value = self.__getattribute__(attribute_name)
        except AttributeError:
            value = default
        return value
 
    def __repr__(self) -> str:
        flag = "~" if self.missing else ""
        return f"SourcedField({flag}{self.value!r})"
 
# ─────────────────────────────────────────────────────────────────────────────
# Shared coercion helpers used by both PydClientSubmission and PydRun.
# These go at module level in pydant/__init__.py, just below SourcedField.
#
# Each helper takes a raw input and returns a SourcedField with the
# value coerced to the expected Python type.
# ─────────────────────────────────────────────────────────────────────────────
 
def _coerce_str_field(raw: Any) -> SourcedField[str]:
    """
    Coerce a raw value to SourcedField[str].
 
    Replaces:
      enforce_value()            on submissiontype / clientlab / contact
      enforce_submitter_plate_id() on submitter_plate_id
      enforce_submission_category_id() on submission_category
      str_to_dict()              on cost_centre
      rescue_rsl_number()        on rsl_plate_number
      rescue_signed_by()         on signed_by
    """
    if isinstance(raw, SourcedField):
        return raw
    if isinstance(raw, dict) and "value" in raw:
        return SourcedField(value=str(raw["value"]) if raw["value"] is not None else None,
                            missing=raw.get("missing", True))
    if raw is None:
        return SourcedField(value=None, missing=True)
    return SourcedField(value=str(raw), missing=False)
 
 
def _coerce_datetime_field(raw: Any, fallback: datetime | None = None) -> SourcedField[datetime]:
    """
    Coerce a raw value to SourcedField[datetime].
 
    Replaces:
      enforce_submitted_date()          (mode="before")
      rescue_date()                     (mode="after")  — both on submitted_date
      rescue_start_date()               (mode="before") — on started_date
      rescue_completed_date()           (mode="before") — on completed_date
      strip_started_datetime_string()   (mode="after")  — on started_date
      strip_completed_datetime_string() (mode="after")  — on completed_date
 
    The RSL-plate-number suffix stripping (r"(_|-)\d(R\d)?$") that lives
    inside strip_started_datetime_string is preserved here via the regex
    pre-clean step.
    """
    if isinstance(raw, SourcedField):
        # If already a SourcedField, just ensure the inner value is a datetime.
        raw = SourcedField.from_raw(raw)
        raw_value = raw.value
        was_missing = raw.missing
    elif isinstance(raw, dict) and "value" in raw:
        raw_value = raw["value"]
        was_missing = raw.get("missing", True)
    else:
        raw_value = raw
        was_missing = raw is None
 
    coerced: datetime | None = None
 
    match raw_value:
        case datetime():
            coerced = raw_value
        case date():
            coerced = datetime.combine(raw_value, datetime.min.time())
        case int():
            # Excel ordinal date
            coerced = datetime.fromordinal(datetime(1900, 1, 1).toordinal() + raw_value - 2)
        case str():
            # Strip RSL plate suffix before parsing (e.g. "2024-01-01-1" → "2024-01-01")
            cleaned = re.sub(r"(_|-)\d(R\d)?$", "", raw_value)
            for attempt in (cleaned, cleaned.replace("-", "")):
                try:
                    coerced = parse(attempt)
                    was_missing = True   # derived from string, treat as generated
                    break
                except (ParserError, ValueError):
                    continue
        case None:
            pass
        case _:
            logger.warning(f"_coerce_datetime_field: unmatched type {type(raw_value)!r}")
 
    if coerced is None:
        coerced = fallback
        was_missing = True
 
    return SourcedField(value=coerced, missing=was_missing)
 
 
def _coerce_int_field(raw: Any) -> SourcedField[int]:
    """
    Coerce a raw value to SourcedField[int].
 
    Replaces:
      enforce_sample_count()  (mode="before") — wraps into dict
      enforce_integer()       (mode="after")  — coerces value to int
      rescue_run_cost()                       — on run_cost (float variant)
    """
    if isinstance(raw, SourcedField):
        inner = raw.value
        missing = raw.missing
    elif isinstance(raw, dict) and "value" in raw:
        inner = raw["value"]
        missing = raw.get("missing", True)
    elif raw is None:
        return SourcedField(value=0, missing=True)
    else:
        inner = raw
        missing = False
 
    if not inner:
        inner = 0
    try:
        inner = int(inner)
    except (ValueError, TypeError) as e:
        raise TypeError(f"Expected integer, got {inner!r}: {e}") from e 
    return SourcedField(value=inner, missing=missing)


class RelationshipField:
    """
    Marker placed in Annotated[..., RelationshipField()] to tag a Pydantic
    field as representing a SQLAlchemy relationship rather than a column.
 
    Optional `uselist` mirrors the SQLAlchemy relationship parameter:
      uselist=True  → one-to-many  (the field is a list)
      uselist=False → many-to-one / one-to-one  (the field is a scalar)
 
    Usage
    -----
    from typing import Annotated
    from pydantic import Field
 
    class PydReagent(PydAbstract):
        reagentrole: Annotated[PydReagentRole | None, RelationshipField(uselist=False)] = Field(default=None)
        reagentlot:  Annotated[List[PydReagentLot], RelationshipField(uselist=True)]    = Field(default_factory=list)
    """
 
    def __init__(self, uselist: bool = True):
        self.uselist = uselist
 
    def __repr__(self) -> str:
        return f"RelationshipField(uselist={self.uselist})"


def _get_relationship_marker(field_info: FieldInfo) -> RelationshipField | None:
    """
    Return the RelationshipField marker from a FieldInfo's Annotated metadata,
    or None if the field is not tagged as a relationship.
 
    Works with both forms:
      Annotated[SomeType, RelationshipField()]
      Annotated[SomeType | None, RelationshipField()]
    """
    annotation = field_info.annotation
    # Unwrap Optional / Union to find the Annotated layer
    if get_origin(annotation) is Annotated:
        for meta in get_args(annotation)[1:]:
            if isinstance(meta, RelationshipField):
                return meta
    # Also check metadata stored directly on the FieldInfo (Pydantic v2
    # moves Annotated extras into field_info.metadata)
    for meta in field_info.metadata:
        if isinstance(meta, RelationshipField):
            return meta
    return None


class PydBaseClass(BaseModel):#, validate_assignment=True):

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
        validate_assignment=True,
        json_schema_extra= {
            "key_value_order": [],
            "excluded": ["excluded"],
            "renderclass": "details"
        }
    )

    sql_instance: BaseClass | None = Field(default=None, repr=False, exclude=True)

    @field_validator("sql_instance", mode="before")
    @classmethod
    def validate_sql_instance(cls, value):
        # Accept an existing instance; do not create one speculatively.
        if value is not None and not isinstance(value, BaseClass):
            logger.warning(f"sql_instance for {cls.__name__} is not a BaseClass; ignoring.")
            return None
        return value

    def __repr_args__(self) -> core_schema.ReprArgs:
        # Get the default repr arguments first
        # This iterates over defined fields and computed fields
        args = super().__repr_args__()
        # Filter out any arguments that correspond to extra fields
        # The 'name' attribute of ReprArgsElement is the field name
        extra_fields = getattr(self, '__pydantic_extra__', {})
        return [arg for arg in args if arg[0] not in extra_fields]

    sql_instance: BaseClass | None = Field(default=None, validate_default=True, repr=False)
    new: bool = Field(default=True, repr=False, validate_default=True)
    
    @classproperty
    def aliases(cls) -> List[str]:
        """
        Gets other names this class may be known by, for lookup purposes.
        """
        return [cls.__name__.replace("Pyd", "").lower()]

    @classproperty
    def _sql_name(cls) -> str:
        """
        Gets the name of the corresponding SQLAlchemy class, for lookup purposes.
        """
        return cls.__name__.replace("Pyd", "")

    @classproperty
    def _sql_class(cls) -> models.BaseClass:
        # Lazy import here to reduce the chance of circular-import issues
        # (models may import pydant elsewhere during package import).
        
        try:
            return getattr(models, cls._sql_name)
        except AttributeError as e:
            # Provide a clearer error message listing available top-level
            # model names to help debugging name mismatches / import order.
            available = [n for n in dir(models) if not n.startswith("_")]
            raise AttributeError(
                f"SQL model '{cls._sql_name}' not found on backend.db.models. "
                f"Available top-level attributes: {available}") from e
        
    @field_validator("sql_instance", mode="before")
    @classmethod
    def generate_blank_sql_instance(cls, value):
        if value is None:
            value = cls._sql_class()
        return value
    
    @field_validator('*', mode="before")
    @classmethod
    def use_default_if_none(cls, v, info: ValidationInfo):
        # Skip validation for specific fields
        if info.field_name in {"sql_instance"}:
            return v
        if v is None:
            # Dynamically fetch the default value for the field being validated
            field = cls.model_fields.get(info.field_name)
            if field and field.default is not ...: # Check if a default exists
                return field.get_default()
        return v
    
    @model_validator(mode="before")
    @classmethod
    def prevalidate(cls, data: dict) -> dict:
        """Strip leading underscores from keys that correspond to SQLAlchemy attributes."""
        if not isinstance(data, dict):
            return data
        # Use sql_inspect to include inherited attributes
        try:
            from sqlalchemy import inspect as sql_inspect
            mapper = sql_inspect(cls._sql_class)
            sql_field_names = {attr.key for attr in mapper.column_attrs} | \
                            {rel.key for rel in mapper.relationships}
        except Exception:
            sql_field_names = set()
        output = {}
        for key, value in data.items():
            stripped = key.lstrip("_")   # strip leading underscores only
            if stripped in sql_field_names and key != stripped:
                output[stripped] = value
            else:
                output[key] = value
        return output

    @model_validator(mode='after')
    def validate_model(self):
        for key, value in self.model_extra.items():
            if key in self._sql_class.timestamps:
                if isinstance(value, str):
                    # Before: self.__setattr__(key, ...)
                    object.__setattr__(self, key, datetime.strptime(value, "%Y-%m-%d"))
            if key == "row" and isinstance(value, str):
                if value.lower() in string.ascii_lowercase[0:8]:
                    try:
                        value = row_keys[value]
                    except KeyError:
                        pass
                object.__setattr__(self, key, value)
        return self

    def filter_field(self, key: str, value: Any | None = None) -> Any:
        """
        Attempts to get value from field dictionary

        Args:
            key (str): name of the field of interest

        Returns:
            Any (): Value found.
        """
        if value is None:
            value = getattr(self, key)
        if isinstance(value, SourcedField):
            return value.value
        elif isinstance(value, dict):
            try:
                return value['value']
            except KeyError as e:
                return None
        return value

    def improved_dict_expand_fields(self, fields: List[str | dict] | dict | str, **kwargs) -> dict:
        """
        Expands fields in the improved dict for use in forms.

        Args:
            fields (List[str] | List[dict]): List[str] is a flat expansion, List[dict] expands recursively.

        Returns:
            dict: Expanded dictionary.
        """
        # Allow callers to pass a single dict or string instead of a list
        condense = kwargs.get("condense", False)
        if isinstance(fields, dict):
            fields = [fields]
        elif isinstance(fields, str):
            fields = [fields]
        if len(fields) == 0:
            fields = self.improved_dict.keys()
        dict_ = self.improved_dict
        for field in fields:
            match field:
                case str():
                    key = field
                    try:
                        value = getattr(self.sql_instance, key)
                    except AttributeError as e:
                        logger.error(f"Skipping {key} in {self.sql_instance} due to {e}")
                        continue
                    match value:
                        case InstrumentedAttribute():
                            output = self.filter_field(key)   # or self.filter_field(key)
                        case _AssociationList():
                            output = []
                            for item in value.col:
                                dicto: dict = item.to_pydantic().improved_dict
                                target = getattr(item, key)
                                new = target.to_pydantic().improved_dict
                                new.update({k:v for k, v in dicto.items() if k !="name"})
                                if new['name'] not in [thing['name'] for thing in output]:
                                    output.append(new)
                        case InstrumentedList():
                            output = [item.to_pydantic().improved_dict for item in value]
                        case _ if issubclass(value.__class__, models.BaseClass):
                            output = value.to_pydantic().improved_dict
                        case _:
                            logger.warning(f"Got unmatched type for {field} during expand_fields: {value.__class__.__name__}")
                            continue
                case dict():
                    key = list(field.keys())[0]
                    new_fields = list(field.values())[0]
                    
                    value = getattr(self.sql_instance, key)
                    match value:
                        case _AssociationList():
                            output = [item.to_pydantic().improved_dict_expand_fields(new_fields, **kwargs) for item in value]
                        case InstrumentedList():
                            output = [item.to_pydantic().improved_dict_expand_fields(new_fields, **kwargs) for item in value]
                        case _ if issubclass(value.__class__, models.BaseClass):
                            output = value.to_pydantic().improved_dict_expand_fields(new_fields, **kwargs)
                        case _:
                            logger.warning(f"Got unmatched type during expand_fields: {value.__class__.__name__}")
                            continue
                case _:
                    continue
            dict_[key] = output
        return dict_
    
    @property
    def improved_dict(self) -> dict:
        """
        Adds model_extra to fields.

        Args:
            dictionaries (bool, optional): Are dictionaries expected as input? i.e. Should key['value'] be retrieved. Defaults to True.

        Returns:
            dict: This instance as a dictionary
        """
        fields = list(self.__class__.model_fields.keys()) + list(self.model_extra.keys())
        output = {k: self.filter_field(k) for k in fields if k not in ["sql_instance", "new"]}
        
        if "misc_info" in output.keys():
            iterator = output['misc_info'] or {}
            for k, v in iterator.items():
                if "sql_instance" in k:
                    continue
                if k.count(" ") > 3:
                    continue
                if k not in output.keys():
                    output[k] = v
            del output['misc_info']
        if "name" not in output.keys():
            try:
                output['name'] = self.sql_instance.name
            except AttributeError:
                logger.error(f"Cannot set name for {self.__class__.__name__}")
        output['excluded'] = self.model_config.get("json_schema_extra", {}).get("excluded", [])
        
        return output
    
    @property
    def _sql_lookup_kwargs(self):
        list_ = {item for item in inspect.signature(self._sql_class.query).parameters.keys() if item in [attr for attr in dir(self) if not attr.startswith("_")]}
        return {item: self.__getattribute__(item) for item in list_}

    def to_sql(self, update: bool = True):
        if self.sql_instance is None:
            # Resolve via query_or_create so we reuse existing DB rows
            instance, _ = self._sql_class.query_or_create(**self._sql_lookup_kwargs())
            self.sql_instance = instance
        from sqlalchemy.ext.hybrid import hybrid_property
        from sqlalchemy.orm.properties import ColumnProperty
 
        if not update:
            return self.sql_instance
 
        rel_fields   = self.__class__._relationship_fields   # {name: RelationshipField}
        col_fields   = self.__class__._column_fields         # [name, ...]
        improved     = self.improved_dict
 
        # ── Column fields ────────────────────────────────────────────────────
        
        for k in col_fields:
            v = improved.get(k)
            if v is None:
                continue
            class_attr = getattr(self._sql_class, k, None)
            if class_attr is None:
                continue
            if hasattr(class_attr, "property"):
                class_attr = class_attr.property
            match class_attr:
                case hybrid_property():
                    continue
                case ColumnProperty():
                    if getattr(self.sql_instance, k) != v:
                        try:
                            setattr(self.sql_instance, k, v)
                        except AttributeError as e:
                            logger.error(f"Could not set {k} on {self.sql_instance}: {e}")
                case _:
                    pass
 
        # ── Relationship fields ───────────────────────────────────────────────
        # Subclasses previously overrode to_sql() solely to add these lines.
        # With the tag, the base class handles them, and overrides are only
        # needed for genuinely bespoke logic.
        for k, marker in rel_fields.items():
            v = getattr(self, k, None)
            if v is None:
                continue
            if marker.uselist and isinstance(v, list) and len(v) == 0:
                # Preserve the "don't clear existing associations" guard
                continue
            try:
                setattr(self.sql_instance, k, v)
            except Exception as e:
                logger.error(f"Could not set relationship {k} on {self.sql_instance}: {e}")
 
        for k, v in self.model_extra.items():
            self.sql_instance._misc_info[k] = models.BaseClass.sanitize_obj_for_json(v)
 
        return self.sql_instance
 
 
# ─────────────────────────────────────────────────────────────────────────────

    
    @property
    def fields(self) -> list:
        """
        Retrieves list of field names.

        Returns:
            list: List of field names.
        """
        output = []
        for k, v in self.improved_dict.items():
            match v:
                case str() | int() | float() | datetime() | date():
                    pass
                case dict():
                    pass
                case list():
                    pass
                case _ if issubclass(v.__class__, PydBaseClass):
                    pass
                case _:
                    continue
            output.append(k)
        return list(set(output))
    
    @classproperty
    def described_fields(cls) -> List[str]:
        """
        Gets all fields that have a description.

        Returns:
            List[str]: List of field names.
        """
        return [k for k, v in cls.model_fields.items() if v.description]
    
    @classproperty
    def sql_classes(cls) -> List[str]:
        """
        Gets all fields associated with sqlalchemy objects.

        Returns:
            List[str]: List of lowercase object names.
        """
        return [class_[0].lower() for class_ in inspect.getmembers(models) if isinstance(class_[1], DeclarativeMeta) and issubclass(class_[1], models.BaseClass)]
    
    @classmethod
    def determine_field_type(cls, field: str, is_new: bool = False) -> str | None:
        """
        Determines which type of field to use in the form.

        Args:
            field (str): Field name

        Returns:
            str: Type name
        """        
        try:
            type_ = getattr(cls._sql_class, field.lower().strip("_"))
        except AttributeError:
            return
        type_name = type_.__class__.__name__
        match type_name:
            case "hybrid_propertyProxy":
                try:
                    type_ = getattr(cls._sql_class, type_.property.key)
                except AttributeError:
                    try:
                        type_ = getattr(cls._sql_class, f"_{field}") # Dicey workaround for hybrid_property with underscore
                    except AttributeError as e:
                        type_ = getattr(cls._sql_class, field) # Dicey workaround for hybrid_property with underscore
                type_name = type_.__class__.__name__
                if type_name == "InstrumentedAttribute":
                    type_ = type_.property
                    type_name = type_.__class__.__name__
                    if type_name == "_RelationshipDeclared":
                        if type_.uselist:
                            type_name = "RelationshipList"
                        else:
                            type_name = "RelationshipScalar"
                    else:
                        try:
                            annotation = cls.model_fields[field].annotation
                        except KeyError:
                            return "Skipped"
                        if isinstance(annotation, UnionType):
                            type_name = annotation.__args__[0].__name__
                        else:
                            try:
                                type_name = annotation.__name__
                            except AttributeError:
                                logger.error(f"Could not determine type name for field {field} on {cls.__name__} {cls.model_fields[field].annotation}")
                                type_name = "Skipped"
                            except KeyError:
                                type_name = "Skipped"
                if type_name == "ObjectAssociationProxyInstance":
                    if is_new:
                        logger.warning(f"AssociationProxyInstance field {field} on {cls.__name__} is being treated as Skipped for new instance.")
                        type_name = "Skipped"
            case "ObjectAssociationProxyInstance":
                if is_new:
                    logger.warning(f"AssociationProxyInstance field {field} on {cls.__name__} is being treated as Skipped for new instance.")
                    type_name = "Skipped"
            case "InstrumentedAttribute":
                try:
                    IA = cls.model_fields[field].annotation
                except KeyError:
                    return "Skipped"
                if isinstance(IA, UnionType):
                    IA = IA.__args__[0]
                try:
                    type_name = IA.__name__
                except AttributeError:
                    logger.warning(f"Could not determine type name for field {field} on {cls.__name__} with annotation {cls.model_fields[field].annotation}")
                    type_name = "Skipped"
            case _:
                logger.warning(f"Got unmatched type: {type_name} for field {field}.")
        return type_name
    
    # Add this new helper method to PydBaseClass (place it before the form_dictionary property)
    def _compute_excluded_items(self, field: str) -> List[str]:
        """
        Determines which sub-items are to be excluded from a form dictionary.

        Args:
            field (str): Name of field to be considered.

        Returns:
            List[str]: List of sub-items. 

        """
        model: models.BaseClass = models.BaseClass.find_subclasses(class_alias=field.lower().strip("_"))
        data = self.model_dump()
        excluded = []
        try:
            rel_attr = self.__class__.__name__.lower().replace("pyd", "")
            raw_field_values = data.get(field, [])
            if isinstance(raw_field_values, list):
                data_names = {v.get("name") if isinstance(v, dict) and "name" in v else v for v in raw_field_values}
            else:
                data_names = {raw_field_values}
            for item in model.query():
                try:
                    related = getattr(item, rel_attr)
                except AttributeError:
                    logger.error(f"Item {item} has no attribute {rel_attr}; skipping")
                    continue
                related_iter = related if isinstance(related, list) else [related]
                related_names = set()
                for r in related_iter:
                    if hasattr(r, "name"):
                        related_names.add(r.name)
                    elif isinstance(r, dict) and "name" in r:
                        related_names.add(r["name"])
                # Some PydBaseClass instances may not have a 'name' attribute
                # Use getattr to safely retrieve self's name, and only consider
                # the relationship check if a name exists on self. If self has
                # no name, rely solely on whether the item is present in the
                # provided data_names when deciding exclusion.
                self_name = getattr(self, "name", None)
                already_related_to_self = (self_name is not None and self_name in related_names)
                if (not already_related_to_self) and (item.name not in data_names):
                    excluded.append(item.name)
        except AttributeError as e:
            logger.warning(f"Could not get excluded items for field {field} due to {e}. Trying sql based.")
        return excluded

    @property
    def form_dictionary(self) -> Generator[dict, None, None]:
        """
        Generates dictionaries to be used to fill jinja2 html form.

        Returns:
            Generator[dict, None, None]: Generator of Dict[field name, type name, value, tooltip text, excluded fields, sql object type name]
        
        """
        if self.__class__.__name__ == "PydBaseClass":
            raise NotImplementedError("Must be used in subclass only")
        data = self.model_dump()
        for field in self.described_fields:
            is_new = getattr(self, "new", False)
            type_name = self.determine_field_type(field, is_new=is_new)
            if field.lower().strip("_") in self.sql_classes:
                excluded = self._compute_excluded_items(field=field)
            else:
                excluded = None
            tooltip = self.__class__.model_fields[field].description
            value = data.get(field, None)
            if isinstance(value, list):
                value = [value['name'] if isinstance(value, dict) and 'name' in value.keys() else value for value in value]
            yield dict(field=field, type=type_name.upper(), value=value, tooltip=tooltip, excluded=excluded, object_type=self._sql_name.lower())

    @classmethod
    def get_association_class(cls, field: str) -> PydBaseClass | None:
        """
        Gets Pydantic model class associated with a field..

        Args:
            field (str): Name of field to be considered.

        Returns:
            PydBaseClass: Class of interest.
        """
        lookup_name = cls.__name__.replace("Pyd", "").lower()
        merged = f"{lookup_name}{field.lower().strip('_')}association"
        subclass = next((class_ for class_ in PydBaseClass.subclasses if merged in class_.aliases), None)
        if subclass is None:
            logger.error(f"Could not find association class for merged alias: {merged}")
        return subclass

    @property
    def html_form(self) -> str:
        """
        Renders instance data through a jinja2 template to an html str.

        Returns:
            str: Rendered HTML string.
        """
        if "association" in self.__class__.__name__.lower():
            association = True
        else:
            association = False
        env = jinja_template_loading()
        template = env.get_template("managers/manager_form.html")
        html = template.render(object=self.form_dictionary, association=association, class_name=self.__class__.__name__)
        return html
            
    @classmethod
    def manage(cls, parent=None) -> QDialog:
        """
        Creates a manager dialog for this class.

        Args:
            parent: The parent widget for this Dialog
        """
        from frontend.widgets.omni_manager_pydant import OmniManager
        widget = OmniManager(parent=parent, object_type=cls)
        widget.exec()
        return widget

    @classproperty
    def subclasses(cls) -> Generator[type[PydBaseClass], None, None]:
        def _walk(class_):
            for sub in class_.__subclasses__():
                yield sub
                yield from _walk(sub)
        yield from _walk(PydBaseClass)   

    def add_relationship(self, field: str, value: str, data: dict | None = None):
        """
        Adds a relationship to a list field.

        Args:
            field (str): Field name
            value (str): Value to add to the relationship.
        """
        try:
            current = self.__getattribute__(field)
        except AttributeError:
            current = []
        if data is not None:
            value = dict(name=value, **data)
        if not isinstance(current, list):
            logger.error(f"Field {field} is not a list relationship.")
            return
        if value in current:
            logger.warning(f"Value {value} already in field {field}.")
            return
        current.append(value)
        self.__setattr__(field, current)

    def remove_relationship(self, field: str, value: str):
        """
        Removes a relationship from a list field.

        Args:
            field (str): Field name
            value (str): The value to remove from the relationship.
        """
        try:
            current = self.__getattribute__(field)
        except AttributeError:
            logger.error(f"Couldn't find attribute {field} to remove {value} from.")
            current = []
        if not isinstance(current, list):
            logger.error(f"Field {field} is not a list relationship.")
            return
        new_list = []
        for item in current:
            if isinstance(item, str) and item == value:
                continue  # Skip if it's the target string
            elif isinstance(item, dict) and value in item.values():
                continue  # Skip if dict contains the target value
            new_list.append(item)
        self.__setattr__(field, new_list)

    def update_instrumentedattribute(self, key, value):
        """
        Updates all instrumented attributes to match the current state of the pydantic model.
        """
        self.__setattr__(key, value)

    def revalidate(self):
        """
        Revalidates the model.
        """
        try:
            new = self.model_validate(self.__dict__)
            self.__dict__.update(new.__dict__)
        except ValidationError as e:
            raise e
        
    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Template: Template to be rendered
        """
        env = jinja_template_loading()
        temp_name = f"{cls._sql_name.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            try:
                template = env.get_template(f"{cls.class_config.renderclass}_details.html")
            except TemplateNotFound:
                template = env.get_template("details.html")
        return template
        
    def to_html(self, css_in: List[str| Path] | str = [], js_in: List[str | Path] | str = [],
                            **kwargs) -> str:
        details_name = self.details_template.name.lower().replace("_details.html", "")
        details = {details_name: self.clean_details_for_render(self.improved_dict), **kwargs}
        logger.debug(f"Excluded: {details.get('excluded', [])}")
        if isinstance(css_in, str | Path):
            css_in = [css_in]
        env = jinja_template_loading()
        html_folder = Path(env.loader.__getattribute__("searchpath")[0])
        css_in = ["styles", self._sql_name.lower()] + css_in
        css_in = [html_folder.joinpath("css", f"{c}.css") for c in css_in]
        if isinstance(js_in, str | Path):
            js_in = [js_in]
        js_in = ["details", self._sql_name.lower()] + js_in
        js_in = [html_folder.joinpath("js", f"{j}.js") for j in js_in]
        css_out = []
        for css in css_in:
            if not css.exists():
                logger.warning(f"CSS file {css} does not exist; skipping.")
                continue
            with open(css, "r") as f:
                css_out.append(f.read())
        js_out = []
        for js in js_in:
            if not js.exists():
                logger.warning(f"JS file {js} does not exist; skipping.")
                continue
            with open(js, "r") as f:
                js_out.append(f.read())
        return self.details_template.render(css=css_out, js=js_out, **details)
    
    @classmethod
    def clean_details_for_render(cls, dictionary: dict) -> dict:
        """
        Cleans dictionary for rendering on a template.

        Args:
            dictionary (dict): input dictionary

        Returns:
            dict: cleaned dictionary
        """
        from backend.db.models import BaseClass
        output = {}
        for k, value in dictionary.items():
            match value:
                case SourcedField():
                    # Unwrap directly — no key guessing needed
                    value = value.value
                    if value is None:
                        continue
                case datetime() | date():
                    value = value.strftime("%Y-%m-%d")

                case bytes():
                    continue
                case dict():
                    try:
                        value = value['value']
                    except KeyError:
                        try:
                            value = value['name']
                        except KeyError:
                            if k == "_misc_info" or k == "misc_info":
                                value = value
                            else:
                                continue
                case _ if issubclass(value.__class__, BaseClass): 
                    try:
                        value = value.name
                    except AttributeError:
                        logger.error(f"Couldn't get name for BaseClass subclase {type(value)}")
                        continue
                case _ if issubclass(value.__class__, PydBaseClass):
                    try:
                        value = value.name
                    except AttributeError:
                        logger.error(f"Couldn't get name for PydBaseClass subclase {type(value)}")
                        continue
                case str() | int() | float() | list():
                    pass
                case _:
                    logger.warning(f"Unmatched type for {k}: {type(value)}")
                    try:
                        value = value.name
                    except AttributeError:
                        continue
            output[k] = value
        return output

    @classproperty
    def class_config(cls) -> DotDict:

        """
        Gets class configuration for use in templates.

        Returns:
            DotDict: Class configuration.
        """
        config = cls.model_config.get("json_schema_extra", {})
        return DotDict(config)

    @classproperty
    def _relationship_fields(cls) -> dict[str, RelationshipField]:
        """
        Return a dict of {field_name: RelationshipField} for every field
        tagged with RelationshipField in this class.
 
        Example
        -------
        PydReagent.relationship_fields
        # {'reagentrole': RelationshipField(uselist=False),
        #  'reagentlot':  RelationshipField(uselist=True)}
        """
        result = {}
        for name, field_info in cls.model_fields.items():
            marker = _get_relationship_marker(field_info)
            if marker is not None:
                result[name] = marker
        return result
 
    @classproperty
    def _column_fields(cls) -> list[str]:
        """
        Return field names that are NOT tagged as relationships.
        Complements relationship_fields.
        """
        rel = cls._relationship_fields
        return [name for name in cls.model_fields if name not in rel]


class PydAbstract(PydBaseClass):

    @classmethod
    def get_managables(cls) -> Generator[PydBaseClass, None, None]:
        """
        Generates list of all subclasses that can be managed.

        Returns:
            Generator[PydBaseClass, None, None]: all subclasses with described fields.
        """
        for class_ in PydAbstract.__subclasses__():
            if "association" in class_.__name__.lower():
                continue
            if len(class_.described_fields) > 0:
                yield class_


class PydConcrete(PydBaseClass):

    @classmethod
    def get_managables(cls):
        """
        Generates list of all subclasses that can be managed.

        Returns:
            Generator[PydBaseClass, None, None]: all subclasses with described fields.
        """
        for class_ in PydConcrete.__subclasses__():
            if "association" in class_.__name__.lower():
                continue
            if len(class_.described_fields) > 0:
                yield class_
        

from .abstract import (
    PydEquipmentRole, 
    PydProcess, 
    PydReagent, 
    PydReagentRole, 
    PydTips, 
    PydProcedureType, 
    PydResultsType, 
    PydSubmissionType,
    PydEquipmentRoleEquipmentAssociation,
    PydProcedureTypeEquipmentRoleAssociation,
    PydProcedureTypeReagentRoleAssociation,
    PydReagentRoleReagentAssociation
)

from .concrete import (
    ParserError,
    PydEquipment, 
    PydClientLab, 
    PydClientSubmission, 
    PydContact, 
    PydProcedure, 
    PydProcessVersion, 
    PydResults, 
    PydRun,
    PydReagentLot,
    PydSample,
    PydTipsLot,
    PydDiscount,
    PydProcedureEquipmentAssociation,
    PydProcedureReagentLotAssociation,
    PydProcedureSampleAssociation,
    PydClientSubmissionSampleAssociation
)