"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
import logging, sys, string, inspect
from pprint import pformat
from pydantic import BaseModel, ValidationError, model_validator, ConfigDict
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Generator, List, Tuple
from tools import classproperty, jinja_template_loading, row_keys
from backend.db import models
# from backend.db.models import *
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm import DeclarativeMeta


logger = logging.getLogger(f"submission.{__name__}")


class PydBaseClass(BaseModel):#, validate_assignment=True):

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
    )

    # _sql_object: ClassVar = None
    key_value_order: ClassVar[List] = []

    @classproperty
    def _sql_name(cls) -> str:
        return cls.__name__.replace("Pyd", "")

    @classproperty
    def _sql_object(cls):
        return getattr(models, cls._sql_name)

    @model_validator(mode="before")
    @classmethod
    def prevalidate(cls, data):
        sql_fields = [k for k, v in cls._sql_object.__dict__.items() if isinstance(v, InstrumentedAttribute)]
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
            if key in cls._sql_object.timestamps:
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
                    logger.error(f"Couldn't get dict value: {item}")
            case _:
                pass
        return item

    def improved_dict(self, dictionaries: bool = True) -> dict:
        """
        Adds model_extra to fields.

        Args:
            dictionaries (bool, optional): Are dictionaries expected as input? i.e. Should key['value'] be retrieved. Defaults to True.

        Returns:
            dict: This instance as a dictionary
        """
        self.revalidate()
        fields = list(self.__class__.model_fields.keys()) + list(self.model_extra.keys())
        if dictionaries:
            output = {k: getattr(self, k) for k in fields}
        else:
            output = {k: self.filter_field(k) for k in fields}
        if "misc_info" in output.keys():
            for k, v in output['misc_info'].items():
                if k not in output.keys():
                    output[k] = v
            del output['misc_info']
        return output

    def to_sql(self):
        dicto = self.improved_dict(dictionaries=False)
        sql, new = self._sql_object.query_or_create(**dicto)
        if new:
            logger.warning(f"Creating new {self._sql_object} with values:\n{pformat(dicto)}")
        return sql

    @property
    def fields(self) -> list:
        """
        Retrieves list of field names.

        Returns:
            list: List of field names.
        """
        output = []
        for k, v in self.improved_dict().items():
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
    def determine_field_type(cls, field: str) -> str:
        """Determines which type of field to use in the form.

        Args:
            field (str): Field name

        Returns:
            str: Type name
        """        
        type_ = getattr(cls._sql_object, field.lower().strip("_"))
        type_name = type_.__class__.__name__
        match type_name:
            case "hybrid_propertyProxy":
                try:
                    type_ = getattr(cls._sql_object, type_.property.key)
                except AttributeError:
                    type_ = getattr(cls._sql_object, f"_{field}") # Dicey workaround for hybrid_property with underscore
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
                        type_name = cls.model_fields[field].annotation.__name__
            case "ObjectAssociationProxyInstance":
                type_name = "AssociationList"
            case "InstrumentedAttribute":
                type_name = cls.model_fields[field].annotation.__name__
            case _:
                logger.debug(f"Got type: {type_name} for field {field}.")
        return type_name

    @property
    def form_dictionary(self) -> Generator[dict, None, None]:
        if self.__class__.__name__ == "PydBaseClass":
            raise NotImplementedError("Must be used in subclass only")
        data = self.model_dump()
        for field in self.described_fields:
            type_name = self.determine_field_type(field)
            if field.lower().strip("_") in self.sql_classes:
                model: models.BaseClass = models.BaseClass.find_subclasses(class_alias=field.lower().strip("_"))
                try:
                    excluded = [item.name for item in model.query() if self.name not in [i.name for i in getattr(item, self.__class__.__name__.lower().replace("pyd", ""))] and item.name not in data[field]]
                except AttributeError as e:
                    logger.warning(f"Could not get excluded items for field {field} due to {e}. Trying sql based.")
                    this_sql = self.to_sql()
                    excluded = [item.name for item in model.query() if this_sql not in getattr(item, self.__class__.__name__.lower().replace("pyd", "")) and item.name not in data[field]]
            else:
                excluded = None
            tooltip = self.__class__.model_fields[field].description
            value = data[field]
            if isinstance(value, list):
                value = [value['name'] if isinstance(value, dict) and 'name' in value.keys() else value for value in value]
            yield dict(field=field, type=type_name.upper(), value=value, tooltip=tooltip, excluded=excluded)

    @classmethod
    def get_association_class(cls, field: str):
        lookup_name = cls.__name__.replace("Pyd", "")
        logger.debug(f"Looking for association class for field {lookup_name}")
        subclasses = [class_ for class_ in PydBaseClass.get_subclasses() if lookup_name in class_.__name__ and "association" in class_.__name__.lower()]
        logger.debug(f"Found subclasses: {pformat([class_ for class_ in subclasses])}")
        class_names = [(class_.__name__.replace(lookup_name, ""), class_) for class_ in subclasses]
        class_names = [(class_[0].replace("Pyd", ""), class_[1]) for class_ in class_names]
        logger.debug(f"Looking for association class for field {field} in classes: {pformat(class_names)}")
        class_ = next((subclass_[1] for subclass_ in class_names if field.lower().strip("_") in subclass_[0].lower()), None)
        logger.debug(f"Found association class: {class_} for field {field}")
        if class_ is None:
            logger.error(f"Could not find association class for field {field} in {pformat(class_names)}")
        return class_

    @property
    def html_form(self) -> str:
        if "association" in self.__class__.__name__.lower():
            association = True
        else:
            association = False
        env = jinja_template_loading()
        template = env.get_template("managers/manager_form.html")
        logger.debug(f"Form dictionary: {pformat(list(self.form_dictionary))}")
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
        

from .abstract import (PydEquipmentRole, PydProcess, PydReagent, PydReagentRole, PydTips, PydProcedureType, PydResultsType, PydSubmissionType)
from .concrete import (PydEquipment, PydClientLab, PydClientSubmission, PydContact, PydProcedure, PydProcessVersion, PydResults, PydRun,
                       PydReagentLot, PydSample, PydTipsLot)