'''
Contains all models for sqlalchemy
'''
from __future__ import annotations
import sys, logging
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.exc import ArgumentError
from typing import Any, List
from pathlib import Path

# Load testing environment
if 'pytest' in sys.modules:
    from pathlib import Path

    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

Base: DeclarativeMeta = declarative_base()

logger = logging.getLogger(f"submissions.{__name__}")


class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.
    """
    __abstract__ = True  #: Will not be added to DB

    __table_args__ = {'extend_existing': True}  #: Will only add new columns

    @declared_attr
    def __tablename__(cls) -> str:
        """
        Sets table name to lower case class name.

        Returns:
            str: lower case class name
        """
        return f"_{cls.__name__.lower()}"

    @declared_attr
    def __database_session__(cls) -> Session:
        """
        Pull db session from ctx to be used in operations

        Returns:
            Session: DB session from ctx settings.
        """
        if not 'pytest' in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.database_session

    @declared_attr
    def __directory_path__(cls) -> Path:
        """
        Pull directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions directory in Settings object
        """
        if not 'pytest' in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.directory_path

    @declared_attr
    def __backup_path__(cls) -> Path:
        """
        Pull backup directory path from ctx to be used in operations.

        Returns:
            Path: Location of the Submissions backup directory in Settings object
        """
        if not 'pytest' in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.backup_path

    @classmethod
    def get_default_info(cls, *args) -> dict | List[str]:
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
    def query(cls, **kwargs):
        return cls.execute_query(**kwargs)

    @classmethod
    def execute_query(cls, query: Query = None, model=None, limit: int = 0, **kwargs) -> Any | List[Any]:
        """
        Execute sqlalchemy query.

        Args:
            query (Query): input query object
            limit (int): Maximum number of results. (0 = all)

        Returns:
            Any | List[Any]: Single result if limit = 1 or List if other.
        """
        if model is None:
            model = cls
        if query is None:
            query: Query = cls.__database_session__.query(model)
        # logger.debug(f"Grabbing singles using {model.get_default_info}")
        singles = model.get_default_info('singles')
        logger.debug(f"Querying: {model}, singles: {singles}")
        for k, v in kwargs.items():
            logger.debug(f"Using key: {k} with value: {v}")
            # logger.debug(f"That key found attribute: {attr} with type: {attr}")
            try:
                attr = getattr(model, k)
                query = query.filter(attr == v)
            except (ArgumentError, AttributeError) as e:
                logger.error(f"Attribute {k} available due to:\n\t{e}\nSkipping.")
            if k in singles:
                limit = 1
        with query.session.no_autoflush:
            match limit:
                case 0:
                    return query.all()
                case 1:
                    return query.first()
                case _:
                    return query.limit(limit).all()

    @classmethod
    def default_info_return(cls, info, *args):
        return info

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


from .controls import *
# import order must go: orgs, kit, subs due to circular import issues
from .organizations import *
from .kits import *
from .submissions import *
