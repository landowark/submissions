"""
Startup script: back up the current SQLite database to a date-tagged ``.sql`` file.

Placement
---------
Put this file in the ``scripts`` directory that ``Settings.set_scripts`` scans
(the same folder as your other startup/teardown scripts). ``set_scripts``
imports every ``[!__]*.py`` module there and wires up any function whose name
appears in the ``startup_scripts`` config.

Registration
------------
``run_startup`` only calls scripts registered in the database config. Add this
function's name to the ``startup_scripts`` config value (convention is
``{name: null}``), e.g. update the ``_configitem`` row whose ``key`` is
``startup_scripts`` so it contains::

    {"backup_database": null}

Calling convention
------------------
``run_startup`` invokes each registered script on a background thread as
``script(ctx)``, so the entry point takes a single ``ctx`` argument and must be
safe to call off the main thread.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(f"submissions.scripts.{__name__}")


def _sqlite_iterdump(conn: sqlite3.Connection):
    """
    Yield a complete SQL dump (schema + data) of *conn*, WITHOUT running
    ``PRAGMA foreign_key_check``.

    Python 3.13's ``Connection.iterdump`` runs that check first and aborts with
    ``OperationalError: foreign key mismatch`` if any foreign key is structurally
    invalid. This reproduces the classic dump and brackets it with
    ``PRAGMA foreign_keys=OFF; ... ON;`` so a malformed FK can block neither the
    dump nor a later restore.
    """
    cu = conn.cursor()
    yield "PRAGMA foreign_keys=OFF;"
    yield "BEGIN TRANSACTION;"

    tables = cu.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE sql NOT NULL AND type = 'table' ORDER BY name"
    ).fetchall()

    sqlite_sequence = []
    for name, sql in tables:
        if name == "sqlite_sequence":
            rows = cu.execute("SELECT name, seq FROM sqlite_sequence").fetchall()
            sqlite_sequence = ["DELETE FROM sqlite_sequence;"]
            sqlite_sequence += [f"INSERT INTO sqlite_sequence VALUES('{n}',{s});" for n, s in rows]
            continue
        if name.startswith("sqlite_"):
            continue
        yield f"{sql};"

        ident = name.replace('"', '""')
        cols = [r[1] for r in cu.execute('PRAGMA table_info("%s")' % ident).fetchall()]
        # quote() returns each value as a ready-to-embed SQL literal (NULL, strings, blobs).
        quoted = ", ".join('quote("%s")' % c.replace('"', '""') for c in cols)
        for row in cu.execute('SELECT %s FROM "%s"' % (quoted, ident)):
            yield 'INSERT INTO "%s" VALUES(%s);' % (ident, ",".join(row))

    for (sql,) in cu.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE sql NOT NULL AND type IN ('index','trigger','view')"
    ).fetchall():
        yield f"{sql};"

    yield from sqlite_sequence
    yield "COMMIT;"
    yield "PRAGMA foreign_keys=ON;"


def backup_database(ctx) -> Path | None:
    """
    Dump the current SQLite database to ``ctx.directories.backup`` as a
    date-tagged ``.sql`` file. Designed to run from ``ctx.run_startup()``.

    The dump is a portable SQL text file (schema + data), equivalent to the
    ``.dump`` command of the sqlite3 CLI. One file is produced per calendar day;
    if today's backup already exists it is left untouched, so re-running on every
    launch is cheap and idempotent. Any failure is logged and swallowed so it can
    never disrupt startup.

    :param ctx: The application Settings/context object.
    :return: Path to the backup file, or ``None`` if no backup was written.
    """
    try:
        database = ctx.database

        # Only SQLite is handled here.
        schema = database.get("schema")
        if schema != "sqlite":
            logger.info("Database schema is %r, not sqlite; skipping backup.", schema)
            return None

        # The live engine's URL is the authoritative source of the file path.
        engine = database.get("engine")
        if engine is None:
            logger.error("No database engine on ctx.database; skipping backup.")
            return None
        db_path = Path(engine.url.database) if engine.url.database else None
        if db_path is None or not db_path.exists():
            logger.error("Could not locate sqlite file (got %r); skipping backup.", str(db_path))
            return None

        # Resolve and create the backup directory.
        backup_root = ctx.directories.get("backup")
        if not backup_root:
            logger.error("ctx.directories.backup is not set; skipping backup.")
            return None
        backup_dir = Path(backup_root)
        backup_dir.mkdir(parents=True, exist_ok=True)

        db_name = database.get("name") or db_path.stem
        today = date.today().isoformat()  # e.g. 2026-06-01 (sorts lexicographically)
        backup_file = backup_dir.joinpath(f"{db_name}_{today}.sql")

        # Runs on every launch, so don't redo a backup already made today.
        if backup_file.exists():
            logger.info("Backup for %s already exists at %s; skipping.", today, backup_file)
            return backup_file

        # Open a fresh connection *in this thread*. run_startup runs scripts on a
        # worker thread and sqlite3 connections are thread-affine, so the app's
        # pooled connection must not be reused here. A read transaction (BEGIN)
        # gives a consistent snapshot; under WAL it won't block the app's writers.
        # Write to a temp file and publish atomically, so an interrupted/failed
        # dump can never leave a half-written .sql masquerading as the day's backup.
        tmp_file = backup_file.with_suffix(".sql.tmp")
        source = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            source.execute("BEGIN")  # consistent-snapshot read transaction
            with open(tmp_file, "w", encoding="utf-8") as fh:
                fh.write("-- submissions database backup (sqlite)\n")
                fh.write(f"-- source:  {db_path}\n")
                fh.write(f"-- created: {datetime.now().isoformat(timespec='seconds')}\n\n")
                for statement in _sqlite_iterdump(source):
                    fh.write(statement)
                    fh.write("\n")
            source.rollback()  # end the read transaction without writing anything
        except Exception:
            tmp_file.unlink(missing_ok=True)
            raise
        finally:
            source.close()

        tmp_file.replace(backup_file)
        logger.info("Database backed up to %s", backup_file)
        return backup_file

    except Exception as e:
        # A backup failure must never interfere with application startup.
        logger.error("Database backup failed: %s", e, exc_info=True)
        return None