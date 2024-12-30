"""
All database related operations.
"""
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
    if ctx.database_schema == "sqlite":
        execution_phrase = "PRAGMA foreign_keys=ON"
    else:
        # print("Nothing to execute, returning")
        cursor.close()
        return
    print(f"Executing '{execution_phrase}' in sql.")
    cursor.execute(execution_phrase)
    cursor.close()


from .models import *


def update_log(mapper, connection, target):
    state = inspect(target)
    object_name = state.object.truncated_name
    update = dict(user=getuser(), time=datetime.now(), object=object_name, changes=[])
    for attr in state.attrs:
        hist = attr.load_history()
        if not hist.has_changes():
            continue
        if attr.key == "custom":
            continue
        added = [str(item) for item in hist.added]
        if attr.key in ['artic_technician', 'submission_sample_associations', 'submission_reagent_associations',
                        'submission_equipment_associations', 'submission_tips_associations', 'contact_id', 'gel_info',
                        'gel_controls', 'source_plates']:
            continue
        deleted = [str(item) for item in hist.deleted]
        change = dict(field=attr.key, added=added, deleted=deleted)
        if added != deleted:
            try:
                update['changes'].append(change)
            except Exception as e:
                logger.error(f"Something went wrong adding attr: {attr.key}: {e}")
                continue
    if update['changes']:
        # Note: must use execute as the session will be busy at this point.
        # https://medium.com/@singh.surbhicse/creating-audit-table-to-log-insert-update-and-delete-changes-in-flask-sqlalchemy-f2ca53f7b02f
        table = AuditLog.__table__
        connection.execute(table.insert().values(**update))
    else:
        logger.info(f"No changes detected, not updating logs.")

event.listen(LogMixin, 'after_update', update_log, propagate=True)
event.listen(LogMixin, 'after_insert', update_log, propagate=True)
