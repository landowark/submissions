"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import sys, logging, json, inspect
from datetime import datetime, date, timedelta
from pprint import pformat
from dateutil.parser import parse
from jinja2 import TemplateNotFound
from pandas import DataFrame
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP, FLOAT
from sqlalchemy.ext.associationproxy import AssociationProxy, _AssociationList
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session, InstrumentedAttribute, ColumnProperty, RelationshipProperty
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
        # Filter kwargs into those that map to SQLAlchemy-mapped attributes
        # (InstrumentedAttribute) or hybrid properties and those that don't.
        # Unknown kwargs will be stored in self._misc_info so callers can
        # pass arbitrary data without raising TypeError from the Declarative
        # base __init__.
        allowed = set()
        for name in dir(self.__class__):
            try:
                attr = getattr(self.__class__, name)
            except Exception:
                continue
            # InstrumentedAttribute covers mapped columns/relationships
            if isinstance(attr, InstrumentedAttribute) or isinstance(attr, hybrid_property):
                allowed.add(name)
        # Keep internal allowed names
        allowed.update({'_misc_info'})

        valid_kwargs = {k: v for k, v in kwargs.items() if k in allowed}
        misc_kwargs = {k: v for k, v in kwargs.items() if k not in valid_kwargs}

        # Call SQLAlchemy / Declarative __init__ only with valid kwargs
        super().__init__(*args, **valid_kwargs)

        # Ensure _misc_info exists and merge misc kwargs into it
        try:
            if self._misc_info is None:
                self._misc_info = {}
        except AttributeError:
            self._misc_info = {}
        if misc_kwargs:
            # merge misc kwargs (overwrites existing misc keys if present)
            self._misc_info.update(misc_kwargs)

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
        query_kwargs = {k: v for k, v in kwargs.items() if k in allowed and not isinstance(v, list)}
        # NOTE: outside kwargs will be reintroduced into misc_info
        # outside_kwargs = {k: v for k, v in kwargs.items() if k not in allowed}
        if "name" in query_kwargs.keys():
            query_kwargs = dict(name=query_kwargs.get("name"))
        instance = cls.query(limit=1, **query_kwargs)
        if not instance or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in kwargs.items():
            if k == "id":
                continue
            # NOTE: Setattr used to make use of overridden method.
            # logger.debug(f"Setting {cls.__qualname__} {k} to {v}")
            try:
                setattr(instance, k, v)
            except AttributeError:
                continue
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
            # Handle when the value provided is an instance of a BaseClass
            # If the instance hasn't been persisted (no id), comparing the
            # relationship directly will raise StatementError because SQLAlchemy
            # can't resolve the primary key value. In that case try to match
            # on a sensible alternative (usually 'name') using .has / .any.
            if isinstance(v, BaseClass):
                obj_pk = getattr(v, "id", None)
                is_rel = isinstance(getattr(attr, "property", None), RelationshipProperty)

                # If it's a relationship property, prefer .has / .any when no pk
                if is_rel:
                    related_cls = attr.property.mapper.class_
                    # If object has a primary key, we can compare directly
                    if obj_pk is not None:
                        try:
                            if check:
                                query = query.filter(attr.contains(v))
                            else:
                                query = query.filter(attr == v)
                        except ArgumentError:
                            pass
                    else:
                        # Try to match by name if available to avoid StatementError
                        obj_name = getattr(v, "name", None)
                        if obj_name is not None:
                            try:
                                if check:
                                    query = query.filter(attr.any(related_cls.name == obj_name))
                                else:
                                    query = query.filter(attr.has(name=obj_name))
                            except ArgumentError:
                                pass
                        else:
                            # Can't resolve the unsaved object; skip this filter
                            continue
                else:
                    # Not a relationship property (unlikely to be a BaseClass),
                    # fall back to attempting direct comparison if pk present.
                    if obj_pk is None:
                        # can't compare unresolved object, skip
                        continue
                    try:
                        query = query.filter(attr == v)
                    except ArgumentError:
                        continue
            else:
                # Non-instance values
                if check:
                    try:
                        query = query.filter(attr.contains(v))
                    except ArgumentError:
                        continue
                else:
                    if isinstance(v, list):
                        continue
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
            logger.critical(f"Problem objects: with {pformat([item for item in self.__database_session__.dirty])}")
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
            logger.error(f"Couldn't get model {pyd_model_name}, returning None")
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

    def check_all_attributes(self, **kwargs) -> bool:
        """
        Checks this instance against a dictionary of attributes to determine if they are a match.

        Args:
            attributes (dict): A dictionary of attributes to be check for equivalence

        Returns:
            bool: If a single unequivocal value is found will be false, else true.
        """
        """
        Compare instance attributes to provided expected values.

        Behavior / assumptions:
        - For attributes that are other BaseClass instances, compares using their
          `name` (or `id` if `name` missing).
        - For list-like relationship attributes, compares sets of stringified
          item identifiers (name/id) to be order-insensitive.
        - Accepts string inputs for expected values and attempts to coerce them
          to the type of the actual attribute when reasonable (int, float,
          bool, datetime).
        - Treats the string "none" (case-insensitive) as None.

        Returns True only if all provided attribute expectations match the
        instance values; returns False on the first mismatch.
        """
        def _as_identifier(val):
            """Return name or id for BaseClass-like objects, else the value itself."""
            try:
                if isinstance(val, BaseClass):
                    return getattr(val, "name", None) or getattr(val, "id", None)
            except Exception:
                pass
            return val

        def _normalize_expected(expected, actual):
            # Normalize simple string markers
            if isinstance(expected, str):
                s = expected.strip()
                if s.lower() == "none":
                    return None
                if s.lower() in ("true", "false") and isinstance(actual, bool):
                    return s.lower() == "true"
                # numeric coercion when actual type suggests it
                try:
                    if isinstance(actual, int) and "." not in s:
                        return int(s)
                    if isinstance(actual, float):
                        return float(s)
                    if isinstance(actual, (datetime, date)):
                        return parse(s)
                except Exception:
                    # leave as string if coercion fails
                    pass
            return expected

        for key, expected in kwargs.items():
            # pull actual value from attribute or misc_info if attribute not present
            try:
                self_value = getattr(self, key)
            except AttributeError:
                try:
                    self_value = self._misc_info.get(key)
                except Exception:
                    return False

            # Handle relationship lists / association proxies
            if isinstance(self_value, (_AssociationList, list, tuple)):
                # normalize collection to identifiers (name/id) and compare sets
                actual_set = {str(_as_identifier(v)) for v in self_value}
                if isinstance(expected, (list, tuple, set)):
                    expected_set = {str(_as_identifier(v)) for v in expected}
                else:
                    expected_set = {str(_as_identifier(expected))}
                if actual_set != expected_set:
                    return False
                else:
                    continue

            # If self_value is another BaseClass-like object, compare by identifier
            if isinstance(self_value, BaseClass):
                actual_id = _as_identifier(self_value)
                if isinstance(expected, BaseClass):
                    expected_id = _as_identifier(expected)
                else:
                    expected_id = expected
                expected_id = _normalize_expected(expected_id, actual_id)
                if actual_id != expected_id:
                    return False
                else:
                    continue

            # Normalize expected when possible based on actual type
            expected_norm = _normalize_expected(expected, self_value)

            # Final direct comparison (allowing for None)
            if self_value != expected_norm:
                return False

        return True

    def __setattr__(self, key, value):
        """
        Custom dunder method to handle potential list relationship issues.
        __setattr__ is called before property.setter methods.
        """
        if key == "_sa_instance_state":
            return super().__setattr__(key, value)
        elif key == "new":
            return
        # NOTE: if attribute not found in this object, value gets shoved in to misc_info
        try:
            attr = inspect.getattr_static(self.__class__, key)
            class_has_attr = True
        except AttributeError:
            attr = None
            class_has_attr = False
        # NOTE: if attribute not found in this object, value gets shoved into misc_info
        if not class_has_attr:
            # NOTE: ensure value is json serializable.
            try:
                value = json.dumps(value)
            except TypeError as e:
                # logger.error(f"Error json dumping value {key}: {value}: {e}")
                value = str(value)
            try:
                self._misc_info.update({key: value})
            except AttributeError:
                self._misc_info = {key: value}
            return
        else:
            # logger.debug(f"setting {self.__class__.__name__}.{key}: {value} of type {type(attr)}")
            # If the class attribute is a descriptor for a property (including
            # SQLAlchemy hybrid_property), calling super().__setattr__ may not
            # always trigger the descriptor's fset. Detect hybrid_property or
            # builtin property descriptors and call their fset directly so
            # property setters run when users call setattr(instance, name, val).
            try:
                # hybrid_property is imported in module scope above
                if isinstance(attr, (property, hybrid_property)):
                    setter = getattr(attr, 'fset', None)
                    # logger.debug(f"{key} setter method: {setter}")
                    if setter:
                        return setter(self, value)
            except Exception as e:
                # fall back to default behavior if detection fails
                logger.error(f"Unable to call setter for {self.__str__()}.{attr} due to {e}")
            try:
                return super().__setattr__(key, value)
                # print(self.__dict__)
            except AttributeError as e:
                if "association" in key:
                    logger.warning(f"Disallowing setting of association {key} automatically")
                else:
                    raise AttributeError(f"{self.__class__.__qualname__} Can't set {key} to {value} due to: {e}")

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
        # logger.debug(f"Correcting details: {value} of type {type(value)}")
        match value:
            case str():
                output = value.strip('\"')
            case list():
                output = [cls.correct_details_fields(v) for v in value]
            case dict():
                output = {k: cls.correct_details_fields(v) for k, v in value.items()}
            case x if issubclass(value.__class__, BaseClass):
                output = value.name
            case x if issubclass(value.__class__, PydBaseClass):
                output = value.name
            case _AssociationList():
                output = [cls.correct_details_fields(v) for v in value]
            # NOTE: datetime is a subclass of date, so the datetime() case
            # must come before date() to avoid matching datetimes as dates
            # (which would force end-of-day time).
            case datetime():
                output = datetime.strftime(value, "%Y-%m-%d %H:%M:%S")
            case date():
                output = datetime.combine(value, datetime.max.time())
                output = datetime.strftime(output, "%Y-%m-%d %H:%M:%S")
            case timedelta():
                output = value.days
            case _:
                logger.debug(f"Unmatched value type: {type(value)} for value: {value}")
                output = value
        # logger.debug(f"Corrected value: {value} to {output}")
        return output
    
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
        # excluded=["excluded", "misc_info", "_misc_info", "id"]
        output = dict(excluded=["excluded", "misc_info", "_misc_info", "id"])
        for k, v in relevant.items():
            if k in output['excluded']:
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
            corrected_value = self.correct_details_fields(value)
            # logger.debug(f"Setting {k} corrected value to {corrected_value} ")
            output[k.strip("_")] = corrected_value
        # logger.debug(f"Details dict output:\n{pformat(output)}")
        if self._misc_info:
            for key, value in self._misc_info.items():
                # logger.debug(f"Misc value: {key}: {value}")
                if key in output.keys():
                    continue
                if key.startswith("_"):
                    continue
                if key in output['excluded']:
                    continue
                output[key] = self.correct_details_fields(value)
        # logger.debug(f"Details dict output:\n{pformat(output)}")
        return output

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs) -> BaseModel:
        pyd = self.pydantic_model(pyd_model_name=pyd_model_name)
        details = self.details_dict(**kwargs)
        # logger.debug(f"Details dict output:\n{pformat(details)}")
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

    @classmethod
    def rank_sample(cls, sample, iii):
        sample.rank = iii
        return sample

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
