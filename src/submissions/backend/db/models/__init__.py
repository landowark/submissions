"""
Contains all models for sqlalchemy
"""
from __future__ import annotations

import sys, logging, json

import sqlalchemy.exc
from dateutil.parser import parse
from pandas import DataFrame
from pydantic import BaseModel
from sqlalchemy import Column, INTEGER, String, JSON
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session, InstrumentedAttribute, ColumnProperty
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.exc import ArgumentError
from typing import Any, List, ClassVar
from pathlib import Path
from sqlalchemy.orm.relationships import _RelationshipDeclared

from frontend import select_save_file
from tools import report_result, list_sort_dict
from backend.excel import writers

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
    omni_removes = ["id", 'run', "omnigui_class_dict", "omnigui_instance_dict"]
    omni_sort = ["name"]
    omni_inheritable = []
    searchables = []

    _misc_info = Column(JSON)

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._misc_info = dict()

    @classproperty
    def jsons(cls) -> List[str]:
        """
        Get list of JSON db columns

        Returns:
            List[str]: List of column names
        """
        try:
            return [item.name for item in cls.__table__.columns if isinstance(item.type, JSON)]
        except AttributeError:
            return []

    @classproperty
    def timestamps(cls) -> List[str]:
        """
        Get list of TIMESTAMP columns

        Returns:
            List[str]: List of column names
        """
        try:
            return [item.name for item in cls.__table__.columns if isinstance(item.type, TIMESTAMP)]
        except AttributeError:
            return []

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
    def find_regular_subclass(cls, name: str | None = None) -> Any:
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
        Converts class sub_dicts into a Dataframe for all control of the class.

        Args:
            objects (list): Objects to be converted to dataframe.
            **kwargs (): Arguments necessary for the to_sub_dict method. eg kittype=X

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
    def query_or_create(cls, **kwargs) -> Tuple[Any, bool]:
        new = False
        allowed = [k for k, v in cls.__dict__.items() if isinstance(v, InstrumentedAttribute) or isinstance(v, hybrid_property)]
        # and not isinstance(v.property, _RelationshipDeclared)]
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        outside_kwargs = {k: v for k, v in kwargs.items() if k not in allowed}
        logger.debug(f"Sanitized kwargs: {sanitized_kwargs}")
        instance = cls.query(**sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            # logger.debug(f"QorC Setting {k} to {v}")
            if k == "id":
                continue
            try:
                setattr(instance, k, v)
            except AttributeError as e:
                from backend.validators.pydant import PydBaseClass
                if issubclass(v.__class__, PydBaseClass):
                    setattr(instance, k, v.to_sql())
                else:
                    logger.error(f"Could not set {k} due to {e}")
        instance._misc_info.update(outside_kwargs)
        logger.info(f"Instance from query or create: {instance}, new: {new}")
        return instance, new

    @classmethod
    def query(cls, **kwargs) -> Any | List[Any]:
        """
        Default query function for models. Overridden in most models with additional filters.

        Returns:
            Any | List[Any]: Result of query execution.
        """
        if "name" in kwargs.keys():
            kwargs['limit'] = 1
        return cls.execute_query(**kwargs)

    @classmethod
    def execute_query(cls, query: Query = None, model=None, limit: int = 0, offset:int|None=None, **kwargs) -> Any | List[Any]:
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
        # if model is None:
        #     model = cls
        # logger.debug(f"Model: {model}")
        if query is None:
            query: Query = cls.__database_session__.query(cls)
        else:
            logger.debug(f"Incoming query: {query}")
        singles = cls.get_default_info('singles')
        for k, v in kwargs.items():
            logger.info(f"Using key: {k} with value: {v} against {cls}")
            try:
                attr = getattr(cls, k)
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\n.")
                continue
                # NOTE: account for attrs that use list.
            try:
                check = attr.property.uselist
            except AttributeError:
                check = False
            if check:
                logger.debug("Got uselist")
                try:
                    query = query.filter(attr.contains(v))
                except ArgumentError:
                    continue
            else:
                logger.debug("Single item.")
                try:
                    query = query.filter(attr == v)
                except ArgumentError:
                    continue
            if k in singles:
                logger.warning(f"{k} is in singles. Returning only one value.")
                limit = 1
        if offset:
            query.offset(offset)
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
        # except sqlalchemy.exc.IntegrityError as i:
        #     logger.error(f"Integrity error saving {self} due to: {i}")
        #     logger.error(pformat(self.__dict__))
        except Exception as e:
            logger.critical(f"Problem saving {self} due to: {e}")
            logger.error(f"Error message: {type(e)}")
            logger.error(pformat(self.__dict__))
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

    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        env = jinja_template_loading()
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            #     logger.error(f"Couldn't find template {e}")
            template = env.get_template("details.html")
        return template

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
        # logger.debug(f"Attempting to set: {key} to {value}")
        if key.startswith("_"):
            return super().__setattr__(key, value)
        # try:
        check = not hasattr(self, key)
        # except:
        #     return
        if check:
            try:
                value = json.dumps(value)
            except TypeError:
                value = str(value)
            try:
                self._misc_info.update({key: value})
            except AttributeError:
                self._misc_info = {key: value}
            return
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
                        # logger.debug(f"Setting with uselist")
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
                                # value = value
                                pass
                            else:
                                value = [value]
                        try:
                            value = list(set(value))
                        except TypeError:
                            pass
                        # logger.debug(f"Final value for {key}: {value}")
                        return super().__setattr__(key, value)
                    else:
                        if isinstance(value, list):
                            if len(value) == 1:
                                value = value[0]
                            else:
                                raise ValueError("Object is too long to parse a single value.")
                        try:
                            return super().__setattr__(key, value)
                        except AttributeError:
                            logger.warning(f"Possible attempt to set relationship {key} to simple var type. {value}")
                            relationship_class = field_type.property.entity.entity
                            value = relationship_class.query(name=value)
                            try:
                                return super().__setattr__(key, value)
                            except AttributeError:
                                return super().__setattr__(key, None)
                case _:
                    return super().__setattr__(key, value)
        else:
            return super().__setattr__(key, value)

    def delete(self):
        logger.error(f"Delete has not been implemented for {self.__class__.__name__}")

    def rectify_query_date(input_date: datetime, eod: bool = False) -> str:
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

    def details_dict(self, **kwargs):
        relevant = {k: v for k, v in self.__class__.__dict__.items() if
                    isinstance(v, InstrumentedAttribute) or isinstance(v, AssociationProxy)}
        output = {}
        for k, v in relevant.items():
            try:
                check = v.foreign_keys
            except AttributeError:
                check = False
            if check:
                continue
            try:
                value = getattr(self, k)
            except AttributeError:
                continue
            match value:
                case datetime():
                    value = value.strftime("%Y-%m-%d %H:%M:%S")
                case _:
                    pass
            output[k.strip("_")] = value
        return output

    def to_pydantic(self, **kwargs):
        from backend.validators import pydant
        pyd_model_name = f"Pyd{self.__class__.__name__}"
        logger.debug(f"Looking for pydant model {pyd_model_name}")
        try:
            pyd = getattr(pydant, pyd_model_name)
        except AttributeError:
            raise AttributeError(f"Could not get pydantic class {pyd_model_name}")
        return pyd(**self.details_dict(**kwargs))

    def show_details(self, obj):
        logger.debug("Show Details")
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

    def export(self, obj, output_filepath: str|Path|None=None):
        if not hasattr(self, "template_file"):
            logger.error(f"Export not implemented for {self.__class__.__name__}")
            return
        pyd = self.to_pydantic()
        if not output_filepath:
            output_filepath = select_save_file(obj=obj, default_name=pyd.construct_filename(), extension="xlsx")
        Writer = getattr(writers, f"{self.__class__.__name__}Writer")
        writer = Writer(output_filepath=output_filepath, pydant_obj=pyd, range_dict=self.range_dict)
        workbook = writer


class LogMixin(Base):
    tracking_exclusion: ClassVar = ['artic_technician', 'clientsubmissionsampleassociation',
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
# NOTE: import order must go: orgs, kittype, run due to circular import issues
from .organizations import *
from .kits import *
from .submissions import *
from .audit import AuditLog

# NOTE: Add a creator to the procedure for reagent association. Assigned here due to circular import constraints.
# https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html#sqlalchemy.ext.associationproxy.association_proxy.params.creator
# Procedure.reagents.creator = lambda reg: ProcedureReagentAssociation(reagent=reg)
