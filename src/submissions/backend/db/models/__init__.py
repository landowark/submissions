"""
Contains all models for sqlalchemy
"""
from __future__ import annotations
import sys, logging
from sqlalchemy import Column, INTEGER, String, JSON
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.exc import ArgumentError
from typing import Any, List
from pathlib import Path

# Load testing environment
if 'pytest' in sys.modules:
    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

Base: DeclarativeMeta = declarative_base()

logger = logging.getLogger(f"submissions.{__name__}")


class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.
    """
    __abstract__ = True  #: Will not be added to DB

    __table_args__ = {'extend_existing': True}  #: Will only add new columns

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
        dicto = dict(singles=['id'])
        output = {}
        for k, v in dicto.items():
            if len(args) > 0 and k not in args:
                # logger.debug(f"Don't want {k}")
                continue
            else:
                output[k] = v
        if len(args) == 1:
            return output[args[0]]
        return output

    @classmethod
    def query(cls, **kwargs) -> Any | List[Any]:
        """
        Default query function for models. Overridden in most models.

        Returns:
            Any | List[Any]: Result of query execution.
        """           
        return cls.execute_query(**kwargs)

    @classmethod
    def execute_query(cls, query: Query = None, model=None, limit: int = 0, **kwargs) -> Any | List[Any]:
        """
        Execute sqlalchemy query with relevant defaults.

        Args:
            model (Any, optional): model to be queried. Defaults to None
            query (Query, optional): input query object. Defaults to None
            limit (int): Maximum number of results. (0 = all). Defaults to 0

        Returns:
            Any | List[Any]: Single result if limit = 1 or List if other.
        """
        if model is None:
            model = cls
        if query is None:
            query: Query = cls.__database_session__.query(model)
        # logger.debug(f"Grabbing singles using {model.get_default_info}")
        singles = model.get_default_info('singles')
        logger.info(f"Querying: {model}, with kwargs: {kwargs}")
        for k, v in kwargs.items():
            # logger.debug(f"Using key: {k} with value: {v}")
            try:
                attr = getattr(model, k)
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

    def save(self):
        """
        Add the object to the database and commit
        """
        # logger.debug(f"Saving object: {pformat(self.__dict__)}")
        try:
            self.__database_session__.add(self)
            self.__database_session__.commit()
        except Exception as e:
            logger.critical(f"Problem saving object: {e}")
            self.__database_session__.rollback()


class ConfigItem(BaseClass):
    """
    Key:JSON objects to store config settings in database. 
    """    
    id = Column(INTEGER, primary_key=True)
    key = Column(String(32)) #: Name of the configuration item.
    value = Column(JSON) #: Value associated with the config item.

    def __repr__(self):
        return f"ConfigItem({self.key} : {self.value})"

    @classmethod
    def get_config_items(cls, *args) -> ConfigItem|List[ConfigItem]:
        """
        Get desired config items from database

        Returns:
            ConfigItem|List[ConfigItem]: Config item(s)
        """        
        config_items = cls.__database_session__.query(cls).all()
        config_items = [item for item in config_items if item.key in args]
        if len(args) == 1:
            config_items = config_items[0]
        return config_items


from .controls import *
# NOTE: import order must go: orgs, kit, subs due to circular import issues
from .organizations import *
from .kits import *
from .submissions import *
BasicSubmission.reagents.creator = lambda reg: SubmissionReagentAssociation(reagent=reg)
