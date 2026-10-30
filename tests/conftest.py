from collections.abc import Callable, Iterator
from datetime import timedelta
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
from chemstock.models import User
from chemstock.roles import Role
from chemstock.security import hash_password
from chemstock.tokens import create_access_token

ROOT = Path(__file__).resolve().parent.parent
TEST_DB_NAME = "chemstock_test"
TEST_SECRET_KEY = "test-only-secret-key-do-not-use-in-production"
TEST_PASSWORD = "a long enough password"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)  # one hash for all users


def _reset_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()


@pytest.fixture(scope="session")
def _test_database() -> Iterator[None]:
    """Create and migrate a dedicated test database (never the dev one)."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("POSTGRES_DB", TEST_DB_NAME)
        monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
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
                "TRUNCATE TABLE inventory_items, chemical_hazard_classes, chemicals, "
                "users, revoked_permissions, auth_attempts "
                "RESTART IDENTITY"
            )
        )


def _auth_headers(role: Role) -> dict[str, str]:
    """Create a user with this role and return headers carrying their token."""
    with Session(get_engine()) as db_session:
        user = User(
            username=f"test-{role.value}",
            hashed_password=TEST_PASSWORD_HASH,  # tests mint tokens directly
            role=role.value,
        )
        db_session.add(user)
        db_session.commit()
        user_id = user.id
    token = create_access_token(str(user_id), TEST_SECRET_KEY, timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def anonymous_client(clean_database: None) -> Iterator[TestClient]:
    """A client that is not logged in."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_as(clean_database: None) -> Iterator[Callable[[Role], TestClient]]:
    """Build a client logged in as a user with the given role (once per role)."""
    clients: dict[Role, TestClient] = {}

    def build(role: Role) -> TestClient:
        if role not in clients:
            clients[role] = TestClient(app, headers=_auth_headers(role))
        return clients[role]

    yield build
    for test_client in clients.values():
        test_client.close()


@pytest.fixture
def client(client_as: Callable[[Role], TestClient]) -> TestClient:
    """The default client is an admin, so ordinary API tests need no auth code."""
    return client_as(Role.ADMIN)


@pytest.fixture
def session(clean_database: None) -> Iterator[Session]:
    """A direct database session, for arranging or inspecting test data."""
    with Session(get_engine()) as db_session:
        yield db_session
