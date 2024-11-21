"""
All database related operations.
"""
import sqlalchemy.orm
from sqlalchemy import event, inspect
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
    # print(ctx.database_schema)
    if ctx.database_schema == "sqlite":
        execution_phrase = "PRAGMA foreign_keys=ON"
        # cursor.execute(execution_phrase)
    elif ctx.database_schema == "mssql+pyodbc":
        execution_phrase = "SET IDENTITY_INSERT dbo._wastewater ON;"
    else:
        print("Nothing to execute, returning")
        cursor.close()
        return
    print(f"Executing {execution_phrase} in sql.")
    cursor.execute(execution_phrase)
    cursor.close()


from .models import *


def update_log(mapper, connection, target):
    logger.debug("\n\nBefore update\n\n")
    state = inspect(target)
    logger.debug(state)
    update = dict(user=getuser(), time=datetime.now(), object=str(state.object), changes=[])
    logger.debug(update)
    for attr in state.attrs:
        hist = attr.load_history()
        if not hist.has_changes():
            continue
        added = [str(item) for item in hist.added]
        deleted = [str(item) for item in hist.deleted]
        change = dict(field=attr.key, added=added, deleted=deleted)
        logger.debug(f"Adding: {pformat(change)}")
        try:
            update['changes'].append(change)
        except Exception as e:
            logger.error(f"Something went horribly wrong adding attr: {attr.key}: {e}")
            continue

    logger.debug(f"Adding to audit logs: {pformat(update)}")
    if update['changes']:
        # Note: must use execute as the session will be busy at this point.
        # https://medium.com/@singh.surbhicse/creating-audit-table-to-log-insert-update-and-delete-changes-in-flask-sqlalchemy-f2ca53f7b02f
        table = AuditLog.__table__
        logger.debug(f"Adding to {table}")
        connection.execute(table.insert().values(**update))
        # logger.debug("Here is where I would insert values, if I was able.")
    else:
        logger.info(f"No changes detected, not updating logs.")


# event.listen(LogMixin, 'after_update', update_log, propagate=True)
# event.listen(LogMixin, 'after_insert', update_log, propagate=True)
