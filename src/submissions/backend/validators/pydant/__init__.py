"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
from copy import deepcopy
import logging, sys, string, inspect
from pprint import pformat
from pydantic import BaseModel, ValidationError, model_validator, ConfigDict
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Generator, List, Tuple
from tools import classproperty, jinja_template_loading, row_keys
from backend.db import models
# from backend.db.models import *
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.ext.associationproxy import _AssociationList


logger = logging.getLogger(f"submission.{__name__}")


class PydBaseClass(BaseModel):#, validate_assignment=True):

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
    )

    # _sql_object: ClassVar = None
    key_value_order: ClassVar[List] = []
    non_expandables: ClassVar[List] = ["procedure"]

    @classproperty
    def aliases(cls) -> str:
        return [cls.__name__.replace("Pyd", "").lower()]

    @classproperty
    def _sql_name(cls) -> str:
        return cls.__name__.replace("Pyd", "")

    @classproperty
    def _sql_class(cls) -> models.BaseClass:
        # Lazy import here to reduce the chance of circular-import issues
        # (models may import pydant elsewhere during package import).
        try:
            from backend.db import models as _models
        except Exception:
            # If import fails, re-raise with context so caller can see
            raise
        try:
            return getattr(_models, cls._sql_name)
        except AttributeError as e:
            # Provide a clearer error message listing available top-level
            # model names to help debugging name mismatches / import order.
            available = [n for n in dir(_models) if not n.startswith("_")]
            raise AttributeError(
                f"SQL model '{cls._sql_name}' not found on backend.db.models. "
                f"Available top-level attributes: {available}") from e
        
    @property
    def _sql_instance(self) -> models.BaseClass:
        assert hasattr(self, "_sql_class")
        instance = self._sql_class.query_or_create(name=self.name)
        if isinstance(instance, tuple):
            instance = instance[0]
        return instance
    
    @model_validator(mode="before")
    @classmethod
    def prevalidate(cls, data):
        sql_fields = [k for k, v in cls._sql_class.__dict__.items() if isinstance(v, InstrumentedAttribute)]
        output = {}
        match data:
            case dict():
                try:
                    items = data.items()
                except AttributeError as e:
                    logger.error(f"Could not prevalidate {cls.__name__} due to {e} for {pformat(data)}")
                    return data
                for key, value in items:
                    new_key = key.replace("_", "")
                    if new_key in sql_fields:
                        output[new_key] = value
                    else:
                        output[key] = value
            case _:
                output = data
        return output

    @model_validator(mode='after')
    @classmethod
    def validate_model(cls, data):
        for key, value in data.model_extra.items():
            # NOTE: make sure all date variables are date objects.
            if key in cls._sql_class.timestamps:
                if isinstance(value, str):
                    data.__setattr__(key, datetime.strptime(value, "%Y-%m-%d"))
            # NOTE: translate row letter to an integer
            if key == "row" and isinstance(value, str):
                if value.lower() in string.ascii_lowercase[0:8]:
                    try:
                        value = row_keys[value]
                    except KeyError:
                        value = value
                data.__setattr__(key, value)
        return data

    def filter_field(self, key: str) -> Any:
        """
        Attempts to get value from field dictionary

        Args:
            key (str): name of the field of interest

        Returns:
            Any (): Value found.
        """
        item = getattr(self, key)
        match item:
            case dict():
                try:
                    item = item['value']
                except KeyError:
                    # logger.error(f"Couldn't get dict value: {item}")
                    pass
                    # logger.error(f"Couldn't get dict value: {item}")
                    pass
            case _:
                pass
        return item

    def improved_dict_expand_fields(self, fields: List[str] | List[dict]):
        if len(fields) == 0:
            fields = self.improved_dict.keys()
        print(f"Fields:\n{pformat(fields)}")
        instance = self._sql_instance
        dicto = self.improved_dict
        for field in fields:
            match field:
                case str():
                    key = field
                    try:
                        value = getattr(instance, key)
                    except AttributeError:
                        logger.error(f"Skipping {key}")
                        continue
                    match value:
                        case InstrumentedList():
                            print(f"Instrumented: {key}: {value}")
                            output = [item.to_pydantic().improved_dict for item in value]
                        case _AssociationList():
                            print(f"Association: {key}: {value}")
                            output = [item.to_pydantic().improved_dict for item in value.col]
                        case _:
                            print(f"Unmatched type {type(value)}")
                            continue
                case dict():
                    key = list(field.keys())[0]
                    new_fields = list(field.values())[0]
                    try:
                        value = getattr(instance, key)
                    except AttributeError:
                        logger.error(f"Skipping {key}")
                        continue
                    match value:
                        case _AssociationList() | InstrumentedList():
                            output = [item.to_pydantic().improved_dict_expand_fields(new_fields) for item in value]
                        case _:
                            print(f"Unmatched type {type(value)}")
                            continue
            dicto[key] = output
        return dicto
    
    @property
    def improved_dict(self) -> dict:
        """
        Adds model_extra to fields.

        Args:
            dictionaries (bool, optional): Are dictionaries expected as input? i.e. Should key['value'] be retrieved. Defaults to True.

        Returns:
            dict: This instance as a dictionary
        """
        # self.revalidate()
        fields = list(self.__class__.model_fields.keys()) + list(self.model_extra.keys())
        output = {k: self.filter_field(k) for k in fields}
        if "misc_info" in output.keys():
            for k, v in output['misc_info'].items():
                if k not in output.keys():
                    output[k] = v
            del output['misc_info']
        if "name" not in output.keys():
            try:
                output['name'] = self._sql_instance.name
            except AttributeError:
                logger.error(f"Cannot set name for {self.__class__.__name__}")
        return output

    def to_sql(self):
        # Prevent accidental clearing of existing SQL relationship lists:
        # Many SQLAlchemy relationship setters in this codebase treat an
        # assignment of an empty list as an instruction to clear that
        # relationship (often resulting in cascade delete-orphan).
        # When converting a Pydantic model to SQL, an empty list usually
        # means "no change" rather than "clear all associations". To be
        # conservative, don't pass empty lists through to query_or_create
        # so we don't unintentionally wipe related association rows.
        sanitized_dicto = {k: v for k, v in self.improved_dict.items() if not (isinstance(v, list) and len(v) == 0)}
        sql, _ = self._sql_class.query_or_create(**sanitized_dicto)
        return sql

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
                    output.append(k)
                case x if issubclass(v.__class__, PydBaseClass):
                    output.append(k)
                case _:
                    continue
        return list(set(output))
    
    @classproperty
    def described_fields(cls) -> List[str]:
        return [k for k, v in cls.model_fields.items() if v.description]
    
    @classproperty
    def sql_classes(cls) -> List[str]:
        return [class_[0].lower() for class_ in inspect.getmembers(models) if isinstance(class_[1], DeclarativeMeta) and issubclass(class_[1], models.BaseClass)]
    
    @classmethod
    def determine_field_type(cls, field: str, is_new: bool = False) -> str:
        """Determines which type of field to use in the form.

        Args:
            field (str): Field name

        Returns:
            str: Type name
        """        
        type_ = getattr(cls._sql_class, field.lower().strip("_"))
        type_name = type_.__class__.__name__
        logger.debug(f"Type name for {field}: {type_name}")
        match type_name:
            case "hybrid_propertyProxy":
                try:
                    type_ = getattr(cls._sql_class, type_.property.key)
                except AttributeError:
                    type_ = getattr(cls._sql_class, f"_{field}") # Dicey workaround for hybrid_property with underscore
                type_name = type_.__class__.__name__
                logger.debug(f"New type_name for hybrid_propertyProxy: {type_name}")
                if type_name == "InstrumentedAttribute":
                    type_ = type_.property
                    type_name = type_.__class__.__name__
                    logger.debug(f"New type_name for hybrid_propertyProxy, InstrumentedAttribute: {type_name}")
                    if type_name == "_RelationshipDeclared":
                        if type_.uselist:
                            type_name = "RelationshipList"
                        else:
                            type_name = "RelationshipScalar"
                    else:
                        type_name = cls.model_fields[field].annotation.__name__
                if type_name == "ObjectAssociationProxyInstance":
                    if is_new:
                        type_name = "Skipped"
            case "ObjectAssociationProxyInstance":
                if is_new:
                    type_name = "Skipped"
            case "InstrumentedAttribute":
                type_name = cls.model_fields[field].annotation.__name__
            case _:
                logger.warning(f"Got unmatched type: {type_name} for field {field}.")
        return type_name
    
    # Add this new helper method to PydBaseClass (place it before the form_dictionary property)
    def _compute_excluded_items(self, field: str) -> list:
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
            logger.debug(f"Querying with model {model}")
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
            value = data[field]
            if isinstance(value, list):
                value = [value['name'] if isinstance(value, dict) and 'name' in value.keys() else value for value in value]
            yield dict(field=field, type=type_name.upper(), value=value, tooltip=tooltip, excluded=excluded)

    @classmethod
    def get_association_class(cls, field: str):
        lookup_name = cls.__name__.replace("Pyd", "").lower()
        merged = f"{lookup_name}{field.lower().strip('_')}association"
        # logger.debug(f"Looking for association class with merged alias: {merged}")
        subclass = next((class_ for class_ in PydBaseClass.get_subclasses() if merged in class_.aliases), None)
        if subclass is None:
            logger.error(f"Could not find association class for merged alias: {merged}")
        return subclass

    @property
    def html_form(self) -> str:
        if "association" in self.__class__.__name__.lower():
            association = True
        else:
            association = False
        env = jinja_template_loading()
        template = env.get_template("managers/manager_form.html")
        # logger.debug(f"Form dictionary: {pformat(list(self.form_dictionary))}")
        html = template.render(object=self.form_dictionary, association=association, class_name=self.__class__.__name__)
        return html
            
    @classmethod
    def manage(cls, parent=None):
        from frontend.widgets.omni_manager_pydant import OmniManager
        widget = OmniManager(parent=parent, object_type=cls)
        widget.exec()
        return widget

    @classmethod
    def get_subclasses(cls):
        for class_ in PydBaseClass.__subclasses__():
            for subclass in class_.__subclasses__():
                yield subclass

    def add_relationship(self, field: str, value: str, data: dict | None = None):
        """
        Adds a relationship to a list field.

        Args:
            field (str): Field name
            value (str): Value to add to the relationship.
        """
        current = self.__getattribute__(field)
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
        current = self.__getattribute__(field)
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


class PydAbstract(PydBaseClass):

    @classmethod
    def get_managables(cls):
        for class_ in PydAbstract.__subclasses__():
            if "association" in class_.__name__.lower():
                continue
            if len(class_.described_fields) > 0:
                yield class_


class PydConcrete(PydBaseClass):

    @classmethod
    def get_managables(cls):
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
    PydDiscount
    )