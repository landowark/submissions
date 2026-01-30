"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
from pathlib import Path
import logging, sys, string, inspect
from pprint import pformat
from pydantic import BaseModel, Field, ValidationError, model_validator, ConfigDict, field_validator
from pydantic_core import core_schema
from datetime import date, datetime
from typing import Any, ClassVar, Generator, List
from types import UnionType
from tools import classproperty, jinja_template_loading, row_keys, sanitize_object_for_json
from backend.db import models
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.orm import DeclarativeMeta, ColumnProperty
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.associationproxy import _AssociationList
from PyQt6.QtWidgets import QDialog


logger = logging.getLogger(f"submission.{__name__}")


class PydBaseClass(BaseModel):#, validate_assignment=True):

    model_config = ConfigDict(
        extra="allow",
        arbitrary_types_allowed=True,
    )

    def __repr_args__(self) -> core_schema.ReprArgs:
        # Get the default repr arguments first
        # This iterates over defined fields and computed fields
        args = super().__repr_args__()
        
        # Filter out any arguments that correspond to extra fields
        # The 'name' attribute of ReprArgsElement is the field name
        extra_fields = getattr(self, '__pydantic_extra__', {})
        return [arg for arg in args if arg[0] not in extra_fields]

    name: str | dict = Field(default="NA", validate_default=True)
    sql_instance: models.BaseClass | None = Field(default=None, validate_default=True, repr=False)
    new: bool = Field(default=True, repr=False, validate_default=True)

    # _sql_object: ClassVar = None
    key_value_order: ClassVar[List] = []
    non_expandables: ClassVar[List] = ["procedure"]
    
    def model_post_init(self, __context__=None) -> None:
        if self.name == "NA":
            try:
                self.name = self.constructed_name
            except AttributeError:
                logger.error(f"{self.__class__.__qualname__} has no attribute 'constructed_name'")
    
    @classproperty
    def aliases(cls) -> List[str]:
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
        
    @field_validator("sql_instance", mode="before")
    @classmethod
    def generate_blank_sql_instance(cls, value):
        if value is None:
            value = cls._sql_class()
        return value
    
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
                item = item.get('value', None)
            case _:
                pass
        return item

    def improved_dict_expand_fields(self, fields: List[str | dict]) -> dict:
        """
        Expands fields in the improved dict for use in forms.

        Args:
            fields (List[str] | List[dict]): List[str] is a flat expansion, List[dict] expands recursively.

        Returns:
            dict: Expanded dictionary.
        """
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
                            pass
                        case _AssociationList():
                            output = []
                            for item in value.col:
                                dicto: dict = item.to_pydantic().improved_dict
                                target = getattr(item, key)
                                target = target.to_pydantic().improved_dict
                                target.update({k:v for k, v in dicto.items() if k !="name"})
                                if target['name'] not in [thing['name'] for thing in output]:
                                    output.append(target)
                        case InstrumentedList():
                            output = [item.to_pydantic().improved_dict for item in value]
                        case x if issubclass(value.__class__, models.BaseClass):
                            output = value.to_pydantic().improved_dict
                        case _:
                            continue
                case dict():
                    key = list(field.keys())[0]
                    new_fields = list(field.values())[0]
                    try:
                        value = getattr(self.sql_instance, key)
                    except AttributeError as e:
                        logger.error(f"Skipping {key} in {self.sql_instance} due to {e}")
                        continue
                    match value:
                        case _AssociationList():
                            output = []
                            output = [item.to_pydantic().improved_dict_expand_fields(new_fields) for item in value]
                            for item in value.col:
                                dicto: dict = item.to_pydantic().improved_dict_expand_fields(new_fields)
                                target = getattr(item, key)
                                target = target.to_pydantic().improved_dict_expand_fields(new_fields)
                                target.update({k:v for k, v in dicto.items() if k !="name"})
                                if target['name'] not in [thing['name'] for thing in output]:
                                    output.append(target)
                        case InstrumentedList():
                            output = [item.to_pydantic().improved_dict_expand_fields(new_fields) for item in value]
                        case x if issubclass(value.__class__, models.BaseClass):
                            output = value.to_pydantic().improved_dict
                        case _:
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
        # logger.debug(f"{self.__class__.__name__} output:\n{output}")
        if "misc_info" in output.keys():
            iterator = output['misc_info'] or {}
            for k, v in iterator.items():
                if "sql_instance" in k:
                    continue
                if k not in output.keys():
                    output[k] = v
            del output['misc_info']
        if "name" not in output.keys():
            try:
                output['name'] = self.sql_instance.name
            except AttributeError:
                try:
                    output['name'] = self.constructed_name
                except AttributeError:
                    logger.error(f"Cannot set name for {self.__class__.__name__}")
        return output

    def to_sql(self, update: bool = True) -> models.BaseClass:
        """
        Converts this instance to the corresponding SQLAlchemy object.

        Args:
            update (bool): If True, relationships will be updated.

        Returns:
            models.BaseClass: SQLAlchemy translation of this object.

        """
        # Prevent accidental clearing of existing SQL relationship lists:
        # Many SQLAlchemy relationship setters in this codebase treat an
        # assignment of an empty list as an instruction to clear that
        # relationship (often resulting in cascade delete-orphan).
        # When converting a Pydantic model to SQL, an empty list usually
        # means "no change" rather than "clear all associations". To be
        # conservative, don't pass empty lists through to query_or_create
        # so we don't unintentionally wipe related association rows.
        if not update:
            return self.sql_instance
        sanitized_dicto = {k: v for k, v in self.improved_dict.items() if not (isinstance(v, list) and len(v) == 0)}
        try:
            assert self.sql_instance is not None
        except AssertionError:
            raise AttributeError(f"Sql Instance for {self.__class__.__name__} is None, cannot save")
        for k, v in sanitized_dicto.items():
            # logger.debug(f"Processing field {k} with value {v} on {self.sql_instance}, classtype: {getattr(self._sql_class, k, None)}")
            try:
                class_attr = getattr(self._sql_class, k, None).property
            except AttributeError as e:
                logger.error(f"Couldn't get class_attr {k} for {self._sql_class} due to {e}")
                continue
            match class_attr:
                case hybrid_property():
                    continue
                case ColumnProperty():
                    if getattr(self.sql_instance, k) == v:
                        continue
                    else:
                        logger.debug(f"New value for {k} on {self.sql_instance}: {v}")
                        try:
                            setattr(self.sql_instance, k, v)
                        except AttributeError as e:
                            logger.error(f"Could not set attribute {k} on {self.sql_instance} due to {e}")
                            continue
                case _:
                    pass
        for k, v in self.model_extra.items():
            self.sql_instance._misc_info[k] = sanitize_object_for_json(v)
        return self.sql_instance
    
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
                case x if issubclass(v.__class__, PydBaseClass):
                    pass
                case _:
                    continue
            # k = self.__class__.replacement_matrix.get(k, k)
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
    def determine_field_type(cls, field: str, is_new: bool = False) -> str:
        """
        Determines which type of field to use in the form.

        Args:
            field (str): Field name

        Returns:
            str: Type name
        """        
        type_ = getattr(cls._sql_class, field.lower().strip("_"))
        type_name = type_.__class__.__name__
        match type_name:
            case "hybrid_propertyProxy":
                try:
                    type_ = getattr(cls._sql_class, type_.property.key)
                except AttributeError:
                    type_ = getattr(cls._sql_class, f"_{field}") # Dicey workaround for hybrid_property with underscore
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
                        annotation = cls.model_fields[field].annotation
                        if isinstance(annotation, UnionType):
                            type_name = annotation.__args__[0].__name__
                        else:
                            try:
                                type_name = annotation.__name__
                            except AttributeError:
                                type_name = "Skipped"
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
    def subclasses(cls) -> Generator[PydBaseClass, None, None]:
        """
        Generates list of all PydBaseClass subclasses.

        Returns:
            Generator[PydBaseClass, None, None]: Generator of all subclasses.
        """
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
        
    def to_html(self, css_in: List[str| Path] | str = [], js_in: List[str | Path] | str = [],
                            **kwargs) -> str:
        details = {self._sql_class.__name__.lower() : self.clean_details_for_render(kwargs)}
        # template = self.details_template
        if isinstance(css_in, str):
            css_in = [css_in]
        env = jinja_template_loading()
        html_folder = Path(env.loader.__getattribute__("searchpath")[0])
        css_in = ["styles"] + css_in
        css_in = [html_folder.joinpath("css", f"{c}.css") for c in css_in]
        if isinstance(js_in, str):
            js_in = [js_in]
        js_in = ["details"] + js_in
        js_in = [html_folder.joinpath("js", f"{j}.js") for j in js_in]
        # if isinstance(template, str):
        #     template = f"{template}.html"
        # template = env.get_template(self.details_template)
        css_out = []
        for css in css_in:
            with open(css, "r") as f:
                css_out.append(f.read())
        js_out = []
        for js in js_in:
            with open(js, "r") as f:
                js_out.append(f.read())
        return self.sql_instance.details_template.render(css=css_out, js=js_out, **details)
    
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
                case datetime() | date():
                    value = value.strftime("%Y-%m-%d")
                case bytes():
                    continue
                case dict():
                    try:
                        value = value['name']
                    except KeyError:
                        if k == "_misc_info" or k == "misc_info":
                            value = value
                        else:
                            continue
                case x if issubclass(value.__class__, BaseClass): 
                    try:
                        value = value.name
                    except AttributeError:
                        logger.error(f"Couldn't get name for BaseClass subclase {type(value)}")
                        continue
                case x if issubclass(value.__class__, PydBaseClass):
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