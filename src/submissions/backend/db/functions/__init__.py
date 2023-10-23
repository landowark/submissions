'''Contains or imports all database convenience functions'''
from tools import Settings, package_dir
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError as AlcOperationalError, IntegrityError as AlcIntegrityError
from sqlite3 import OperationalError as SQLOperationalError, IntegrityError as SQLIntegrityError
from pathlib import Path
import logging

logger = logging.getLogger(f"Submissions_{__name__}")

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    *should* allow automatic creation of foreign keys in the database
    I have no idea how it actually works.

    Args:
        dbapi_connection (_type_): _description_
        connection_record (_type_): _description_
    """    
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def create_database_session(ctx:Settings) -> Session:
    """
    Create database session for app.

    Args:
        ctx (Settings): settings passed down from gui

    Raises:
        FileNotFoundError: Raised if sqlite file not found

    Returns:
        Session: Sqlalchemy session object.
    """    
    database_path = ctx.database_path
    if database_path == None:
        # check in user's .submissions directory for submissions.db
        if Path.home().joinpath(".submissions", "submissions.db").exists():
            database_path = Path.home().joinpath(".submissions", "submissions.db")
        # finally, look in the local dir
        else:
            database_path = package_dir.joinpath("submissions.db")
    else:
        if database_path == ":memory:":
            pass
        # check if user defined path is directory
        elif database_path.is_dir():
            database_path = database_path.joinpath("submissions.db")
        # check if user defined path is a file
        elif database_path.is_file():
            database_path = database_path
        else:
            raise FileNotFoundError("No database file found. Exiting program.")
    logger.debug(f"Using {database_path} for database file.")
    engine = create_engine(f"sqlite:///{database_path}", echo=True, future=True)
    session = Session(engine)
    return session

def store_object(ctx:Settings, object) -> dict|None:
    """
    Store an object in the database

    Args:
        ctx (Settings): Settings object passed down from gui
        object (_type_): Object to be stored

    Returns:
        dict|None: Result of action
    """    
    dbs = ctx.database_session
    dbs.merge(object)
    try:
        dbs.commit()
    except (SQLIntegrityError, AlcIntegrityError) as e:
        logger.debug(f"Hit an integrity error : {e}")
        dbs.rollback()
        return {"message":f"This object {object} already exists, so we can't add it.\n{e}", "status":"Critical"}
    except (SQLOperationalError, AlcOperationalError):
        logger.error(f"Hit an operational error: {e}")
        dbs.rollback()
        return {"message":"The database is locked for editing."}
    return None

from .lookups import *
# from .constructions import *
from .misc import *
