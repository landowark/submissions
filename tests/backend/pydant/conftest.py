"""Pytest configuration for pydant tests.

This module sets up a toy database for all pydant tests, ensuring that
sql_instances created during test execution are properly bound to the
test database session.
"""
import sys
import pytest

if "C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")

if "C:\\Users\\lwark\\Documents\\python\\submissions\\tests\\backend\\database" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\tests\\backend\\database")

from tests.resources.toy_database import make_toy_db


@pytest.fixture(scope="function")
def toy_db():
    """Create and populate a toy database for testing.
    
    Yields:
        tuple: (engine, session) for database interaction
    """
    engine, session = make_toy_db(populate=True)
    yield engine, session
    # Cleanup
    try:
        session.close()
    except Exception:
        pass
    try:
        engine.dispose()
    except Exception:
        pass


@pytest.fixture(scope="function", autouse=True)
def reset_database(toy_db):
    """Automatically use the toy database for all tests."""
    # The toy_db fixture is called, which initializes ctx.database_session
    # All model queries will use this session automatically
    pass
