"""
All database related operations.
"""
from sqlalchemy import event
from sqlalchemy.engine import Engine
from tools import ctx


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    *should* allow automatic creation of foreign keys in the database
    I have no idea how it actually works.
    Listens for connect and then turns on foreign keys?

    Args:
        dbapi_connection (_type_): _description_
        connection_record (_type_): _description_
    """    
    cursor = dbapi_connection.cursor()
    if ctx.database_schema == "sqlite":
        cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


from .models import *
