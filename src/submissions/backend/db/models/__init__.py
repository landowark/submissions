'''
Contains all models for sqlalchemy
'''
import sys
from sqlalchemy.orm import DeclarativeMeta, declarative_base, Query
from sqlalchemy.ext.declarative import declared_attr
if 'pytest' in sys.modules:
    from pathlib import Path
    sys.path.append(Path(__file__).parents[4].absolute().joinpath("tests").__str__())

Base: DeclarativeMeta = declarative_base()

class BaseClass(Base):
    """
    Abstract class to pass ctx values to all SQLAlchemy objects.

    Args:
        Base (DeclarativeMeta): Declarative base for metadata.
    """
    __abstract__ = True
    
    __table_args__ = {'extend_existing': True} 

    @declared_attr
    def __tablename__(cls):
        """
        Set tablename to lowercase class name
        """        
        return f"_{cls.__name__.lower()}"

    @declared_attr
    def __database_session__(cls):
        """
        Pull db session from ctx
        """        
        if not 'pytest' in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.database_session

    @declared_attr
    def __directory_path__(cls):
        """
        Pull submission directory from ctx
        """        
        if not 'pytest' in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.directory_path
    
    @declared_attr
    def __backup_path__(cls):
        """
        Pull backup directory from ctx
        """        
        if not 'pytest' in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        return ctx.backup_path
    
    def query_return(query:Query, limit:int=0):
        """
        Execute sqlalchemy query.

        Args:
            query (Query): Query object
            limit (int, optional): Maximum number of results to return (0 = all). Defaults to 0.

        Returns:
            _type_: Query result.
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
