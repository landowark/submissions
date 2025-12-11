"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import sys, logging, json, inspect
from datetime import datetime, date
from pprint import pformat
from dateutil.parser import parse
from jinja2 import TemplateNotFound
from pandas import DataFrame
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP, FLOAT
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session, InstrumentedAttribute, ColumnProperty
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.exc import ArgumentError
from typing import Any, List, ClassVar, Tuple, TYPE_CHECKING
from pathlib import Path
from sqlalchemy.orm.relationships import _RelationshipDeclared
from tools import report_result, list_sort_dict, jinja_template_loading, Report, Alert, ctx
if TYPE_CHECKING:
    from pydantic import BaseModel

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

    _misc_info = Column(JSON)

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.name})>"
        except AttributeError:
            return f"<{self.__class__.__name__}(Name Unavailable)>"

    @hybrid_property
    def misc_info(self):
        return self._misc_info
    
    @misc_info.setter
    def misc_info(self, value):
        print(f"Setting misc_info to {value}")
        self._misc_info = value

    @classproperty
    def aliases(cls):
        """
        List of other names this class might be known by.

        Returns:
            List[str]: List of names
        """
        return [cls.query_alias]

    @declared_attr
    @classmethod
    def query_alias(cls):
        """
        What to query this class as.

        Returns:
            str: query name
        """
        return cls.__name__.lower()

    @declared_attr
    @classmethod
    def __tablename__(cls) -> str:
        """
        Sets table name to lower case class name.

        Returns:
            str: lower case class name
        """
        return f"_{cls.query_alias}"

    @declared_attr
    @classmethod
    def __database_session__(cls) -> Session:
        """
        Pull db session from ctx to be used in operations

        Returns:
            Session: DB session from ctx settings.
        """
        return ctx.database_session

    @declared_attr
    @classmethod
    def __directory_path__(cls) -> Path:
        """
        Pull directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions directory in Settings object
        """
        return ctx.directory_path

    @declared_attr
    @classmethod
    def __backup_path__(cls) -> Path:
        """
        Pull backup directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions backup directory in Settings object
        """
        return ctx.backup_path

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._misc_info = dict()

    @declared_attr
    @classmethod
    def jsons(cls):
        """
        Get list of JSON db columns

        Returns:
            List[str]: List of column names
        """
        try:
            return [item.name for item in cls.__table__.columns if isinstance(item.type, JSON)]
        except AttributeError:
            return []

    @declared_attr
    @classmethod
    def timestamps(cls):
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
    def get_searchables(cls):
        output = []
        for item in inspect.getmembers(cls, lambda a: not (inspect.isroutine(a))):
            if item[0] in ["_misc_info"]:
                continue
            if not isinstance(item[1], InstrumentedAttribute):
                continue
            if not isinstance(item[1].property, ColumnProperty):
                continue
            if len(item[1].foreign_keys) > 0:
                continue
            if item[1].type.__class__.__name__ not in ["String"]:
                continue
            output.append(item[0])
        return output

    @classmethod
    def get_default_info(cls, *args) -> dict | list | str:
        """
        Returns default info for a model

        Returns:
            dict | list | str: Output of key:value dict or single (list, str) desired variable
        """
        # NOTE: singles is a list of fields that need to be limited to 1 result.
        return dict(singles=list(set(cls.singles + BaseClass.singles)))

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
        Converts class details_dicts into a Dataframe for all control of the class.

        Args:
            objects (list, Optional): Objects to be converted to dataframe. Defaults to None.
            **kwargs (): Arguments necessary for the details_dict method. eg proceduretype=X

        Returns:
            Dataframe
        """
        if not objects:
            try:
                q = cls.query()
            except AttributeError:
                q = cls.query(page_size=0)
        else:
            q = objects
        records = []
        for obj in q:
            dicto = obj.details_dict(**kwargs)
            records.append({key: value for key, value in dicto.items() if key not in dicto['excluded']})
        return DataFrame.from_records(records)

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[Any, bool]:
        """
        Gets existing object or creates new one.

        Args:
            **kwargs:

        Returns:
            Tuple[Any, bool]: Object and whether or not it's new.
        """
        new = False
        allowed = [k for k, v in cls.__dict__.items() if
                   isinstance(v, InstrumentedAttribute) or isinstance(v, hybrid_property)]
        query_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        print(f"Sanitized Kwargs: {query_kwargs}")
        # NOTE: outside kwargs will be reintroduced into misc_info
        outside_kwargs = {k: v for k, v in kwargs.items() if k not in allowed}
        print(f"Outside kwargs: {outside_kwargs}")
        instance = cls.query(limit=1, **query_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in kwargs.items():
            if k == "id":
                continue
            # NOTE: Setattr used to make use of overridden method.
            setattr(instance, k, v)
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
    def execute_query(cls, query: Query = None, model=None, limit: int = 0, offset: int | None = None,
                      **kwargs) -> Any | List[Any]:
        """
        Execute sqlalchemy query with relevant defaults.

        Args:
            query (Query, optional): input query object. Defaults to None
            model (Any, optional): model to be queried, allows for plugging in. Defaults to None
            limit (int): Maximum number of results. (0 = all). Defaults to 0
            offset (int, optional): Offset from which to start. Defaults to None.

        Returns:
            Any | List[Any]: Single result if limit = 1 or List if other.
        """
        if query is None:
            query: Query = cls.__database_session__.query(cls)
        singles = cls.get_default_info('singles')
        for k, v in kwargs.items():
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
                try:
                    query = query.filter(attr.contains(v))
                except ArgumentError:
                    continue
            else:
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
        del_keys = []
        try:
            items = self._misc_info.items()
        except AttributeError:
            items = []
        # NOTE: Ensure values in misc_info are json serializable.
        for key, value in items:
            try:
                json.dumps(value)
            except TypeError as e:
                del_keys.append(key)
        for dk in del_keys:
            del self._misc_info[dk]
        try:
            self.__database_session__.add(self)
            self.__database_session__.commit()
        except Exception as e:
            logger.critical(f"Problem saving {self} due to: {e}")
            self.__database_session__.rollback()
            report.add_result(Alert(msg=e, status="Critical"))
            return report

    @classmethod
    def pydantic_model(cls, pyd_model_name: str | None = None, **kwargs) -> Any:
        """
        Gets the pydantic model corresponding to this object.

        Returns:
            Pydantic model with name "Pyd{cls.__name__}"
        """
        from backend.validators import pydant
        if not pyd_model_name:
            try:
                pyd_model_name = f"Pyd{cls.pyd_model_name}"
            except AttributeError:
                pyd_model_name = f"Pyd{cls.__name__}"
        try:
            model = getattr(pydant, pyd_model_name)
        except AttributeError:
            # logger.error(f"Couldn't get {pyd_model_name} pydantic model. Falling back to declared pyd_model_name")
            # try:
            #     model = getattr(pydant, f"Pyd{cls.pyd_model_name}")
            # except AttributeError:
            logger.error(f"Could get model {pyd_model_name}, returning None")
            return None
        return model

    @declared_attr
    @classmethod
    def details_template(cls):
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Tuple(dict, Template): (Updated dictionary, Template to be rendered)
        """
        env = jinja_template_loading()
        temp_name = f"{cls.query_alias}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
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
        for key, value in attributes.items():
            if value.lower() == "none":
                value = None
            self_value = getattr(self, key)
            class_attr = getattr(self.__class__, key)
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
                    try:
                        self_value = self_value.name
                    except AttributeError:
                        pass
                    if class_attr.property.uselist:
                        self_value = self_value.__str__()
            try:
                check = issubclass(self_value.__class__, self.__class__)
            except TypeError as e:
                logger.error(f"Couldn't check if {self_value.__class__} is subclass of {self.__class__} due to {e}")
                check = False
            if check:
                self_value = self_value.name
            if self_value != value:
                # output = False
                return False
        return True

    def __setattr__(self, key, value):
        """
        Custom dunder method to handle potential list relationship issues.
        __setattr__ is called before property.setter methods.
        """
        if key.startswith("_"):
            return super().__setattr__(key, value)
        # NOTE: if attribute not found in this object, value gets shoved in to misc_info
        try:
            inspect.getattr_static(self.__class__, key)
            class_has_attr = True
        except AttributeError:
            class_has_attr = False
        # NOTE: if attribute not found in this object, value gets shoved into misc_info
        if not class_has_attr:
            # NOTE: ensure value is json serializable.
            try:
                value = json.dumps(value)
            except TypeError as e:
                logger.error(f"Error json dumping value {key}: {value}: {e}")
                value = str(value)
            try:
                self._misc_info.update({key: value})
            except AttributeError:
                self._misc_info = {key: value}
            return
        else:
            try:
                super().__setattr__(key, value)
                # print(self.__dict__)
            except AttributeError:
                raise AttributeError(f"Can't set {key} to {value}")

    def delete(self, **kwargs):
        logger.error(f"Delete has not been implemented for {self.__class__.__name__}")

    def rectify_query_date(input_date: datetime, eod: bool = False) -> str:
        """
        Converts input into a datetime string for querying purposes

        Args:
            eod (bool, optional): Whether to use max time to indicate end of day. Defaults to False.
            input_date (datetime): Input date to convert.

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

    @classmethod
    def correct_details_fields(cls, value) -> Any:
        """
        Corrects fields in details_dict to proper types.

        Args:
            value: input value
        Returns:
            Any: corrected value
        """
        from backend.validators.pydant import PydBaseClass
        match value:
            case str():
                return value.strip('\"')
            case list():
                return [cls.correct_details_fields(v) for v in value]
            case dict():
                return {k: cls.correct_details_fields(v) for k, v in value.items()}
            case x if issubclass(value.__class__, BaseClass):
                return value.name
            case x if issubclass(value.__class__, PydBaseClass):
                return value.name
            case _:
                return value
    
    def details_dict(self, **kwargs) -> dict:
        """
        Primary method for getting BaseClass subclasses as dictionaries

        Args:
            **kwargs:

        Returns:
            dict():
        """
        relevant = {k: v for k, v in self.__class__.__dict__.items() if
                    isinstance(v, InstrumentedAttribute) or isinstance(v, AssociationProxy)}
        excluded=["excluded", "misc_info", "_misc_info", "id"]
        output = dict()
        for k, v in relevant.items():
            if k in excluded:
                continue
            # NOTE: foreign keys handled in child overrides.
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
            output[k.strip("_")] = self.correct_details_fields(value)
        if self._misc_info:
            for key, value in self._misc_info.items():
                if key in excluded:
                    continue
                output[key] = self.correct_details_fields(value)
        return output

    @classmethod
    def clean_details_for_render(cls, dictionary) -> dict:
        """
        Cleans dictionary for rendering.

        Args:
            dictionary: input dictionary

        Returns:
            dict: cleaned dictionary
        """
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
                        continue
                case _:
                    pass
            output[k] = value
        return output

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs) -> BaseModel:
        pyd = self.pydantic_model(pyd_model_name=pyd_model_name)
        details = self.details_dict(**kwargs)
        return pyd(**details)

    def show_details(self, obj):
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        dlg.exec()

    def export(self, obj, output_filepath: str | Path | None = None):
        from backend import managers
        Manager = getattr(managers, f"Default{self.__class__.__name__}")
        manager = Manager(parent=obj, input_object=self)

    @classmethod
    def find_subclasses(cls, class_name: str|None=None, class_alias: str|None=None) -> BaseClass | List[BaseClass] | None:
        if class_name:
            object_ = next((cl for cl in BaseClass.__subclasses__() if cl.__name__.lower() == class_name.lower().strip("_")), None)
            return object_
        elif class_alias:
            object_ = next((cl for cl in BaseClass.__subclasses__() if class_alias.lower().strip("_") in cl.aliases), None)
            return object_
        else:
            return BaseClass.__subclasses__()


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


# NOTE: import order must go: orgs, procedure, submissions due to circular import issues
from .audit import AuditLog
from .organizations import (
    ClientLab, Contact, BaseClass # NOTE: For some reason I  need to import BaseClass at this point for queries to work.
)
from .procedures import (
    ReagentRole, Reagent, ReagentLot, Discount, SubmissionType, ProcedureType, Procedure, ProcedureTypeReagentRoleAssociation,
    ProcedureReagentLotAssociation, EquipmentRole, Equipment, EquipmentRoleEquipmentAssociation, Process, ProcessVersion,
    Tips, TipsLot, ProcedureEquipmentAssociation, ProcedureTypeEquipmentRoleAssociation, Results, ReagentRoleReagentAssociation,
    ResultsType
)
from .submissions import (
    ClientSubmission, Run, Sample, ClientSubmissionSampleAssociation, RunSampleAssociation, ProcedureSampleAssociation
)
# from .controls import ControlType, Control

# NOTE: Add a creator to the procedure for reagent association. Assigned here due to circular import constraints.
# https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html#sqlalchemy.ext.associationproxy.association_proxy.params.creator
# Procedure.reagents.creator = lambda reg: ProcedureReagentAssociation(reagent=reg)
