"""_proceduresampleassociation: surrogate id PK + composite unique

Replaces the composite primary key (procedure_id, sample_id, procedure_rank)
with a surrogate autoincrement ``id`` primary key, and demotes the old key to a
plain UNIQUE constraint (uq_proc_sample_rank). This removes the client-side
``autoincrement_id`` id generator, which produced colliding ids for equal ranks.

SQLite cannot ALTER a primary key in place, so this rebuilds the table
(create-new / copy / drop / rename). The table is referenced by
``_results.assoc_id`` with ON DELETE SET NULL; because the app enables
foreign_keys, the DROP would null those links, so we snapshot and restore them
within the same transaction. All ``id`` values are preserved, so the restore is
exact.

Revision ID: b7d3f9a1c2e4
Revises: 81eb1a777da2
Create Date: 2026-07-10
"""
from alembic import op

revision = "b7d3f9a1c2e4"
down_revision = "5491f5ffb268"
branch_labels = None
depends_on = None

TABLE = "_proceduresampleassociation"
COLS = 'id, procedure_id, sample_id, "row", "column", procedure_rank, _comment, _misc_info'


def _abort_if_duplicates() -> None:
    """Old composite PK forbids committed duplicates, but check defensively:
    a UNIQUE constraint cannot be added over existing duplicate rows."""
    bind = op.get_bind()
    dupes = bind.exec_driver_sql(
        f"SELECT procedure_id, sample_id, procedure_rank, COUNT(*) c "
        f"FROM {TABLE} GROUP BY procedure_id, sample_id, procedure_rank HAVING c > 1"
    ).fetchall()
    if dupes:
        raise RuntimeError(
            f"Cannot add uq_proc_sample_rank: {len(dupes)} duplicate "
            f"(procedure_id, sample_id, procedure_rank) group(s) exist. "
            f"Resolve these rows before migrating: {dupes[:10]}"
        )


def upgrade() -> None:
    _abort_if_duplicates()
    op.execute(f"""
        CREATE TEMP TABLE _psa_fk_backup AS
            SELECT id AS results_id, assoc_id FROM _results WHERE assoc_id IS NOT NULL;
    """)
    op.execute(f"""
        CREATE TABLE {TABLE}_new (
            id             INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            procedure_id   INTEGER NOT NULL REFERENCES _procedure(id) ON DELETE CASCADE,
            sample_id      INTEGER NOT NULL REFERENCES _sample(id)    ON DELETE RESTRICT,
            "row"          INTEGER,
            "column"       INTEGER,
            procedure_rank INTEGER NOT NULL DEFAULT 0,
            _comment       JSON,
            _misc_info     JSON,
            CONSTRAINT uq_proc_sample_rank UNIQUE (procedure_id, sample_id, procedure_rank)
        );
    """)
    op.execute(f"INSERT INTO {TABLE}_new ({COLS}) SELECT {COLS} FROM {TABLE};")
    op.execute(f"DROP TABLE {TABLE};")                                  # nulls _results.assoc_id (SET NULL)
    op.execute(f"ALTER TABLE {TABLE}_new RENAME TO {TABLE};")
    op.execute("""
        UPDATE _results
           SET assoc_id = (SELECT assoc_id FROM _psa_fk_backup WHERE results_id = _results.id)
         WHERE id IN (SELECT results_id FROM _psa_fk_backup);
    """)                                                               # restore the links
    op.execute("DROP TABLE _psa_fk_backup;")


def downgrade() -> None:
    op.execute(f"""
        CREATE TEMP TABLE _psa_fk_backup AS
            SELECT id AS results_id, assoc_id FROM _results WHERE assoc_id IS NOT NULL;
    """)
    op.execute(f"""
        CREATE TABLE {TABLE}_old (
            id             INTEGER NOT NULL UNIQUE,
            procedure_id   INTEGER NOT NULL REFERENCES _procedure(id) ON DELETE CASCADE,
            sample_id      INTEGER NOT NULL REFERENCES _sample(id)    ON DELETE RESTRICT,
            "row"          INTEGER,
            "column"       INTEGER,
            procedure_rank INTEGER NOT NULL DEFAULT 0,
            _comment       JSON,
            _misc_info     JSON,
            PRIMARY KEY (procedure_id, sample_id, procedure_rank)
        );
    """)
    op.execute(f"INSERT INTO {TABLE}_old ({COLS}) SELECT {COLS} FROM {TABLE};")
    op.execute(f"DROP TABLE {TABLE};")
    op.execute(f"ALTER TABLE {TABLE}_old RENAME TO {TABLE};")
    op.execute("""
        UPDATE _results
           SET assoc_id = (SELECT assoc_id FROM _psa_fk_backup WHERE results_id = _results.id)
         WHERE id IN (SELECT results_id FROM _psa_fk_backup);
    """)
    op.execute("DROP TABLE _psa_fk_backup;")