"""
Structural checks on the schema the models declare.

These run against ``Base.metadata`` and a freshly created database rather than
against any live data, so they catch declaration mistakes before those mistakes
reach a migration or a production write.

The motivating case: ``ProcedureTypeReagentRoleAssociation.last_used_lot`` was
declared ``ForeignKey("_reagentlot.lot")`` while ``_reagentlot.lot`` was neither a
primary key nor unique. SQLite accepts that ``CREATE TABLE`` happily and only
objects at write time, with the famously unhelpful ``foreign key mismatch``. Since
``backend/db`` turns ``PRAGMA foreign_keys=ON`` on for every connection, the
result was that a whole association table could not be written to at all --
discovered only by trying to insert into it.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool


def _metadata():
    from backend.db.models import Base

    return Base.metadata


def test_every_foreign_key_targets_a_unique_column(db):
    """
    SQLite requires the *parent* column of a foreign key to be a primary key or
    to carry a unique index. Anything else is a malformed constraint that fails
    at write time rather than at definition time.
    """
    metadata = _metadata()
    problems = []

    for table in metadata.tables.values():
        for column in table.columns:
            for fk in column.foreign_keys:
                target = fk.column
                parent = target.table
                if target.primary_key:
                    continue
                if target.unique:
                    continue
                # A column-level unique=True renders as a unique Index rather
                # than a UniqueConstraint, so both have to be consulted.
                in_unique_constraint = any(
                    list(constraint.columns) == [target]
                    for constraint in parent.constraints
                    if constraint.__class__.__name__ == "UniqueConstraint"
                )
                in_unique_index = any(
                    index.unique and list(index.columns) == [target]
                    for index in parent.indexes
                )
                if in_unique_constraint or in_unique_index:
                    continue
                problems.append(
                    f"{table.name}.{column.name} -> {parent.name}.{target.name} "
                    f"({parent.name}.{target.name} is not a primary key and is not unique)"
                )

    assert not problems, (
        "malformed foreign keys; SQLite will report 'foreign key mismatch' on "
        "writes to either table:\n  " + "\n  ".join(problems)
    )


def test_schema_creates_with_foreign_keys_enforced():
    """
    Build the whole schema in a database with enforcement on and confirm the
    integrity pragmas come back clean. This is the cheap end-to-end version of
    the check above.
    """
    metadata = _metadata()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    try:
        with engine.connect() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            metadata.create_all(connection)
            connection.commit()
            assert connection.execute(text("PRAGMA integrity_check")).scalar() == "ok"
            assert connection.execute(text("PRAGMA foreign_key_check")).all() == []
    finally:
        engine.dispose()


def test_populated_database_passes_integrity_checks(graph, db):
    """The seeded graph must leave the database internally consistent."""
    assert db.execute(text("PRAGMA integrity_check")).scalar() == "ok"
    assert db.execute(text("PRAGMA foreign_key_check")).all() == []


def test_association_tables_are_writable(graph, db):
    """
    Insert into every association table that the fixture already populated.

    A malformed foreign key does not stop ``create_all``; it stops ``INSERT``.
    Writing one more row into each association table is the only way to find that
    out, and it is exactly how the ``last_used_lot`` bug surfaced.
    """
    import backend.db.models as M

    association_classes = [
        cls for cls in (
            M.ClientSubmissionSampleAssociation,
            M.EquipmentRoleEquipmentAssociation,
            M.ProcedureEquipmentAssociation,
            M.ProcedureReagentLotAssociation,
            M.ProcedureSampleAssociation,
            M.ProcedureTypeEquipmentRoleAssociation,
            M.ProcedureTypeReagentRoleAssociation,
            M.ReagentRoleReagentAssociation,
            M.RunSampleAssociation,
        )
    ]
    failures = []
    for cls in association_classes:
        rows = db.query(cls).all()
        if not rows:
            continue
        # Re-writing an existing row's own columns is enough to trip a malformed
        # FK, without needing to invent a valid new key for each table.
        row = rows[0]
        try:
            db.add(row)
            db.flush()
        except Exception as exc:
            db.rollback()
            failures.append(f"{cls.__name__}: {type(exc).__name__}: {str(exc)[:160]}")
    assert not failures, "association tables rejected writes:\n  " + "\n  ".join(failures)


def test_reagentlot_multi_row_insert(graph, db):
    """
    Flush several ``ReagentLot`` rows at once.

    SQLAlchemy batches multi-row inserts differently from single-row ones, and a
    malformed foreign key on ``_reagentlot`` showed up only in the batched path --
    inserting one lot at a time slipped past the check and hid the problem.
    """
    from backend.db.models import ReagentLot

    reagent = next(iter(graph["reagents"].values()))
    db.add_all([
        ReagentLot(reagent=reagent, lot=f"BATCH-TEST-{i}", active=True)
        for i in range(4)
    ])
    db.commit()
    assert db.query(ReagentLot).filter(
        ReagentLot.lot.like("BATCH-TEST-%")).count() == 4


def test_lot_uniqueness_matches_the_declared_constraint(graph, db):
    """
    Pin whichever uniqueness rule ``ReagentLot.lot`` currently declares.

    Making ``lot`` globally unique is what makes the ``last_used_lot`` foreign key
    well-formed, but it also forbids two different reagent products from sharing a
    lot string. That is a real data-modelling decision, so it gets an explicit
    test rather than being left implicit in a column definition.
    """
    from sqlalchemy.exc import IntegrityError

    from backend.db.models import ReagentLot

    reagents = list(graph["reagents"].values())
    assert len(reagents) >= 2, "need two distinct reagents"

    db.add(ReagentLot(reagent=reagents[0], lot="SHARED-LOT", active=True))
    db.commit()

    db.add(ReagentLot(reagent=reagents[1], lot="SHARED-LOT", active=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
