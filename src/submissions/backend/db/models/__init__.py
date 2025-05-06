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
from sqlalchemy.exc import ArgumentError
from typing import Any, List, ClassVar
from pathlib import Path
from sqlalchemy.orm.relationships import _RelationshipDeclared
from tools import report_result, list_sort_dict

# NOTE: Load testing environment
if 'pytest' in sys.modules:
    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

# NOTE: For inheriting in LogMixin
Base: DeclarativeMeta = declarative_base()

logger = logging.getLogger(f"submissions.{__name__}")


class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.
    """
    __abstract__ = True  #: NOTE: Will not be added to DB as a table

    __table_args__ = {'extend_existing': True}  #: NOTE Will only add new columns

    singles = ['id']
    omni_removes = ["id", 'submissions', "omnigui_class_dict", "omnigui_instance_dict"]
    omni_sort = ["name"]
    omni_inheritable = []
    searchables = []

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.name})>"
        except AttributeError:
            return f"<{self.__class__.__name__}(Name Unavailable)>"

    @classproperty
    def aliases(cls) -> List[str]:
        """
        List of other names this class might be known by.

        Returns:
            List[str]: List of names
        """
        return [cls.query_alias]

    @classproperty
    def query_alias(cls) -> str:
        """
        What to query this class as.

        Returns:
            str: query name
        """
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
    def find_regular_subclass(cls, name: str|None = None) -> Any:
        """
        Args:
            name (str): name of subclass of interest.

        Returns:
            Any: Subclass of this object.
        """
        if name:
            if " " in name:
                search = name.title().replace(" ", "")
            else:
                search = name
            return next((item for item in cls.__subclasses__() if item.__name__ == search), cls)
        else:
            return cls.__subclasses__()


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
    def results_to_df(cls, objects: list | None = None, **kwargs) -> DataFrame:
        """
        Converts class sub_dicts into a Dataframe for all instances of the class.

        Args:
            objects (list): Objects to be converted to dataframe.
            **kwargs (): Arguments necessary for the to_sub_dict method. eg extraction_kit=X

        Returns:
            Dataframe
        """
        if not objects:
            try:
                records = [obj.to_sub_dict(**kwargs) for obj in cls.query()]
            except AttributeError:
                records = [obj.to_dict(**kwargs) for obj in cls.query(page_size=0)]
        else:
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
        # logger.debug(f"Kwargs: {kwargs}")
        if model is None:
            model = cls
        # logger.debug(f"Model: {model}")
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

    def check_all_attributes(self, attributes: dict) -> bool:
        """
        Checks this instance against a dictionary of attributes to determine if they are a match.

        Args:
            attributes (dict): A dictionary of attributes to be check for equivalence

        Returns:
            bool: If a single unequivocal value is found will be false, else true.
        """
        # logger.debug(f"Incoming attributes: {attributes}")
        for key, value in attributes.items():
            if value.lower() == "none":
                value = None
            # logger.debug(f"Attempting to grab attribute: {key}")
            self_value = getattr(self, key)
            class_attr = getattr(self.__class__, key)
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
                    # logger.debug(f"Checking {self_value}")
                    try:
                        self_value = self_value.name
                    except AttributeError:
                        pass
                    if class_attr.property.uselist:
                        self_value = self_value.__str__()
            try:
                # logger.debug(f"Check if {self_value.__class__} is subclass of {self.__class__}")
                check = issubclass(self_value.__class__, self.__class__)
            except TypeError as e:
                logger.error(f"Couldn't check if {self_value.__class__} is subclass of {self.__class__} due to {e}")
                check = False
            if check:
                # logger.debug(f"Checking for subclass name.")
                self_value = self_value.name
            # logger.debug(f"Checking self_value {self_value} of type {type(self_value)} against attribute {value} of type {type(value)}")
            if self_value != value:
                output = False
                # logger.debug(f"Value {key} is False, returning.")
                return output
        return True

    def __setattr__(self, key, value):
        """
        Custom dunder method to handle potential list relationship issues.
        """
        try:
            field_type = getattr(self.__class__, key)
        except AttributeError:
            return super().__setattr__(key, value)
        if isinstance(field_type, InstrumentedAttribute):
            # logger.debug(f"{key} is an InstrumentedAttribute.")
            match field_type.property:
                case ColumnProperty():
                    # logger.debug(f"Setting ColumnProperty to {value}")
                    return super().__setattr__(key, value)
                case _RelationshipDeclared():
                    # logger.debug(f"{self.__class__.__name__} Setting _RelationshipDeclared for {key} to {value}")
                    if field_type.property.uselist:
                        logger.debug(f"Setting with uselist")
                        existing = self.__getattribute__(key)
                        # NOTE: This is causing problems with removal of items from lists. Have to overhaul it.
                        if existing is not None:
                            logger.debug(f"{key} Existing: {existing}, incoming: {value}")
                            if isinstance(value, list):
                                # value = existing + value
                                value = value
                            else:
                                value = existing + [value]
                        else:
                            if isinstance(value, list):
                                value = value
                            else:
                                value = [value]
                        value = list(set(value))
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

    def delete(self):
        logger.error(f"Delete has not been implemented for {self.__class__.__name__}")

    def rectify_query_date(input_date, eod: bool = False) -> str:
        """
        Converts input into a datetime string for querying purposes

        Args:
            eod (bool, optional): Whether to use max time to indicate end of day.
            input_date ():

        Returns:
            datetime: properly formated datetime
        """
        match input_date:
            case datetime() | date():
                output_date = input_date
            case int():
                output_date = datetime.fromordinal(
                    datetime(1900, 1, 1).toordinal() + input_date - 2)
            case _:
                output_date = parse(input_date)
        if eod:
            addition_time = datetime.max.time()
        else:
            addition_time = datetime.min.time()
        output_date = datetime.combine(output_date, addition_time).strftime("%Y-%m-%d %H:%M:%S")
        return output_date


class LogMixin(Base):

    tracking_exclusion: ClassVar = ['artic_technician', 'submission_sample_associations',
                                    'submission_reagent_associations', 'submission_equipment_associations',
                                    'submission_tips_associations', 'contact_id', 'gel_info', 'gel_controls',
                                    'source_plates']

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
from .audit import AuditLog

# NOTE: Add a creator to the submission for reagent association. Assigned here due to circular import constraints.
# https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html#sqlalchemy.ext.associationproxy.association_proxy.params.creator
BasicSubmission.reagents.creator = lambda reg: SubmissionReagentAssociation(reagent=reg)
