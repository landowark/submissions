"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import re, sys, logging, json, inspect
from datetime import datetime, date, timedelta
from dateutil.parser import parse
from jinja2 import Template, TemplateNotFound
from pandas import DataFrame
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP, inspect as sql_inspect
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.ext.associationproxy import AssociationProxy, _AssociationList, AssociationProxyExtensionType
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session, ColumnProperty, RelationshipProperty, reconstructor
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.exc import ArgumentError
from typing import Any, List, ClassVar, Tuple, TYPE_CHECKING
from pathlib import Path
from tools import report_result, jinja_template_loading, Report, Alert, ctx
if TYPE_CHECKING:
    from pydantic import BaseModel
    from backend.validators import PydSample

# NOTE: Load testing environment
if 'pytest' in sys.modules:
    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

# NOTE: For inheriting in LogMixin
Base: DeclarativeMeta = declarative_base()

logger = logging.getLogger(f"submissions.{__name__}")


class SafeMiscInfo(MutableDict, dict):

    """
    Dictionary wrapper for misc_info to ensure values are sanitized for JSON storage 
    and to prevent key conflicts with actual model fields. 
    Values set on this dict will be automatically sanitized using the parent model's 
    sanitize_obj_for_json method if available, and keys that conflict with SQLAlchemy-mapped 
    field names will be ignored to prevent issues with attribute access and querying.
    """

    def __init__(self, *args, owner: BaseClass | None = None, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self._owner = owner

    def _set_safe_item(self, key, value):
        if self._owner and key.replace("_", "").lower() in self._owner.sqlalchemy_fields:
            logger.warning(f"Key {key} in misc_info conflicts with existing field name. Skipping.")
            return
        safe_value = self._owner.sanitize_obj_for_json(value) if self._owner else value
        dict.__setitem__(self, key, safe_value)

    def __setitem__(self, key, value):
        self._set_safe_item(key, value)
        self.changed()

    def update(self, *args, **kwargs):
        merged = dict(*args, **kwargs)
        for key, value in merged.items():
            self._set_safe_item(key, value)
        self.changed()


class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.
    """
    __abstract__ = True  #: NOTE: Will not be added to DB as a table

    __table_args__ = {'extend_existing': True}  #: NOTE Will only add new columns

    singles = ['id']

    _misc_info = Column(MutableDict.as_mutable(JSON))

    def __repr__(self) -> str:
        try:
            return f"<{self.__class__.__name__}({self.name})>"
        except AttributeError:
            return f"<{self.__class__.__name__}(Name Unavailable)>"

    def _wrap_misc_info(self):
        try:
            if self._misc_info is None:
                self._misc_info = SafeMiscInfo(owner=self)
            elif isinstance(self._misc_info, SafeMiscInfo):
                self._misc_info._owner = self
            else:
                self._misc_info = SafeMiscInfo(self._misc_info, owner=self)
        except AttributeError:
            self._misc_info = SafeMiscInfo(owner=self)

    @reconstructor
    def init_on_load(self):
        self._wrap_misc_info()

    @hybrid_property
    def misc_info(self) -> dict:
        return self._misc_info
    
    # NOTE: Placeholder setter for now, but allows for future validation or transformation of misc_info values if desired.
    @misc_info.setter
    def misc_info(self, value):
        if not isinstance(value, dict):
            logger.warning(f"Attempted to set misc_info to non-dict value: {value}. Ignoring.")
            return
        self._misc_info = SafeMiscInfo(owner=self)
        self._misc_info.update(value)

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

    @declared_attr
    @classmethod
    def __tablename__(cls) -> str:
        """
        Sets table name to lower case class name.

        Returns:
            str: lower case class name
        """
        return f"_{cls.query_alias}"

    @classproperty
    def __database_session__(cls) -> Session:
        """
        Pull db session from ctx to be used in operations

        Returns:
            Session: DB session from ctx settings.
        """
        return ctx.database_session

    @classproperty
    def __directory_path__(cls) -> Path:
        """
        Pull directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions directory in Settings object
        """
        return ctx.directory_path

    @classproperty
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
        super().__init__(**valid_kwargs)
        # Ensure _misc_info exists and is wrapped in the safe dict type
        self._wrap_misc_info()
        if misc_kwargs:
            self._misc_info.update(misc_kwargs)

    @classproperty
    def jsons(cls):
        """
        Get list of JSON db columns

        Returns:
            List[str]: List of column names
        """
        try:
            return [item.name for item in cls.__table__.columns if isinstance(item.type, JSON)]
        except AttributeError:
            if not cls.__qualname__ == "BaseClass":
                logger.error(f"Could not get timestamps due to {e}")
            return []
        
    @classproperty
    def timestamps(cls):
        """
        Get list of TIMESTAMP columns

        Returns:
            List[str]: List of column names
        """
        try:
            return [item.name.strip("_") for item in cls.__table__.columns if isinstance(item.type, TIMESTAMP)]
        except AttributeError as e:
            if not cls.__qualname__ == "BaseClass":
                logger.error(f"Could not get timestamps due to {e}")
            return []

    @classproperty
    def sqlalchemy_fields(cls) -> List[str]:
        """
        Get list of SQLAlchemy mapped field names for this model.

        Returns:
            List[str]: List of column and relationship attribute names
        """
        try:
            mapper = sql_inspect(cls)
            column_names = [attr.key for attr in mapper.column_attrs]
            relationship_names = [rel.key for rel in mapper.relationships]
            sqls = sorted(set(column_names + relationship_names))
            return [item.replace("_id", "").replace("_name", "").replace("_", "") for item in sqls]
        except Exception as e:
            if cls.__qualname__ != "BaseClass":
                logger.debug(f"Could not inspect SQLAlchemy fields for {cls.__name__}: {e}")
            return []

    def _serialize_misc_value(self, value):
        """
        Attempt to coerce a value into a JSON-serializable form.

        Returns the original value when already serializable, or a
        converted representation (str, isoformat, integer) for common
        non-serializable types. Raises TypeError if it cannot be
        coerced.
        """
        # First, quick test for serializability
        try:
            json.dumps(value)
            return value
        except TypeError:
            pass
        # Handle some common non-serializable types
        try:
            if isinstance(value, datetime):
                return value.strftime("%Y-%m-%dT%H:%M:%S")
            if isinstance(value, date):
                return value.strftime("%Y-%m-%d")
            if isinstance(value, timedelta):
                return value.days
        except Exception:
            # fall through to other heuristics
            pass
        # If it's a BaseClass-like instance, prefer name/id when available
        try:
            if issubclass(value.__class__, BaseClass):
                return getattr(value, "name", None) or getattr(value, "id", None) or str(value)
        except Exception:
            pass
        # As a last resort, try to convert to string. If that fails, raise.
        try:
            return str(value)
        except Exception:
            raise TypeError(f"Value of type {type(value)} is not JSON serializable")

    @classmethod
    def determine_field_type(cls, field: str, is_new: bool = False) -> str:
        """Determines which type of field to use in the form.

        Args:
            field (str): Field name

        Returns:
            str: Type name
        """       
        def handle_instrument_attr(type_):
            type_ = type_.property
            type_name = type_.__class__.__name__
            if type_name == "_RelationshipDeclared":
                if type_.uselist:
                    type_name = "RelationshipList"
                else:
                    type_name = "RelationshipScalar"
            else:
                type_name = type_.expression.type.__str__()
            return type_name
        try: 
            type_ = getattr(cls, field.lower().strip("_"))
        except TypeError:
            return "Invalid"
        type_name = type_.__class__.__name__
        match type_name:
            case "hybrid_propertyProxy":
                try:
                    type_ = getattr(cls, type_.property.key)
                except AttributeError:
                    type_ = getattr(cls, f"_{field}") # Dicey workaround for hybrid_property with underscore
                type_name = type_.__class__.__name__
                if type_name == "InstrumentedAttribute":
                    type_name = handle_instrument_attr(type_=type_)
                if type_name == "ObjectAssociationProxyInstance":
                    if is_new:
                        type_name = "SKIPPED"
            case "ObjectAssociationProxyInstance":
                if is_new:
                    type_name = "SKIPPED"
            case "InstrumentedAttribute":
                type_name = handle_instrument_attr(type_=type_)
            case _:
                logger.warning(f"Got unmatched type: {type_name} for field {field}.")
        type_name = re.sub(r"\(.*\)", "", type_name)
        return type_name.upper()

    @classmethod
    def get_searchables(cls) -> List[str]:
        """
        List fields this class is searchable by.
        
        Returns: 
            List[str]: List of fields this class is searchable by.
        """
        output = []
        # NOTE: get only non-function attributes that are columns, not foreign keys, and of type String.
        for item in inspect.getmembers(cls, lambda a: not (inspect.isroutine(a))):
            if item[0] in ["_misc_info"]:
                continue
            if not isinstance(item[1], InstrumentedAttribute) and not isinstance(item[1], hybrid_property):
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
    def results_to_df(cls, objects: list | None = None) -> DataFrame:
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
            dicto = obj.details_dict
            records.append({key: value for key, value in dicto.items() if key not in dicto['excluded']})
        return DataFrame.from_records(records)

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[Any, bool]:
        """
        Gets existing object or creates new one.

        Args:
            **kwargs: field: value to query or add to crated instance.

        Returns:
            Tuple[Any, bool]: Object and whether or not it's new.
        """
        new = False
        # NOTE: ensure only valid fields are being used.
        allowed = [k for k, v in cls.__dict__.items() if
                   isinstance(v, InstrumentedAttribute) or isinstance(v, hybrid_property)] + ['value']
        query_kwargs = {k: v for k, v in kwargs.items() if k in allowed and not isinstance(v, list)}
        if "value" in query_kwargs.keys() and "name" not in query_kwargs.keys():
            query_kwargs["name"] = query_kwargs.get("value")
        # NOTE: if searching with 'name', only search with name.
        if "name" in query_kwargs.keys():
            query_kwargs = dict(name=query_kwargs.get("name"))
        instance = cls.query(limit=1, **query_kwargs)
        if instance is None or isinstance(instance, list):
            instance = cls()
            new = True
        for k, v in kwargs.items():
            if k == "id":
                continue
            # NOTE: Setattr used to make use of overridden method.
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
            # NOTE: determine which fields to limit to 1.
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
                obj_primarykey = getattr(v, "id", None)
                is_relationship = isinstance(getattr(attr, "property", None), RelationshipProperty)
                # If it's a relationship property, prefer .has / .any when no pk
                if is_relationship:
                    related_cls = attr.property.mapper.class_
                    # If object has a primary key, we can compare directly
                    if obj_primarykey is not None:
                        try:
                            # If the attribute is a list-like relationship, use contains; otherwise compare directly
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
                    if obj_primarykey is None:
                        # can't compare unresolved object, skip
                        continue
                    try:
                        query = query.filter(attr == v)
                    except ArgumentError:
                        continue
            else:
                # Non-instance values
                # NOTE: Recall check is true if attr.uselist
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
            if not isinstance(self._misc_info, SafeMiscInfo):
                self._misc_info = SafeMiscInfo(self._misc_info or {}, owner=self)
            items = list(self._misc_info.items())
        except AttributeError:
            items = []
        # Ensure values in misc_info are json serializable. Try to coerce
        # values where possible; drop keys that cannot be coerced.
        for key, value in items:
            try:
                json.dumps(value)
            except TypeError:
                try:
                    self._misc_info[key] = self.sanitize_obj_for_json(value)
                except TypeError:
                    del_keys.append(key)
        for dk in del_keys:
            try:
                del self._misc_info[dk]
            except Exception:
                pass
        try:
            self.__database_session__.add(self)
            self.__database_session__.commit()
        except Exception as e:
            logger.critical(f"Problem saving {self} due to: {e}")
            self.__database_session__.rollback()
            report.add_result(Alert(msg=e, status="Critical"))
            return report

    @classmethod
    def pydantic_model(cls, pyd_model_name: str | None = None) -> Any:
        """
        Gets the pydantic model corresponding to this object.

        Args:
            pyd_model_name (str, optional): Name of the pydantic model to be used. Defaults to None

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
            logger.error(f"Couldn't get model {pyd_model_name}, returning None")
            return None
        return model

    @classproperty
    def details_template(cls) -> Template:
        """
        Get the details jinja template for the correct class

        Args:
            base_dict (dict): incoming dictionary of Submission fields

        Returns:
            Template: Template to be rendered
        """
        env = jinja_template_loading()
        temp_name = f"{cls.query_alias}_details.html"
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            template = env.get_template("details.html")
        return template
    
    def to_html(self, css_in: List[str| Path] | str = [], js_in: List[str | Path] | str = [],
                            **kwargs) -> str:
        """
        Creates an html string. Loads js and css files.

        Args:
            css_in (List[str| Path] | str): css files to be used. Default []
            js_in (List[str| Path] | str): js files to be used. Default []

        Returns:
            str: html code

        """
        details = {self.__class__.__name__.lower() : self.sanitize_obj_for_json(kwargs)}
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
        css_out = []
        for css in css_in:
            with open(css, "r") as f:
                css_out.append(f.read())
        js_out = []
        for js in js_in:
            with open(js, "r") as f:
                js_out.append(f.read())
        return self.details_template.render(css=css_out, js=js_out, **details)

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
        except AttributeError as e:
            attr = None
            class_has_attr = False
        # NOTE: if attribute not found in this object, value gets shoved into misc_info
        if not class_has_attr:
            # ensure value is json serializable (or coerce it)
            try:
                safe_value = self._serialize_misc_value(value)
            except TypeError:
                # Could not coerce to a JSON serializable form; skip storing
                return
            if not "sql_instance" in key:
                try:
                    try:
                        if self._misc_info is None:
                            super().__setattr__("_misc_info", {})
                    except AttributeError:
                        super().__setattr__("_misc_info", {})
                    self._misc_info.update({key: safe_value})
                except AttributeError:
                    super().__setattr__("_misc_info", {key: safe_value})
        else:
            # If the class attribute is a descriptor for a property (including
            # SQLAlchemy hybrid_property), calling super().__setattr__ may not
            # always trigger the descriptor's fset. Detect hybrid_property or
            # builtin property descriptors and call their fset directly so
            # property setters run when users call setattr(instance, name, val).
            current = getattr(self, key)
            try:
                # hybrid_property is imported in module scope above
                if isinstance(attr, (property, hybrid_property)):
                    setter = getattr(attr, 'fset', None)
                    if setter:
                        return setter(self, value)
            except Exception as e:
                # fall back to default behavior if detection fails
                logger.error(f"Unable to call setter for {self.__str__()}.{attr.__name__} due to {e}")
                return super().__setattr__(key, current)
            try:
                return super().__setattr__(key, value)
            except AttributeError as e:
                logger.error(f"{self.__class__.__qualname__} Can't set {key} to {value} due to: {e}")
                
    # @classmethod
    # def get_association_proxy_details(cls, field_name):
    #     """
    #     Retrieves details of a specific association proxy field.
    #     """
    #     mapper = sql_inspect(cls)
    #     descriptor = mapper.all_orm_descriptors.get(field_name)
    #     if isinstance(descriptor, AssociationProxy):
    #         # Initialize the descriptor
    #         descriptor.__get__(None, cls)
    #         return {
    #             "name": field_name,
    #             "target_attribute": descriptor.value_attr,
    #             "info": descriptor.__dict__
    #         }
    #     else:
    #         return None

    # @classmethod
    # def find_proxies_for_field(cls, field_name):
    #     """Finds proxies targeting a specific relationship and field."""
    #     mapper = sql_inspect(cls)
    #     for _, desc in mapper.all_orm_descriptors.items():
    #         descriptor = getattr(desc, "extension_type", None)
    #         match descriptor:
    #             case AssociationProxyExtensionType.ASSOCIATION_PROXY:
    #                 if desc.target_collection == field_name:
    #                     return desc.value_attr.strip("_")
    #             case _:
    #                 continue
    #     return 
    
    @classmethod
    def get_relationship_sqlclass(cls, key) -> BaseClass | None:
        """
        Finds BaseClass subclass with name == relationship.
        
        Args:
            key: relationship name to be searched for
        
        Returns: 
            BaseClass: Class bound to this relationship.
        """
        field_type = cls.determine_field_type(key)
        if "RELATIONSHIP" in field_type:
            return cls.find_subclasses(class_alias=key.strip("_"))
        return None
   
    def delete(self, **kwargs):
        logger.error(f"Delete has not been implemented for {self.__class__.__name__}")

    def rectify_query_date(input_date: datetime, eod: bool = False) -> str:
        """
        Converts input into a datetime string for querying purposes

        Args:
            input_date (datetime): Input date to convert.
            eod (bool, optional): Whether to use max time to indicate end of day. Defaults to False.

        Returns:
            str: properly formated datetime
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
    def sanitize_obj_for_json(cls, obj_, expand: bool=False) -> Any:
        """
        Cleans obj (generally a dict) for rendering on a template or storage as a json.

        Args:
            obj_: input object

        Returns:
            Any: cleaned object
        """
        from backend.validators.pydant import PydBaseClass
        match obj_:
            case datetime():
                return obj_.isoformat()
            case date():
                return datetime.combine(obj_, datetime.max.time()).isoformat()
            case timedelta():
                return obj_.days
            case list() | _AssociationList():
                return [cls.sanitize_obj_for_json(item, expand=expand) for item in obj_]
            case dict():
                return {k: cls.sanitize_obj_for_json(v, expand=expand) for k, v in obj_.items()}
            case x if issubclass(obj_.__class__, BaseClass):
                if not expand:
                    return cls.sanitize_obj_for_json(obj_.name)
                else:
                    return cls.sanitize_obj_for_json(obj_.details_dict, expand=expand)
            case x if issubclass(obj_.__class__, PydBaseClass):
                if not expand:
                    return cls.sanitize_obj_for_json(obj_.name)
                else:
                    return cls.sanitize_obj_for_json(obj_.improved_dict, expand=expand)
            case _:
                return obj_

    def details_dict_expand_fields(self, fields: List[str] | List[dict], visited: set | None = None) -> dict:
        """
        details_dict with additional information from relationships.
        
        Args:
            fields (List[str] | List[dict]): Fields (if ['a', 'b']) and subfields (if {'a': ['b']})
        
        Returns: 
            dict[Any, Any]
        """
        dict_ = self.details_dict
        if len(fields) == 0:
            return dict_
        for field in fields:
            match field:
                case str():
                    # NOTE: This is necessary... mostly because I'm too lazy to figure out how to simplify it.
                    # key = field
                    try:
                        value = getattr(self, field)
                    except AttributeError as e:
                        logger.error(f"Skipping {field} in {self} due to {e}")
                        continue
                    match value:
                        case InstrumentedAttribute():
                            output = getattr(self.sql_instance, field)
                        case _AssociationList():
                            output = []
                            for item in value.col:
                                dicto: dict = item.details_dict
                                target = getattr(item, field)
                                target = target.details_dict
                                target.update({k:v for k, v in dicto.items() if k !="name"})
                                if target['name'] not in [thing['name'] for thing in output]:
                                    output.append(target)
                        case InstrumentedList():
                            output = [item.details_dict for item in value]
                        case x if issubclass(value.__class__, BaseClass):
                            output = value.details_dict
                        case _:
                            continue
                case dict():
                    # NOTE: this handles recursions if fields is a dict.
                    new_fields = list(field.values())[0]
                    field = list(field.keys())[0]
                    
                    try:
                        value = getattr(self, field)
                    except AttributeError as e:
                        logger.error(f"Skipping {field} in {self} due to {e}")
                        continue
                    match value:
                        case _AssociationList():
                            output = [item.details_dict_expand_fields(new_fields) for item in value]
                            for item in value.col:
                                dicto: dict = item.details_dict_expand_fields(new_fields)
                                target = getattr(item, field)
                                target = target.details_dict_expand_fields(new_fields)
                                target.update({k:v for k, v in dicto.items() if k !="name"})
                                if target['name'] not in [thing['name'] for thing in output]:
                                    output.append(target)
                        case InstrumentedList():
                            output = [item.details_dict_expand_fields(new_fields) for item in value]
                        case x if issubclass(value.__class__, BaseClass):
                            output = value.details_dict
                        case _:
                            continue
                case _:
                    continue
            dict_[field] = output
        return dict_
    
    @property
    def details_dict(self) -> dict:
        """
        Primary method for getting BaseClass subclasses as dictionaries

        Returns:
            dict: All pertenant information about this instance.
        """
        relevant = {k: v for k, v in self.__class__.__dict__.items() if
                    isinstance(v, InstrumentedAttribute) or isinstance(v, AssociationProxy)}
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
            corrected_value = self.sanitize_obj_for_json(value)
            output[k.strip("_")] = corrected_value
        if self._misc_info:
            for key, value in self._misc_info.items():
                # NOTE don't update from misc_info
                if key in output.keys():
                    continue
                if key.startswith("_"):
                    continue
                if key in output['excluded']:
                    continue
                output[key] = self.sanitize_obj_for_json(value)
        if 'name' not in output.keys():
            output['name'] = self.name
        return output

    def to_pydantic(self, pyd_model_name: str | None = None, **kwargs) -> BaseModel:
        """
        Transforms this instance to the pydantic model.
        
        Args:
            pyd_model_name (str, optional): Name for any model other than f'pyd{cls.__name__} to be used. Defaults to None.
        
        Returns: 
            BaseModel: Pydantic representation of this object
        """
        pyd = self.pydantic_model(pyd_model_name=pyd_model_name)
        details = self.details_dict
        details['sql_instance'] = self
        return pyd(**details)

    def show_details(self, obj):
        """
        Shows details as html for this instance.
        
        Args:
            obj: Parent QWidget or QDialog
        """
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, object_ = self.to_pydantic())
        dlg.exec()

    @classmethod
    def find_subclasses(cls, class_name: str|None=None, class_alias: str|None=None) -> BaseClass | List[BaseClass] | None:
        """
        Finds BaseClass subclasses by a name or alias
        
        Args:
            class_name (str, optional): Name (i.e. cls.__name__.lower() of subclass of interest). Defaults to None.
            class_alias (str, optional): Alias set in class.
        
        Returns:
            BaseClass | List[BaseClass] | None
        """
        if class_name:
            object_ = next((cl for cl in BaseClass.__subclasses__() if cl.__name__.lower() == class_name.lower().strip("_")), None)
            return object_
        elif class_alias:
            object_ = next((cl for cl in BaseClass.__subclasses__() if class_alias.lower().strip("_") in cl.aliases), None)
            return object_
        else:
            return BaseClass.__subclasses__()

    @classmethod
    def rank_sample(cls, sample: PydSample, iii: int) -> PydSample:
        """
        Adds a rank to a sample in this class
        
        Args:
            sample (Sample): Sample to be amended.
            iii (int): Rank to be added to Sample. 
        """
        sample.rank = iii
        return sample


class LogMixin(Base):
    """
    Mixin to add auditlog tracking to a BaseModel subclass
    """
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
    ResultsType, ProcedureEquipmentTipslotAssociation
)
from .submissions import (
    ClientSubmission, Run, Sample, ClientSubmissionSampleAssociation, RunSampleAssociation, ProcedureSampleAssociation
)

# NOTE: Add a creator to the procedure for reagent association. Assigned here due to circular import constraints.
# https://docs.sqlalchemy.org/en/20/orm/extensions/associationproxy.html#sqlalchemy.ext.associationproxy.association_proxy.params.creator
# Procedure.reagents.creator = lambda reg: ProcedureReagentAssociation(reagent=reg)
