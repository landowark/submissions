"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import sys, logging, json, inspect
from datetime import datetime, date
from pprint import pformat
from dateutil.parser import parse
from jinja2 import TemplateNotFound, Template
from pandas import DataFrame
from pydantic import BaseModel
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP
from sqlalchemy.ext.associationproxy import AssociationProxy
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session, InstrumentedAttribute, ColumnProperty
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.exc import ArgumentError
from typing import Any, List, ClassVar
from pathlib import Path
from sqlalchemy.orm.relationships import _RelationshipDeclared
from tools import report_result, list_sort_dict, jinja_template_loading, Report, Alert, ctx

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


    @declared_attr
    @classmethod
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
        return f"_{cls.__name__.lower()}"

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
    def get_omni_sort(cls):
        output = [item[0] for item in inspect.getmembers(cls, lambda a: not (inspect.isroutine(a)))
                  if isinstance(item[1], InstrumentedAttribute)]  # and not isinstance(item[1].property, _RelationshipDeclared)]
        output = [item for item in output if item not in ['_misc_info']]
        return output

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
        new = False
        allowed = [k for k, v in cls.__dict__.items() if
                   isinstance(v, InstrumentedAttribute) or isinstance(v, hybrid_property)]
        sanitized_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        outside_kwargs = {k: v for k, v in kwargs.items() if k not in allowed}
        instance = cls.query(limit=1, **sanitized_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in sanitized_kwargs.items():
            if k == "id":
                continue
            try:
                setattr(instance, k, v)
            except AttributeError as e:
                from backend.validators.pydant import PydBaseClass
                if issubclass(v.__class__, PydBaseClass):
                    setattr(instance, k, v.to_sql())
        instance._misc_info.update(outside_kwargs)
        # logger.info(f"Instance from query or create: {instance}, new: {new}")
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
            model (Any, optional): model to be queried, allows for plugging in. Defaults to None
            query (Query, optional): input query object. Defaults to None
            limit (int): Maximum number of results. (0 = all). Defaults to 0

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

    @property
    def omnigui_instance_dict(self) -> dict:
        """
        For getting any object in an omni-thing friendly output.

        Returns:
            dict: Dictionary of object minus _sa_instance_state with id at the front.
        """
        dicto = {key: dict(class_attr=getattr(self.__class__, key), instance_attr=getattr(self, key))
                 for key in self.get_omni_sort()}
        for k, v in dicto.items():
            try:
                v['instance_attr'] = v['instance_attr'].name
            except AttributeError:
                continue
        try:
            dicto = list_sort_dict(input_dict=dicto, sort_list=self.__class__.get_omni_sort())
        except TypeError as e:
            logger.error(f"Could not sort {self.__class__.__name__} by list due to :{e}")
        try:
            dicto = {'id': dicto.pop('id'), **dicto}
        except KeyError:
            pass
        return dicto

    @declared_attr
    @classmethod
    def pydantic_model(cls):
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
            try:
                model = getattr(pydant, f"Pyd{cls.pyd_model_name}")
            except AttributeError:
                return pydant.PydElastic
        return model

    # @classproperty
    @declared_attr
    @classmethod
    def add_edit_tooltips(cls):
        """
        Gets tooltips for Omni-add-edit

        Returns:
            dict: custom dictionary for this class.
        """
        return dict()

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
        temp_name = f"{cls.__name__.lower()}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            # logger.error(f"Couldn't find template {e}")
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
                output = False
                return output
        return True

    def __setattr__(self, key, value):
        """
        Custom dunder method to handle potential list relationship issues.
        """
        if key.startswith("_"):
            return super().__setattr__(key, value)
        check = not hasattr(self, key)
        if check:
            try:
                value = json.dumps(value)
            except TypeError as e:
                logger.error(f"Error json dumping value: {e}")
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
            match field_type.property:
                case ColumnProperty():

                    return super().__setattr__(key, value)
                case _RelationshipDeclared():
                    if field_type.property.uselist:
                        existing = self.__getattribute__(key)
                        # NOTE: This is causing problems with removal of items from lists. Have to overhaul it.
                        if existing is not None:
                            if isinstance(value, list):
                                value = value
                            else:
                                value = existing + [value]
                        else:
                            if isinstance(value, list):
                                pass
                            else:
                                value = [value]
                        try:
                            value = list(set(value))
                        except TypeError:
                            pass
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
            try:
                return super().__setattr__(key, value)
            except AttributeError:
                raise AttributeError(f"Can't set {key} to {value}")

    def delete(self, **kwargs):
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

    def details_dict(self, **kwargs) -> dict:

        relevant = {k: v for k, v in self.__class__.__dict__.items() if
                    isinstance(v, InstrumentedAttribute) or isinstance(v, AssociationProxy)}
        output = dict(excluded=["excluded", "misc_info", "_misc_info", "id", "background_color"])
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
                case str():
                    value = value.strip('\"')
                case _:
                    pass
            output[k.strip("_")] = value
        if self._misc_info:
            for key, value in self._misc_info.items():
                output[key] = value
        return output

    @classmethod
    def clean_details_for_render(cls, dictionary):
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
                case x if issubclass(value.__class__, cls):
                    try:
                        value = value.name
                    except AttributeError:
                        continue
                case _:
                    pass
            output[k] = value
        return output

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs):
        from backend.validators import pydant
        if not pyd_model_name:
            pyd_model_name = f"Pyd{self.__class__.__name__}"
        # logger.info(f"Looking for pydant model {pyd_model_name}")
        try:
            pyd = getattr(pydant, pyd_model_name)
        except AttributeError:
            raise AttributeError(f"Could not get pydantic class {pyd_model_name}")
        pyd.model_rebuild()
        return pyd(**self.details_dict(**kwargs))

    def show_details(self, obj):
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, sub=self)
        if dlg.exec():
            pass

    def export(self, obj, output_filepath: str | Path | None = None):
        from backend import managers
        Manager = getattr(managers, f"Default{self.__class__.__name__}")
        manager = Manager(parent=obj, input_object=self)


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


# NOTE: import order must go: orgs, kittype, run due to circular import issues
from .audit import AuditLog
from .organizations import (
    ClientLab, Contact, BaseClass # NOTE: For some reason I  need to import BaseClass at this point for queries to work.
)
from .procedures import (
    ReagentRole, Reagent, ReagentLot, Discount, SubmissionType, ProcedureType, Procedure, ProcedureTypeReagentRoleAssociation,
    ProcedureReagentLotAssociation, EquipmentRole, Equipment, EquipmentRoleEquipmentAssociation, Process, ProcessVersion,
    Tips, TipsLot, ProcedureEquipmentAssociation, ProcedureTypeEquipmentRoleAssociation, Results
)
from .submissions import (
    ClientSubmission, Run, Sample, ClientSubmissionSampleAssociation, RunSampleAssociation, ProcedureSampleAssociation
)
from .controls import ControlType, Control

# NOTE: Add a creator to the procedure for reagent association. Assigned here due to circular import constraints.
# https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html#sqlalchemy.ext.associationproxy.association_proxy.params.creator
# Procedure.reagents.creator = lambda reg: ProcedureReagentAssociation(reagent=reg)
