from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.db import get_engine
from chemstock.main import app

ROOT = Path(__file__).resolve().parent.parent
TEST_DB_NAME = "chemstock_test"


def _reset_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture(scope="session")
def _test_database() -> Iterator[None]:
    """Create and migrate a dedicated test database (never the dev one)."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("POSTGRES_DB", TEST_DB_NAME)
        _reset_caches()
        settings = get_settings()
        assert settings.postgres_db == TEST_DB_NAME

        admin_engine = create_engine(
            settings.database_url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
        )
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
        admin_engine.dispose()

        alembic_config = Config(str(ROOT / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(alembic_config, "head")

        yield

        get_engine().dispose()
        _reset_caches()


@pytest.fixture
def clean_database(_test_database: None) -> None:
    """Empty every table before each test (and never touch the dev database)."""
    engine = get_engine()
    assert engine.url.database == TEST_DB_NAME  # safety net
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE inventory_items, chemical_hazard_classes, chemicals "
                "RESTART IDENTITY"
            )
        )


@pytest.fixture
def client(clean_database: None) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session(clean_database: None) -> Iterator[Session]:
    """A direct database session, for arranging or inspecting test data."""
    with Session(get_engine()) as db_session:
        yield db_session
