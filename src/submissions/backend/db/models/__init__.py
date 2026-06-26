"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import re, sys, logging, json, inspect
from datetime import datetime, date, timedelta
from dateutil.parser import parse
from sqlalchemy import Column, INTEGER, String, JSON, TIMESTAMP, inspect as sql_inspect
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.ext.associationproxy import AssociationProxy, _AssociationList
from sqlalchemy.orm import CompositeProperty, DeclarativeMeta, declarative_base, Query, Session, ColumnProperty, RelationshipProperty, reconstructor
from sqlalchemy.orm.attributes import InstrumentedAttribute, set_committed_value
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.exc import ArgumentError, IntegrityError, OperationalError, StatementError
from typing import Any, List, ClassVar, Tuple, TYPE_CHECKING
from pathlib import Path
from tools import report_result, Report, Alert, ctx
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
    Dictionary wrapper for misc_info to ensure values are sanitized for JSON storage.
    
    This class wraps a dictionary to ensure values are automatically sanitized for JSON 
    storage and to prevent key conflicts with actual model fields. Keys that conflict with 
    SQLAlchemy-mapped field names are ignored to prevent issues with attribute access and querying.
    
    Values set on this dict will be automatically sanitized using the parent model's 
    :meth:`sanitize_obj_for_json` method if available.
    
    :ivar _owner: The parent model instance that owns this dict.
    :vartype _owner: :class:`BaseClass` or None
    """

    _INTERNAL_MARKERS = ("AssociationProxy", "sa_instance_state", "_sa_")

    def __init__(self, *args, owner: BaseClass | None = None, **kwargs):
        """
        Initialize SafeMiscInfo dictionary.
        
        :param args: Positional arguments passed to dict constructor.
        :param owner: The parent model instance.
        :type owner: :class:`BaseClass` or None
        :param kwargs: Keyword arguments passed to dict constructor.
        """
        dict.__init__(self, *args, **kwargs)
        self._owner = owner

    def _is_internal_key(self, key) -> bool:
        if not isinstance(key, str):
            return False
        return key.startswith("_") or any(m in key for m in self._INTERNAL_MARKERS)

    def _set_safe_item(self, key: str, value):
        """
        Set a key-value pair with sanitization and conflict checking.
        
        Checks if the key conflicts with existing SQLAlchemy field names and sanitizes 
        the value for JSON storage using the owner model's sanitization method if available.
        
        :param key: Dictionary key to set.
        :type key: str
        :param value: Value to store, will be sanitized if owner is present.
        """
        if self._is_internal_key(key):
            return                                # silently drop ORM internals
        if self._owner and key.replace("_", "").lower() in self._owner.sqlalchemy_fields:
            logger.debug(f"Key {key} in misc_info shadows a mapped field; skipping.")  # was warning
            return
        safe_value = self._owner.sanitize_obj_for_json(value) if self._owner else value
        dict.__setitem__(self, key, safe_value)

    # def _set_safe_item(self, key: str, value):
        
    #     if self._owner and key.replace("_", "").lower() in self._owner.sqlalchemy_fields:
    #         logger.warning(f"Key {key} in misc_info conflicts with existing field name. Skipping.")
    #         return
    #     safe_value = self._owner.sanitize_obj_for_json(value) if self._owner else value
    #     dict.__setitem__(self, key, safe_value)

    def __setitem__(self, key: str, value):
        """
        Set item with automatic sanitization and tracking of changes.
        
        :param key: Dictionary key to set.
        :type key: str
        :param value: Value to store.
        """
        self._set_safe_item(key, value)
        self.changed()

    def update(self, *args, **kwargs):
        """
        Update dictionary with multiple items with automatic sanitization.
        
        :param args: Positional arguments passed to dict constructor.
        :param kwargs: Keyword arguments to update.
        """
        merged = dict(*args, **kwargs)
        for key, value in merged.items():
            self._set_safe_item(key, value)
        self.changed()


class BaseClass(Base):
    """
    Abstract base class for all SQLAlchemy models with context and utility methods.
    
    This class provides a foundation for all database models with features including:
    
    - Context management through :attr:`ctx` for database sessions and file paths
    - Miscellaneous info storage via :attr:`misc_info` for arbitrary key-value pairs
    - Query functionality via :meth:`query` and :meth:`execute_query`
    - Serialization support for JSON storage via :meth:`sanitize_obj_for_json`
    - Conversion to Pydantic models via :meth:`to_pydantic`
    - Details dictionary generation via :meth:`details_dict`
    
    This is an abstract class and should not be instantiated directly.
    
    :ivar singles: List of field names that should be limited to a single result in queries.
    :vartype singles: list
    :ivar _misc_info: Mutable dictionary for storing arbitrary data.
    :vartype _misc_info: dict
    """
    __abstract__ = True  #: NOTE: Will not be added to DB as a table

    __table_args__ = {'extend_existing': True}  #: NOTE Will only add new columns

    # singles = ['id', 'name']

    _misc_info = Column(MutableDict.as_mutable(JSON))

    def __repr__(self) -> str:
        """
        Return string representation of this object.
        
        Uses the object's name attribute if available, otherwise returns a generic representation.
        
        :return: String representation in the format ``<ClassName(name)>``.
        :rtype: str
        """
        try:
            return f"<{self.__class__.__name__}({self.name})>"
        except AttributeError:
            return f"<{self.__class__.__name__}(Name Unavailable)>"

    def _wrap_misc_info(self):
        """
        Wrap or initialize the _misc_info attribute as a SafeMiscInfo instance.
        
        Ensures that _misc_info is properly initialized as a SafeMiscInfo dictionary 
        with this object set as the owner. Called during object initialization and 
        reconstruction from the database.
        """
        try:
            raw_misc = object.__getattribute__(self, "_misc_info")
        except AttributeError:
            raw_misc = None
        if raw_misc is None or isinstance(raw_misc, Column):
            self._misc_info = SafeMiscInfo(owner=self)
        elif isinstance(raw_misc, SafeMiscInfo):
            raw_misc._owner = self
        else:
            self._misc_info = SafeMiscInfo(raw_misc, owner=self)

    @reconstructor
    def init_on_load(self):
        raw = self.__dict__.get("_misc_info")
        if isinstance(raw, SafeMiscInfo):
            raw._owner = self
        else:
            # committed value -> loaded row is not marked dirty -> no spurious UPDATE/flush
            set_committed_value(self, "_misc_info", SafeMiscInfo(raw or {}, owner=self))

    @hybrid_property
    def misc_info(self) -> dict:
        """
        Get the miscellaneous info dictionary for this object.
        
        :return: Dictionary containing arbitrary key-value pairs stored as misc info.
        :rtype: dict
        """
        return self._misc_info
    
    @misc_info.setter
    def misc_info(self, value):
        """
        Set the miscellaneous info dictionary for this object.
        
        :param value: Dictionary to store as misc info. Must be a dict type.
        :type value: dict
        
        .. note::
           If a non-dict value is provided, it will be ignored with a warning logged.
        """
        if not isinstance(value, dict):
            logger.warning(f"Attempted to set misc_info to non-dict value: {value}. Ignoring.")
            return
        if not isinstance(self._misc_info, SafeMiscInfo):
            self._misc_info = SafeMiscInfo(owner=self)
        self._misc_info.update(value)

    @classproperty
    def aliases(cls) -> List[str]:
        """
        Get list of other names this class might be known by.
        
        Returns the list of aliases used for querying this class type. Useful for 
        providing alternative names for the model.

        :return: List of alias names, including at minimum the query_alias.
        :rtype: list[str]
        """
        return [cls.query_alias]

    @classproperty
    def query_alias(cls) -> str:
        """
        Get the primary alias or name used for querying this class.
        
        Returns the lowercase version of the class name, used as the primary 
        identifier for database queries.

        :return: Lowercase class name to use in queries.
        :rtype: str
        """
        return cls.__name__.lower()

    @declared_attr
    @classmethod
    def __tablename__(cls) -> str:
        """
        Get the database table name for this model.
        
        Automatically sets the table name to an underscore-prefixed lowercase 
        version of the class name.

        :return: Table name in format ``_<query_alias>``.
        :rtype: str
        """
        return f"_{cls.query_alias}"

    @classproperty
    def __database_session__(cls) -> Session:
        """
        Get the current database session for this model.
        
        Retrieves the active SQLAlchemy database session from the application context.
        Used internally for all database operations.

        :return: Active SQLAlchemy database session from application settings.
        :rtype: :class:`sqlalchemy.orm.Session`
        """
        return ctx.database.session

    @classproperty
    def __directory_path__(cls) -> Path:
        """
        Get the main submissions directory path from application context.
        
        Retrieves the configuration setting for the primary data directory.

        :return: Location of the main Submissions directory from Settings object.
        :rtype: :class:`pathlib.Path`
        """
        return Path(ctx.directories.main)

    @classproperty
    def __backup_path__(cls) -> Path:
        """
        Get the backup directory path from application context.
        
        Retrieves the configuration setting for the backup data directory.

        :return: Location of the Submissions backup directory from Settings object.
        :rtype: :class:`pathlib.Path`
        """
        return Path(ctx.directories.backup)

    def __init__(self, *args, **kwargs):
        """
        Initialize a BaseClass instance.
        
        Separates known SQLAlchemy-mapped attributes from arbitrary keyword arguments.
        Known attributes are passed to the parent class, while unknown kwargs are stored 
        in the misc_info dictionary.
        
        :param args: Positional arguments (unused).
        :param kwargs: Keyword arguments. Known attributes are used for model initialization,
                       while unknown attributes are stored in misc_info.
        """
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
    def jsons(cls) -> List[str]:
        """
        Get list of JSON database columns for this model.

        Inspects the table schema and returns all columns with JSON type.

        :return: List of JSON column names. Empty list if table doesn't exist.
        :rtype: list[str]
        """
        try:
            return [item.name for item in cls.__table__.columns if isinstance(item.type, JSON)]
        except AttributeError as e:
            if not cls.__qualname__ == "BaseClass":
                logger.error(f"Could not get timestamps due to {e}")
            return []
        
    @classproperty
    def timestamps(cls) -> List[str]:
        """
        Get list of TIMESTAMP columns for this model.

        Inspects the table schema and returns all columns with TIMESTAMP type,
        stripping leading underscores from column names.

        :return: List of timestamp column names. Empty list if table doesn't exist.
        :rtype: list[str]
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
        Get list of all SQLAlchemy mapped field names for this model.
        
        Returns all column names, relationship names, and hybrid property names
        that are defined for this model class.

        :return: Sorted list of unique field names (with prefixes removed).
        :rtype: list[str]
        """
        try:
            mapper = sql_inspect(cls)
            column_names = [attr.key for attr in mapper.column_attrs]
            relationship_names = [rel.key for rel in mapper.relationships]
            hybrid_names = []
            for base in cls.__mro__:
                for name, attr in base.__dict__.items():
                    if name == 'sqlalchemy_fields' or name.startswith("_"):
                        continue
                    if isinstance(attr, hybrid_property):
                        hybrid_names.append(name)
            sqls = sorted(set(column_names + relationship_names + hybrid_names))
            return list(set([item.replace("_id", "").replace("_name", "").strip("_") for item in sqls]))
        except Exception as e:
            if cls.__qualname__ != "BaseClass":
                logger.error(f"Could not inspect SQLAlchemy fields for {cls.__name__}: {e}")
            return []

    def _serialize_misc_value(self, value):
        """
        Serialize a value to a JSON-compatible form.
        
        Attempts to coerce a value into a JSON-serializable form. Returns the original 
        value if already serializable, or converts common types like datetime, date, 
        timedelta, and BaseClass instances to JSON-compatible representations.

        :param value: Value to serialize.
        :return: JSON-serializable version of the value.
        :rtype: any
        :raises TypeError: If the value cannot be coerced to a JSON-serializable form.
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
        """
        Determine the SQLAlchemy field type for a given field name.
        
        Inspects the model and returns the type name suitable for form generation,
        handling relationships, columns, and hybrid properties.

        :param field: Field name to inspect (case-insensitive).
        :type field: str
        :param is_new: Whether this is a new record. Some field types 
                       are skipped for new records. Defaults to False.
        :type is_new: bool
        :return: Uppercase type name (e.g., 'STRING', 'INTEGER', 'RELATIONSHIPLIST', 'SKIPPED').
        :rtype: str
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
        Get list of fields this model is searchable by.
        
        Returns only non-function attributes that are String columns and not foreign keys.
        These fields are suitable for full-text or fuzzy search operations.
        
        :return: List of searchable field names.
        :rtype: list[str]
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
        Get default metadata information for this model.
        
        Returns default configuration including singleton fields that should be 
        limited to single results in queries.

        :param args: Variable-length argument list containing keys to extract 
                     (e.g., 'singles' to get singleton field names).
        :return: Dictionary of defaults or specific extracted value.
        :rtype: dict | list | str
        """
        # NOTE: singles is a list of fields that need to be limited to 1 result.
        return dict(singles=list(set(cls.singles + BaseClass.singles)))

    @classmethod
    def fuzzy_search(cls, **kwargs) -> List[Any]:
        """
        Perform a fuzzy search on this model using wildcard matching.
        
        Searches for records matching the given field patterns using SQL LIKE operators.
        Useful for user-friendly search interfaces and autocomplete functionality.

        :param kwargs: Field names mapped to search terms. Each field will be searched 
                       using percentage-wrapped wildcards (e.g., ``field='value'`` searches for 
                       ``%value%``).
        :return: List of matching model instances (max 50 results).
        :rtype: list[any]
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
    def _mapped_fields(cls) -> set[str]:
        """Names of columns, relationships and hybrid accessors on this model
        (inherited ones included)."""
        fields = set()
        # Collect instrumented attributes (columns, relationships) via getattr
        for name in dir(cls):
            try:
                attr = getattr(cls, name)
            except Exception:
                continue
            if isinstance(attr, InstrumentedAttribute):
                fields.add(name)
        # hybrid_property descriptors live on the class __dict__ (or base classes)
        # and may not be detectable via getattr(cls, name) at runtime because
        # SQLAlchemy replaces them with proxy objects. Inspect class dicts
        # directly to find the actual hybrid_property objects.
        for base in cls.__mro__:
            for name, attr in base.__dict__.items():
                try:
                    if isinstance(attr, hybrid_property):
                        fields.add(name)
                except Exception:
                    continue
        return fields

    @classmethod
    def _query_or_create_sample_link(cls, *, parent, parent_model, parent_lookup,
                                 query_kwarg, ctor_kwarg, sample, id=None, **kwargs):
        if isinstance(parent, str):
            parent = parent_model.query(**{parent_lookup: parent})
        if parent is None:
            raise ValueError(f"{cls.__name__} requires a valid parent.")
        if isinstance(sample, str):
            sample = Sample.query(sample_id=sample)
        if sample is None:
            raise ValueError(f"{cls.__name__} requires a valid sample.")
        try:
            instance = cls.query(limit=1, sample=sample,
                                row=kwargs.get("row"), column=kwargs.get("column"),
                                **{query_kwarg: parent})
        except StatementError:
            instance = None
        if instance is None:
            instance = cls(sample=sample, id=id, **{ctor_kwarg: parent}, **kwargs)
        return instance

    @classmethod
    def query_or_create(cls, **kwargs) -> Tuple[Any, bool]:
        """
        Find an existing row matching `kwargs`, or create one, then write every
        valid kwarg onto the resulting instance.

        Only kwargs naming a column, relationship or hybrid field on `cls` are
        used; anything else is discarded. Scalar fields drive the lookup;
        list-valued fields are skipped for the query (they can't be
        equality-matched) but are still applied afterward. If there are no usable
        filters, or the query finds nothing, a new instance is created.

        :return: (instance, is_new)
        """
        # logger.debug(f"query_or_create called on {cls.__name__} with kwargs: {kwargs}")
        valid = cls._mapped_fields()
        fields = {k: v for k, v in kwargs.items() if k in valid}

        query_kwargs = {k: v for k, v in fields.items() if not isinstance(v, list)}

        instance = cls.query(limit=1, **query_kwargs) if query_kwargs else None
        if isinstance(instance, list):
            instance = None
        # Final check to ensure the instance actually matches all provided filters (e.g. list-valued ones)
        if instance:
            # logger.debug(f"query_or_create: found existing {cls.__name__} with {query_kwargs}, running final check for all fields.")
            check = all(
                (getattr(instance, k) == v if not isinstance(v, list) else all(item in getattr(instance, k) for item in v))
                for k, v in fields.items()
            )
            if not check:
                # logger.debug(f"query_or_create: existing instance did not match all fields, creating new {cls.__name__}.")
                instance = None
        new = instance is None
        if new:
            instance = cls()

        for k, v in fields.items():
            if k == "id":                      # never force/overwrite the primary key
                continue
            try:
                setattr(instance, k, v)
            except (AttributeError, ValueError) as e:
                logger.error(f"query_or_create: could not set {k} on {cls.__name__}: {e}")
        return instance, new

    @classmethod
    def _filter_relationship(cls, query, column, value, model, lookup="name"):
        if value is None:
            return query
        if isinstance(value, int) and not isinstance(value, bool):   # id lookup
            value = model.query(id=value)
        elif isinstance(value, str):                                 # name lookup
            resolved = model.query(**{lookup: value})
            if isinstance(resolved, list):        # e.g. Reagent.query(name=) returns a list
                resolved = resolved[0] if resolved else None
            value = resolved
        query = query.filter(column == value) if value is not None else query
        return query

    @classmethod
    def _filter_scalar(cls, query, column, value, *, match=None):
        # `match` lets callers keep non-equality comparisons (e.g. startswith).
        if value is None:
            return query
        condition = match(value) if match else (column == value)
        query = query.filter(condition)
        return query

    @classmethod
    def query(cls, **kwargs) -> Any | List[Any]:
        """
        Query the database for objects of this model type.
        
        Convenience wrapper around :meth:`execute_query` that sets limit to 1 
        when searching by name.

        :param kwargs: Query filters and options. Common options:

                       - name (str): Search by name, automatically limits to 1 result.
                       - limit (int): Maximum results to return.
                       - Other model fields as filter conditions.
        :return: Single result if limit=1 or name search, list otherwise.
        :rtype: any | list[any]
        """
        return cls.execute_query(**kwargs)

    @classmethod
    def execute_query(cls, query: Query = None, limit: int = 0, offset: int | None = None,
                      **kwargs) -> Any | List[Any]:
        """
        Execute a database query with advanced filtering and relationship handling.
        
        Executes a flexible query against the database with support for:
        
        - Dynamic filtering by any model field
        - Relationship handling (including unsaved instances)
        - Wildcard/list filtering
        - Result limiting and offsetting
        - Automatic single-result limiting for special fields

        :param query: Pre-built SQLAlchemy query object. 
                      If None, creates a fresh query. Defaults to None.
        :type query: :class:`sqlalchemy.orm.Query` or None
        :param limit: Maximum results to return (0 means no limit). Defaults to 0.
        :type limit: int
        :param offset: Result offset for pagination. Defaults to None.
        :type offset: int | None
        :param kwargs: Field names and values for filtering. Values can be:

                       - Scalar values for equality comparison
                       - List values (for fields with uselist=True)
                       - BaseClass instances (matches by id or name)
        :return: Single result if limit=1, list of results otherwise.
        :rtype: any | list[any]
        """
        if query is None:
            query: Query = cls.__database_session__.query(cls)
            # NOTE: determine which fields to limit to 1.
        # singles = cls.get_default_info('singles')
        for k, v in kwargs.items():
            if v is None:
                continue
            try:
                attr = getattr(cls, k)
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} unavailable due to:\n\t{e}\n.")
                continue
            # >>> INSERT HERE (new block) <
            prop = getattr(attr, "property", None)
            if isinstance(prop, RelationshipProperty) and isinstance(v, (str, int)) and not isinstance(v, bool):
                related_cls = prop.mapper.class_
                resolved = related_cls.query(**{"id" if isinstance(v, int) else "name": v})
                if isinstance(resolved, list):
                    resolved = resolved[0] if resolved else None
                if resolved is None:
                    continue
                v = resolved
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
            if k in cls.singles:
                # logger.warning(f"{k} is in singles. Returning only one value.")
                limit = 1
        if offset:
            query = query.offset(offset)
        with query.session.no_autoflush:
            if query.count() == 1:
                return query.first()
            elif query.count() == 0:
                return None
            else:
                match limit:
                    case 0:
                        return query.all()
                    case 1:
                        return query.first()
                    case _:
                        return query.limit(limit).all()

    @classmethod
    def get_primary_keys(cls):
        """Returns a list of primary key names from an SQLAlchemy object."""
        mapper = sql_inspect(cls)
        return [key.name for key in mapper.primary_key]

    @report_result
    def save(self) -> Report | None:
        """
        Add this object to the database and commit the transaction.
        
        Ensures all values in misc_info are JSON-serializable, converting them if possible.
        Removes any values that cannot be serialized.

        :return: Report object with alerts if any errors occurred, or None on success.
        :rtype: :class:`Report` | None
            
        .. note::
           This method is decorated with @report_result which provides automatic 
           result reporting. On failure, returns a Report with a Critical-level Alert.
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
        except IntegrityError as e:
            self.__database_session__.rollback()
            logger.error(f"Integrity error saving {self}: {e.orig}")
            report.add_result(Alert(msg=str(e.orig), status="Critical"))
            raise  # or return report, but don't silently drop
        except OperationalError as e:
            self.__database_session__.rollback()
            logger.critical(f"Operational error saving {self}: {e}")
            raise

    @classmethod
    def pydantic_model(cls, pyd_model_name: str | None = None) -> Any:
        """
        Get the Pydantic model class corresponding to this SQLAlchemy model.
        
        Retrieves the Pydantic validation model used for converting instances
        to validated data structures.

        :param pyd_model_name: Custom name for the Pydantic model to retrieve.
                               If None, defaults to ``Pyd{cls.__name__}`` or ``Pyd{cls.pyd_model_name}``
                               if that attribute exists. Defaults to None.
        :type pyd_model_name: str | None
        :return: Pydantic model class, or None if not found.
        :rtype: any
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

    def __setattr__(self, key, value):
        """
        Custom attribute setter to handle relationships and properties.
        
        This method intercepts attribute assignments and:
        
        - Handles SQLAlchemy special attributes correctly
        - Routes unknown attributes to misc_info
        - Properly triggers property setters for hybrid_property and property descriptors
        - Ensures JSON serializable values in misc_info
        
        :param key: Attribute name.
        :type key: str
        :param value: Value to assign.
            
        .. note::
           __setattr__ is called before property.setter methods, so this method 
           explicitly handles property descriptors to ensure their setters are called.
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
                            self._wrap_misc_info()
                    except AttributeError:
                        self._wrap_misc_info()
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
                
    @classmethod
    def get_relationship_sqlclass(cls, key: str) -> BaseClass | None:
        """
        Find the BaseClass subclass associated with a relationship field.
        
        Given a relationship field name, determines and returns the SQLAlchemy 
        model class that the relationship points to.
        
        :param key: Relationship field name to look up.
        :type key: str
        :return: Model class bound to this relationship, or None if not found.
        :rtype: :class:`BaseClass` | None
        """
        field_type = cls.determine_field_type(key)
        if "RELATIONSHIP" in field_type:
            return cls.find_subclasses(class_alias=key.strip("_"))
        return None
   
    def delete(self, **kwargs):
        """
        Delete this object from the database.
        
        This is a placeholder method. Subclasses should override to provide 
        proper deletion logic.
        
        :param kwargs: Additional keyword arguments (unused in base implementation).
        
        .. note::
           Currently logs an error and does not perform any deletion.
        """
        logger.error(f"Delete has not been implemented for {self.__class__.__name__}")

    @staticmethod
    def rectify_query_date(input_date: datetime, eod: bool = False) -> str:
        """
        Convert input into a datetime string for querying purposes.
        
        Accepts various date/datetime formats and converts them to a standardized 
        datetime string suitable for database queries.

        :param input_date: Input date to convert. Can be:

                           - datetime object
                           - date object
                           - integer (Excel ordinal format)
                           - string (parsed by dateutil.parser)
        :type input_date: datetime | date | int | str
        :param eod: Whether to append end-of-day time (23:59:59) instead 
                    of start-of-day time (00:00:00). Defaults to False.
        :type eod: bool
        :return: Formatted datetime string in format ``YYYY-MM-DD HH:MM:SS``.
        :rtype: str
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
    def sanitize_obj_for_json(cls, obj_, expand: bool = False) -> Any:
        """
        Recursively sanitize an object for JSON storage and rendering.
        
        Converts complex types to JSON-compatible representations:
        
        - datetime → ISO format string
        - date → ISO format string  
        - timedelta → days (integer)
        - Lists/AssociationLists → list with sanitized items
        - Dicts → dict with sanitized values
        - BaseClass instances → name string (or details_dict if expand=True)
        - Pydantic models → name string (or improved_dict if expand=True)

        :param obj_: Object to sanitize.
        :type obj_: any
        :param expand: If True, expands objects to their full detail 
                       dictionaries instead of just names. Defaults to False.
        :type expand: bool
        :return: JSON-compatible version of the object.
        :rtype: any
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
            case _ if issubclass(obj_.__class__, BaseClass):
                if not expand:
                    return cls.sanitize_obj_for_json(obj_.name)
                else:
                    return cls.sanitize_obj_for_json(obj_.to_pydantic().improved_dict, expand=expand)
            case _ if issubclass(obj_.__class__, PydBaseClass):
                if not expand:
                    return cls.sanitize_obj_for_json(obj_.name)
                else:
                    return cls.sanitize_obj_for_json(obj_.improved_dict, expand=expand)
            case _:
                return obj_

    def details_dict_expand_fields(self, fields: List[str] | List[dict]) -> dict:
        """
        Get details dictionary with expanded relationship information.
        
        Returns the details dictionary with additional nested information from 
        related objects. Supports both simple field expansion and recursive expansion.
        
        :param fields: Fields to expand. Format options:

                       - List of strings: ``['field1', 'field2']`` - expand these fields from relationships.
                       - List with nested dicts: ``[{'field1': ['subfield1', 'subfield2']}]`` - 
                         recursively expand subfields within relationship fields.
        :type fields: list[str] | list[dict]
        :return: Details dictionary with requested fields expanded.
        :rtype: dict
        """
        dict_ = self.details_dict
        if len(fields) == 0:
            return dict_
        for field in fields:
            match field:
                case str():
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
                        case _ if issubclass(value.__class__, BaseClass):
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
                        case _ if issubclass(value.__class__, BaseClass):
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
        Get a dictionary representation of this object suitable for serialization.
        
        Generates a dictionary of all relevant model data, excluding internal fields 
        and foreign keys. Includes miscellaneous info and automatically sanitizes values 
        for JSON compatibility.
        
        :return: Dictionary with 'excluded' key listing hidden fields and all other 
                 model data sanitized for JSON storage.
        :rtype: dict
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
        Convert this SQLAlchemy instance to a Pydantic model.
        
        Transforms the object's data into a validated Pydantic model instance,
        useful for data validation, serialization, and API responses.
        
        :param pyd_model_name: Custom name for the Pydantic model class to use.
                               If None, defaults to ``Pyd{cls.__name__}``. Defaults to None.
        :type pyd_model_name: str | None
        :param kwargs: Additional arguments (reserved for future use).
        :return: Pydantic model instance representing this object.
        :rtype: :class:`pydantic.BaseModel`
        """
        pyd = self.pydantic_model(pyd_model_name=pyd_model_name)
        details = self.details_dict
        details['sql_instance'] = self
        return pyd(**details)

    def show_details(self, obj):
        """
        Display details of this object as an interactive HTML dialog.
        
        Converts the object to a Pydantic model and displays it in a styled widget.
        Requires a parent QWidget or QDialog to attach the dialog to.
        
        :param obj: Parent QWidget or QDialog that will own the details dialog.
        """
        from frontend.widgets.submission_details import SubmissionDetails
        dlg = SubmissionDetails(parent=obj, object_ = self.to_pydantic())
        dlg.exec()

    @classmethod
    def find_subclasses(cls, class_name: str | None = None, class_alias: str | None = None) -> BaseClass | List[BaseClass] | None:
        """
        Find BaseClass subclasses by class name or alias.
        
        Searches the registry of BaseClass subclasses for a match by name or alias.
        
        :param class_name: Class name to search for (case-insensitive).
                           Will search for ``cls.__name__.lower()``. Defaults to None.
        :type class_name: str | None
        :param class_alias: Alias to search for, checked against each class's
                            :attr:`aliases` list. Defaults to None.
        :type class_alias: str | None
        :return: Matching class (if class_name or class_alias provided),
                 list of all subclasses (if neither provided), or None if no match found.
        :rtype: :class:`BaseClass` | list[:class:`BaseClass`] | None
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
        Add a rank to a sample in this class.
        
        Updates a Pydantic sample instance with a rank value.
        
        :param sample: Sample model to be updated.
        :type sample: :class:`PydSample`
        :param iii: Rank value to assign to the sample.
        :type iii: int
        :return: Updated sample with rank assigned.
        :rtype: :class:`PydSample`
        """
        sample.rank = iii
        return sample

    @classmethod
    def already_in_collection(cls, obj: BaseClass, collection: list) -> bool:
        """
        Check whether *obj* is already represented in *collection* by comparing
        primary key values, rather than by object identity.

        Handles three cases:
        - obj has no PK yet (all PKs are None)  → always False, treat as new
        - a collection member is the same Python object → True (fast path)
        - a collection member has identical non-None PK values → True

        Args:
            obj: A SQLAlchemy model instance (must inherit BaseClass).
            collection: The instrumented list / plain list to search.

        Returns:
            True if an equivalent row is already present, False otherwise.
        """
        pk_names = obj.get_primary_keys()
        pk_vals = {k: getattr(obj, k, None) for k in pk_names}
        if obj.__class__.__qualname__ == "Results":
            if obj.result in [item.result for item in collection]:
                return True
        # If every PK column is None the object hasn't been persisted yet;
        # we can't meaningfully deduplicate it, so let it through.
        if all(v is None for v in pk_vals.values()):
            obj_sample = getattr(getattr(obj, "sample", None), "sample_id", None)
            obj_rank = getattr(obj, "procedure_rank", None)
            if obj_sample is not None and obj_rank is not None:
                for existing in collection:
                    if (getattr(getattr(existing, "sample", None), "sample_id", None) == obj_sample
                            and getattr(existing, "procedure_rank", None) == obj_rank):
                        return True
            return False
        
        for existing in collection:
            if existing is obj:
                return True
            if all(getattr(existing, k, None) == v for k, v in pk_vals.items()):
                return True

        return False

    @classproperty
    def singles(cls) -> List[str]:
        """
        Field names that uniquely identify at most one row, so a ``query()`` filtering
        on them should return a single object rather than a list.

        Included:
        * primary-key columns and any column carrying its own UNIQUE constraint
            (e.g. ``id``, a unique ``name``);
        * to-one relationships from the queried object's perspective — one-to-many
            (filtering a parent by one of its children yields that one parent) and
            one-to-one (a many-to-one whose local foreign key is itself unique).

        Excluded (these can match many rows):
        * ordinary many-to-one relationships (many rows share the related object);
        * many-to-many relationships;
        * individual columns of a composite primary key, none of which is unique
            on its own.

        Names are returned without a single leading underscore so they line up with
        the keys callers pass to ``query()`` (``clientlab``, not ``_clientlab``).
        """
        from sqlalchemy import UniqueConstraint

        mapper = getattr(cls, "__mapper__", None)
        table = getattr(cls, "__table__", None)
        if mapper is None or table is None:
            return []
        def _public(key: str) -> str:
            return key[1:] if key.startswith("_") else key
        def _columns_are_unique(columns) -> bool:
            cols = set(columns)
            if not cols:
                return False
            # The exact primary key (e.g. a sole 'id' column).
            if cols == set(table.primary_key.columns):
                return True
            # Each column carries its own unique=True.
            if all(getattr(col, "unique", False) for col in cols):
                return True
            # The columns exactly match a declared UNIQUE constraint.
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint) and set(constraint.columns) == cols:
                    return True
            return False
        fields = set(["name", "id"])
        for column in mapper.columns:
            if _columns_are_unique({column}):
                fields.add(_public(column.key))
        for rel in mapper.relationships:
            direction = rel.direction.name  # ONETOMANY | MANYTOONE | MANYTOMANY
            if direction == "ONETOMANY":
                fields.add(_public(rel.key))
            elif direction == "MANYTOONE" and not rel.uselist and _columns_are_unique(rel.local_columns):
                fields.add(_public(rel.key))  # genuine one-to-one (unique local FK)
        return sorted(fields)


class LogMixin(Base):
    """
    Mixin class to add audit logging tracking to SQLAlchemy models.
    
    This mixin should be combined with BaseClass to enable comprehensive audit tracking
    of model changes. Certain attributes are excluded from tracking to avoid noise.
    
    This is an abstract class and should not be instantiated directly.
    
    :cvar tracking_exclusion: List of field names to exclude from audit tracking.
    :vartype tracking_exclusion: ClassVar[list]
    """
    tracking_exclusion: ClassVar = ['clientsubmissionsampleassociation',
                                    'contact_id', 'clientlab_id', 'misc_info', '_misc_info']

    __abstract__ = True

    @property
    def truncated_name(self) -> str:
        """
        Get a truncated version of the object's name for concise logging.
        
        Limits the name to 64 characters, appending "..." if truncated.
        
        :return: Truncated name, up to 64 characters total.
        :rtype: str
        """
        name = str(self)
        if len(name) > 64:
            name = f"...{name[-61:]}"
        return name


class ConfigItem(BaseClass):
    """
    Configuration item model for storing key-value settings in the database.
    
    Stores application configuration settings as key-value pairs with JSON-serialized values,
    allowing for flexible storage of complex configuration data.
    
    :ivar id: Primary key auto-incremented identifier.
    :vartype id: int
    :ivar key: Unique configuration key name (max 32 characters).
    :vartype key: str
    :ivar value: JSON-serialized configuration value.
    :vartype value: dict
    """

    id = Column(INTEGER, primary_key=True)
    key = Column(String(32), nullable=False, unique=True)  #: Name of the configuration item.
    value = Column(JSON)  #: Value associated with the config item.

    def __repr__(self) -> str:
        """
        Return string representation of this ConfigItem.
        
        :return: String representation in format ``<ConfigItem(key : value)>``.
        :rtype: str
        """
        return f"<ConfigItem({self.key} : {self.value})>"

    @classmethod
    def get_config_items(cls, *args) -> ConfigItem | List[ConfigItem]:
        """
        Retrieve configuration items from the database.
        
        Fetches all config items, a single item by key, or multiple items by keys.

        :param args: Configuration keys to retrieve:

                     - No args: Returns all config items.
                     - One arg: Returns single config item (or None if not found).
                     - Multiple args: Returns list of all matching config items.
        :type args: str
        :return: Single ConfigItem (if one key provided),
                 list of ConfigItem objects, or all ConfigItem objects if no keys provided.
        :rtype: :class:`ConfigItem` | list[:class:`ConfigItem`]
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
from .organizations import *
from .procedures import *
from .submissions import *

__all__ = ["LogMixin", "ConfigItem",
    "AuditLog",
    "ReagentRole", "Reagent", "ReagentLot", "Discount", "SubmissionType", "ProcedureType", "Procedure", "ProcedureTypeReagentRoleAssociation",
    "ProcedureReagentLotAssociation", "EquipmentRole", "Equipment", "EquipmentRoleEquipmentAssociation", "Process", "ProcessVersion",
    "Tips", "TipsLot", "ProcedureEquipmentAssociation",
    "ProcedureTypeEquipmentRoleAssociation", "Results",
    "ClientSubmission", "Run", "Sample", "ClientSubmissionSampleAssociation", "RunSampleAssociation", "ProcedureSampleAssociation",
    "ClientLab", "Contact"]