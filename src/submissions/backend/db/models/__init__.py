'''
Contains all models for sqlalchemy
'''
import sys
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query, Session
from sqlalchemy.ext.declarative import declared_attr
from typing import Any, List
from pathlib import Path
# Load testing environment
if 'pytest' in sys.modules:
    from pathlib import Path
    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

Base: DeclarativeMeta = declarative_base()


class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.
    """
    __abstract__ = True  #: Will not be added to DB
    
    __table_args__ = {'extend_existing': True}   #: Will only add new columns

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
    def execute_query(cls, query: Query, limit: int = 0) -> Any | List[Any]:
        """
        Execute sqlalchemy query.

        Args:
            query (Query): input query object
            limit (int): Maximum number of results. (0 = all)

        Returns:
            Any | List[Any]: Single result if limit = 1 or List if other.
        """        
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


from .controls import *
# import order must go: orgs, kit, subs due to circular import issues
from .organizations import *
from .kits import *
from .submissions import *
