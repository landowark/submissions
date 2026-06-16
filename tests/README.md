# `query()` characterization tests

These tests pin the **current** behavior of every `BaseClass.query()` override so
the repetitive `match/case` filter blocks can be collapsed into shared helpers
without silently changing what any query returns. They are characterization
(golden-master) tests: each one asserts the existing return shape and row
selection, so a green run after refactoring means behavior was preserved.

All 26 classes that define their own `query()` are covered:

| Module | Classes under test |
|---|---|
| `test_query_catalog.py` | ClientLab, Contact, SubmissionType, ProcedureType, Process, ReagentRole, Reagent, EquipmentRole, Equipment, Tips, Sample |
| `test_query_relationships.py` | ReagentLot, TipsLot, ProcessVersion, Discount |
| `test_query_submissions.py` | ClientSubmission, Run, ClientSubmissionSampleAssociation, RunSampleAssociation |
| `test_query_procedure_associations.py` | Procedure, ProcedureReagentLotAssociation, ProcedureTypeReagentRoleAssociation, EquipmentRoleEquipmentAssociation, ProcedureTypeEquipmentRoleAssociation, ProcedureEquipmentAssociation, ProcedureSampleAssociation |

## Running

From the repository root:

```bash
QT_QPA_PLATFORM=offscreen pytest tests/
```

`QT_QPA_PLATFORM=offscreen` avoids needing a display — importing the models pulls
in the frontend (PyQt6/WebEngine/plotly) because `procedures.py` imports from
`frontend.widgets` at module load. (That import-time coupling is worth breaking
later so the backend can be tested without the GUI stack.)

## How the harness works

* `conftest.py` adds `src/submissions` to `sys.path`, ensures a minimal sqlite
  `config.yml` exists so `tools.ctx` can be constructed (it does **not** overwrite
  an existing config), and provides two fixtures:
  * `db` — a fresh in-memory SQLite database wired into `ctx.database` per test,
    with all tables created from `Base.metadata`. Full isolation; no shared state.
  * `seed` — inserts a row via SQLAlchemy **Core** and returns the ORM object.
    Core inserts are used so fixtures don't go through the models' `__init__`
    coercion (e.g. `ProcedureType` auto-wiring a `SubmissionType`).
* `Settings.set_from_db` already short-circuits when `'pytest' in sys.modules`, so
  importing the app under pytest never touches a real database.
* `factories.py` holds small builders that assemble only as much of the relational
  graph as a given query needs.

## Behaviors deliberately pinned (per-method quirks)

These are inconsistencies in the current code that the tests lock in. They are the
exact cases most likely to drift when collapsing the filter blocks — decide
intentionally whether to preserve or normalize each during the refactor:

* `Reagent.query(name=...)` returns a **list**, not a single object (most `name`
  lookups force a single result; this one does not).
* `Tips.query(ref=...)` returns a single object, but `Tips.query(manufacturer=...)`
  returns a list.
* `ReagentLot.query(name=...)` and `TipsLot.query(name=...)` return `None` — the
  `name` hybrid is not the bare lot string, so a lot value never matches via `name`.
* `ProcessVersion.query(name=...)` filters the version label, not the parent
  process name, so a process name returns `[]`.

## Known schema defect surfaced while building these

`ProcedureTypeReagentRoleAssociation.last_used_lot` (`procedures.py`, ~line 2718)
is a `ForeignKey("_reagentlot.lot")` — a foreign key to a **non-unique** column.
SQLite rejects this as a "foreign key mismatch" on insert, so that one row is
seeded with FK enforcement disabled (`seed(..., fk_checks=False)`). The query
itself is unaffected. The FK should target `_reagentlot.id` (or `lot` should be
made unique).