"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import sys, logging
from pandas import DataFrame
from pydantic import BaseModel
from sqlalchemy import Column, INTEGER, String, JSON
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session, InstrumentedAttribute, ColumnProperty
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.exc import ArgumentError, InvalidRequestError
from typing import Any, List
from pathlib import Path

from sqlalchemy.orm.relationships import _RelationshipDeclared

from tools import report_result, list_sort_dict

# NOTE: Load testing environment
if 'pytest' in sys.modules:
    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

# NOTE: For inheriting in LogMixin
Base: DeclarativeMeta = declarative_base()

logger = logging.getLogger(f"submissions.{__name__}")


class LogMixin(Base):
    __abstract__ = True

    @property
    def truncated_name(self):
        name = str(self)
        if len(name) > 64:
            name = name.replace("<", "").replace(">", "")
        if len(name) > 64:
            # NOTE: As if re'agent'
            name = name.replace("agent", "")
        if len(name) > 64:
            name = f"...{name[-61:]}"
        return name


class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.
    """
    __abstract__ = True  #: NOTE: Will not be added to DB

    __table_args__ = {'extend_existing': True}  #: Will only add new columns

    singles = ['id']
    omni_removes = ["id", 'submissions', "omnigui_class_dict", "omnigui_instance_dict"]
    omni_sort = ["name"]

    @classproperty
    def skip_on_edit(cls):
        if "association" in cls.__name__.lower() or cls.__name__.lower() == "discount":
            return True
        else:
            return False

    @classproperty
    def aliases(cls):
        return [cls.query_alias]

    @classproperty
    def level(cls):
        if "association" in cls.__name__.lower() or cls.__name__.lower() == "discount":
            return 2
        else:
            return 1

    @classproperty
    def query_alias(cls):
        return cls.__name__.lower()

    @classmethod
    @declared_attr
    def __tablename__(cls) -> str:
        """
        Sets table name to lower case class name.

        Returns:
            str: lower case class name
        """
        return f"_{cls.__name__.lower()}"

    @classmethod
    @declared_attr
    def __database_session__(cls) -> Session:
        """
        Pull db session from ctx to be used in operations

        Returns:
            Session: DB session from ctx settings.
        """
        if 'pytest' not in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.database_session

    @classmethod
    @declared_attr
    def __directory_path__(cls) -> Path:
        """
        Pull directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions directory in Settings object
        """
        if 'pytest' not in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.directory_path

    @classmethod
    @declared_attr
    def __backup_path__(cls) -> Path:
        """
        Pull backup directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions backup directory in Settings object
        """
        if 'pytest' not in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.backup_path

    @classmethod
    def get_default_info(cls, *args) -> dict | list | str:
        """
        Returns default info for a model

        Returns:
            dict | list | str: Output of key:value dict or single (list, str) desired variable
        """
        # NOTE: singles is a list of fields that need to be limited to 1 result.
        singles = list(set(cls.singles + BaseClass.singles))
        return dict(singles=singles)

    @classmethod
    def find_regular_subclass(cls, name: str = "") -> Any:
        """

        Args:
            name (str): name of subclass of interest.

        Returns:
            Any: Subclass of this object

        """
        # if not name:
        #     logger.warning("You need to include a name of what you're looking for.")
        #     return cls
        if " " in name:
            search = name.title().replace(" ", "")
        else:
            search = name
        return next((item for item in cls.__subclasses__() if item.__name__ == search), cls)

    @classmethod
    def fuzzy_search(cls, **kwargs) -> List[Any]:
        """
        Uses approximation of fields to get list of query results.

        Args:
            **kwargs ():

        Returns:
            List[Any]: Results of sqlalchemy query.
        """
        query: Query = cls.__database_session__.query(cls)
        for k, v in kwargs.items():
            # NOTE: Not sure why this is necessary, but it is.
            search = f"%{v}%"
            try:
                attr = getattr(cls, k)
                # NOTE: the secret sauce is in attr.like
                query = query.filter(attr.like(search))
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\nSkipping.")
        return query.limit(50).all()

    @classmethod
    def results_to_df(cls, objects: list, **kwargs) -> DataFrame:
        """

        Args:
            objects (list): Objects to be converted to dataframe.
            **kwargs (): Arguments necessary for the to_sub_dict method. eg extraction_kit=X

        Returns:
            Dataframe
        """
        try:
            records = [obj.to_sub_dict(**kwargs) for obj in objects]
        except AttributeError:
            records = [{k: v['instance_attr'] for k, v in obj.omnigui_instance_dict.items()} for obj in objects]
        return DataFrame.from_records(records)

    @classmethod
    def query(cls, **kwargs) -> Any | List[Any]:
        """
        Default query function for models. Overridden in most models with additional filters.

        Returns:
            Any | List[Any]: Result of query execution.
        """
        return cls.execute_query(**kwargs)

    @classmethod
    def execute_query(cls, query: Query = None, model=None, limit: int = 0, **kwargs) -> Any | List[Any]:
        """
        Execute sqlalchemy query with relevant defaults.

        Args:
            model (Any, optional): model to be queried, allows for plugging in. Defaults to None
            query (Query, optional): input query object. Defaults to None
            limit (int): Maximum number of results. (0 = all). Defaults to 0

        Returns:
            Any | List[Any]: Single result if limit = 1 or List if other.
        """
        if model is None:
            model = cls
        if query is None:
            query: Query = cls.__database_session__.query(model)
        singles = model.get_default_info('singles')
        for k, v in kwargs.items():
            logger.info(f"Using key: {k} with value: {v}")
            try:
                attr = getattr(model, k)
                # NOTE: account for attrs that use list.
                if attr.property.uselist:
                    query = query.filter(attr.contains(v))
                else:
                    query = query.filter(attr == v)
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\nSkipping.")
            if k in singles:
                logger.warning(f"{k} is in singles. Returning only one value.")
                limit = 1
        with query.session.no_autoflush:
            match limit:
                case 0:
                    return query.all()
                case 1:
                    return query.first()
                case _:
                    return query.limit(limit).all()

    @report_result
    def save(self) -> Report | None:
        """
        Add the object to the database and commit
        """
        report = Report()
        try:
            self.__database_session__.add(self)
            self.__database_session__.commit()
        except Exception as e:
            logger.critical(f"Problem saving object: {e}")
            logger.error(f"Error message: {type(e)}")
            self.__database_session__.rollback()
            report.add_result(Result(msg=e, status="Critical"))
            return report

    @property
    def omnigui_instance_dict(self) -> dict:
        """
        For getting any object in an omni-thing friendly output.

        Returns:
            dict: Dictionary of object minus _sa_instance_state with id at the front.
        """
        dicto = {key: dict(class_attr=getattr(self.__class__, key), instance_attr=getattr(self, key))
                 for key in dir(self.__class__) if
                 isinstance(getattr(self.__class__, key), InstrumentedAttribute) and key not in self.omni_removes
                 }
        for k, v in dicto.items():
            try:
                v['instance_attr'] = v['instance_attr'].name
            except AttributeError:
                continue
        try:
            dicto = list_sort_dict(input_dict=dicto, sort_list=self.__class__.omni_sort)
        except TypeError as e:
            logger.error(f"Could not sort {self.__class__.__name__} by list due to :{e}")
        try:
            dicto = {'id': dicto.pop('id'), **dicto}
        except KeyError:
            pass
        # logger.debug(f"{self.__class__.__name__} omnigui dict:\n\n{pformat(dicto)}")
        return dicto

    @classproperty
    def pydantic_model(cls) -> BaseModel:
        """
        Gets the pydantic model corresponding to this object.

        Returns:
            Pydantic model with name "Pyd{cls.__name__}"
        """
        from backend.validators import pydant
        try:
            model = getattr(pydant, f"Pyd{cls.__name__}")
        except AttributeError:
            logger.warning(f"Couldn't get {cls.__name__} pydantic model.")
            return pydant.PydElastic
        return model

    @classproperty
    def add_edit_tooltips(cls) -> dict:
        """
        Gets tooltips for Omni-add-edit

        Returns:
            dict: custom dictionary for this class.
        """
        return dict()

    @classmethod
    def relevant_relationships(cls, relationship_instance):
        query_kwargs = {relationship_instance.query_alias: relationship_instance}
        return cls.query(**query_kwargs)

    def check_all_attributes(self, attributes: dict):
        logger.debug(f"Incoming attributes: {attributes}")
        for key, value in attributes.items():
            # print(getattr(self.__class__, key).property)
            if value.lower() == "none":
                value = None
            self_value = getattr(self, key)
            class_attr = getattr(self.__class__, key)
            match class_attr.property:
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
                case _RelationshipDeclared():
                    try:
                        self_value = self_value.name
                    except AttributeError:
                        pass
                    if class_attr.property.uselist:
                        self_value = self_value.__str__()
            logger.debug(f"Checking self_value {self_value} of type {type(self_value)} against attribute {value} of type {type(value)}")
            if self_value != value:
                output = False
                logger.debug(f"Value {key} is False, returning.")
                return output
        return True

    def __setattr__(self, key, value):
        logger.debug(f"Attempting to set {key} to {pformat(value)}")
        try:
            field_type = getattr(self.__class__, key)
        except AttributeError:
            return super().__setattr__(key, value)
        if isinstance(field_type, InstrumentedAttribute):
            logger.debug(f"{key} is an InstrumentedAttribute.")
            match field_type.property:
                case ColumnProperty():
                    logger.debug(f"Setting ColumnProperty to {value}")
                    return super().__setattr__(key, value)
                case _RelationshipDeclared():
                    logger.debug(f"Setting _RelationshipDeclared to {value}")
                    if field_type.property.uselist:
                        logger.debug(f"Setting with uselist")
                        if self.__getattribute__(key) is not None:
                            if isinstance(value, list):
                                value = self.__getattribute__(key) + value
                            else:
                                value = self.__getattribute__(key) + [value]
                        else:
                            value = [value]
                        return super().__setattr__(key, value)
                    else:
                        if isinstance(value, list):
                            if len(value) == 1:
                                value = value[0]
                            else:
                                raise ValueError("Object is too long to parse a single value.")
                        return super().__setattr__(key, value)
        else:
            super().__setattr__(key, value)


class ConfigItem(BaseClass):
    """
    Key:JSON objects to store config settings in database. 
    """
    id = Column(INTEGER, primary_key=True)
    key = Column(String(32))  #: Name of the configuration item.
    value = Column(JSON)  #: Value associated with the config item.

    def __repr__(self) -> str:
        return f"<ConfigItem({self.key} : {self.value})>"

    @classmethod
    def get_config_items(cls, *args) -> ConfigItem | List[ConfigItem]:
        """
        Get desired config items, or all from database

        Returns:
            ConfigItem|List[ConfigItem]: Config item(s)
        """
        query = cls.__database_session__.query(cls)
        match len(args):
            case 0:
                config_items = query.all()
            # NOTE: If only one item sought, don't use a list, just return it.
            case 1:
                config_items = query.filter(cls.key == args[0]).first()
            case _:
                # NOTE: All items whose key field is in args.
                config_items = query.filter(cls.key.in_(args)).all()
        return config_items


from .controls import *
# NOTE: import order must go: orgs, kit, subs due to circular import issues
from .organizations import *
from .kits import *
from .submissions import *
from .audit import *

# NOTE: Add a creator to the submission for reagent association. Assigned here due to circular import constraints.
# https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html#sqlalchemy.ext.associationproxy.association_proxy.params.creator
BasicSubmission.reagents.creator = lambda reg: SubmissionReagentAssociation(reagent=reg)
