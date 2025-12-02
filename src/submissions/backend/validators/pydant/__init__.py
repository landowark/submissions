"""
Contains pydantic models and accompanying validators
"""
from __future__ import annotations
import logging, sys, string
from pprint import pformat
from pydantic import BaseModel, model_validator, ConfigDict
from datetime import date, datetime
from typing import TYPE_CHECKING, ClassVar, Generator
from tools import classproperty, row_keys
from backend.db import models
from backend.db.models import *
from sqlalchemy.orm.attributes import InstrumentedAttribute


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
        fields = list(self.model_fields.keys()) + list(self.model_extra.keys())
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
        return [class_[0].lower() for class_ in inspect.getmembers(models) if isinstance(class_[1], DeclarativeMeta) and issubclass(class_[1], BaseClass)]
    
    @property
    def construct_form_dictionary(self) -> Generator[dict, None, None]:
        data = self.model_dump()
        for field in self.described_fields:
            type_ = self.model_fields[field].annotation
            value = data[field]
            if field.lower().strip("_") in self.sql_classes:
                model = models.BaseClass
            



class PydAbstract(PydBaseClass):

    @classmethod
    def get_managables(cls):
        for class_ in PydAbstract.__subclasses__:
            if len(class_.get_described_attributes()):
                yield class_._sql_object


class PydConcrete(PydBaseClass):

    @classmethod
    def get_managables(cls):
        for class_ in PydConcrete.__subclasses__:
            if len(class_.get_described_attributes()):
                yield class_._sql_object
        

from .abstract import (PydEquipmentRole, PydProcess, PydReagent, PydReagentRole, PydTips)
from .concrete import (PydEquipment, PydClientLab, PydClientSubmission, PydContact, PydProcedure, PydProcessVersion, PydResults, PydRun,
                       PydReagentLot, PydSample)