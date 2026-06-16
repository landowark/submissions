"""
Pytest harness for the ``query()`` characterization suite.

These tests pin the *current* behavior of every ``BaseClass.query()`` override so
the repetitive ``match/case`` filter blocks can be collapsed into shared helpers
without changing what each query returns.

How the harness works
---------------------
* ``tools.ctx`` is instantiated at import time and needs a database config, so we
  write a minimal sqlite ``config.yml`` into the location ``Settings`` searches —
  but only if the developer doesn't already have one (we never clobber a real
  config).
* ``Settings.set_from_db`` already short-circuits to hardcoded defaults when
  ``'pytest' in sys.modules``, so importing the app under pytest does not touch
  any database.
* The ``db`` fixture then throws away whatever engine the config produced and
  wires ``ctx.database`` to a fresh in-memory SQLite database per test, with all
  tables created from ``Base.metadata``. Full isolation, no shared state.
"""
from __future__ import annotations

import platform
import sys
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# 1. Put the application package roots on sys.path.                            #
#    The app imports its modules as top-level names (``tools``, ``backend``,   #
#    ``frontend``), so ``src/submissions`` must be importable.                 #
# --------------------------------------------------------------------------- #
SRC = Path(__file__).resolve().parents[1] / "src" / "submissions"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# --------------------------------------------------------------------------- #
# 2. Ensure a database config exists before ``tools`` is imported.            #
#    Mirrors ``Settings.main_aux_dir`` so we write to the same place it looks. #
# --------------------------------------------------------------------------- #
def _aux_config_dir() -> Path:
    os_config_dir = "AppData/local" if platform.system() == "Windows" else ".config"
    return Path.home() / os_config_dir / "submissions_tng" / "config"


def _ensure_minimal_config() -> None:
    search_locations = [
        _aux_config_dir() / "config.yml",
        Path.home() / ".submissions_tng" / "config.yml",
    ]
    if any(p.exists() for p in search_locations):
        # A real config is present; importing tools is harmless under pytest
        # (no DB access) and the ``db`` fixture overrides the engine anyway.
        return
    target = _aux_config_dir()
    target.mkdir(parents=True, exist_ok=True)
    (target / "config.yml").write_text(
        "database:\n"
        "  schema: sqlite\n"
        "  path: /tmp\n"
        "  name: test_submissions\n"
    )


_ensure_minimal_config()


# --------------------------------------------------------------------------- #
# 3. Per-test in-memory database wired into ctx.                              #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def db():
    """
    Yield a fresh, isolated in-memory SQLite session wired into ``ctx.database``.

    A new engine + schema is built for every test so rows from one test can never
    leak into another. The single shared connection (StaticPool) keeps the
    in-memory database alive for the duration of the test.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import scoped_session, sessionmaker
    from sqlalchemy.pool import StaticPool

    import tools
    from backend.db.models import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = scoped_session(sessionmaker(bind=engine))

    prev = (tools.ctx.database.get("engine"),
            tools.ctx.database.get("session"),
            tools.ctx.database.get("schema"))
    tools.ctx.database.engine = engine
    tools.ctx.database.session = Session
    tools.ctx.database.schema = "sqlite"

    try:
        yield Session
    finally:
        Session.remove()
        engine.dispose()
        tools.ctx.database.engine, tools.ctx.database.session, tools.ctx.database.schema = prev


@pytest.fixture()
def seed(db):
    """
    Return a helper that inserts a row via SQLAlchemy Core and returns the ORM
    object.

    Core inserts are used deliberately: the models' ``__init__`` methods perform
    relationship coercion (e.g. ``ProcedureType`` auto-wires a ``SubmissionType``),
    which makes ORM construction fragile for fixtures. Writing columns directly
    keeps seeding explicit and decoupled from constructor behavior.
    """
    from sqlalchemy import text

    def _seed(cls, fk_checks=True, **values):
        # ``ProcedureTypeReagentRoleAssociation.last_used_lot`` is a FK to a
        # non-unique column (``_reagentlot.lot``), which SQLite rejects as a
        # "foreign key mismatch". Such rows are seeded with fk_checks=False.
        if not fk_checks:
            db.execute(text("PRAGMA foreign_keys=OFF"))
        try:
            result = db.execute(cls.__table__.insert().values(**values))
            db.commit()
        finally:
            if not fk_checks:
                db.execute(text("PRAGMA foreign_keys=ON"))
        pk = result.inserted_primary_key
        ident = pk[0] if len(pk) == 1 else tuple(pk)
        return db.get(cls, ident)

    return _seed