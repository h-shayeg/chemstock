from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chemstock.models import AuthAttempt
from chemstock.throttle import LOGIN
from chemstock.users import create_user

PASSWORD = "a long enough password"
WRONG = "definitely the wrong password"
NEW = "a brand new long password"
BLOCKED = {"detail": "Too many failed attempts. Try again later."}


@pytest.fixture
def client(anonymous_client: TestClient) -> TestClient:
    """Everything in this file starts without credentials."""
    return anonymous_client


def _login(
    client: TestClient, username: str = "alice", password: str = PASSWORD
) -> Response:
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


def _wrong_logins(client: TestClient, username: str, count: int) -> list[int]:
    return [_login(client, username, WRONG).status_code for _ in range(count)]


def test_repeated_failures_lead_to_429(client: TestClient, session: Session) -> None:
    create_user(session, "alice", PASSWORD, "member")

    assert _wrong_logins(client, "alice", 6) == [401] * 5 + [429]


def test_the_429_answer_says_when_to_retry(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")
    _wrong_logins(client, "alice", 5)

    blocked = _login(client, "alice", WRONG)

    assert blocked.status_code == 429
    assert blocked.json() == BLOCKED
    assert 1 <= int(blocked.headers["Retry-After"]) <= 15 * 60


def test_a_correct_password_is_refused_during_a_lockout(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")
    _wrong_logins(client, "alice", 5)

    assert _login(client).status_code == 429


def test_unknown_users_are_throttled_like_real_ones(client: TestClient) -> None:
    assert _wrong_logins(client, "ghost", 6) == [401] * 5 + [429]


def test_blocked_answers_look_the_same_for_real_and_unknown_users(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")
    _wrong_logins(client, "alice", 5)
    _wrong_logins(client, "ghost", 5)

    real = _login(client, "alice", WRONG)
    unknown = _login(client, "ghost", WRONG)

    assert real.status_code == unknown.status_code == 429
    assert real.json() == unknown.json() == BLOCKED


def test_a_locked_username_does_not_block_another_one(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")
    create_user(session, "bob", PASSWORD, "member")
    _wrong_logins(client, "alice", 6)

    assert _login(client, "bob").status_code == 200


def test_a_successful_login_resets_the_counter(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")
    assert _wrong_logins(client, "alice", 4) == [401] * 4
    assert _login(client).status_code == 200

    assert _wrong_logins(client, "alice", 6) == [401] * 5 + [429]


def test_one_address_cannot_try_many_usernames(client: TestClient) -> None:
    codes = [_login(client, f"ghost-{i}", WRONG).status_code for i in range(21)]

    assert codes == [401] * 20 + [429]


def test_old_attempts_do_not_count(client: TestClient, session: Session) -> None:
    create_user(session, "alice", PASSWORD, "member")
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    session.add_all(
        AuthAttempt(
            scope=LOGIN,
            username="alice",
            ip_address="testclient",
            attempted_at=long_ago,
        )
        for _ in range(5)
    )
    session.commit()

    assert _login(client).status_code == 200


def test_blocked_requests_are_not_recorded(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")

    _wrong_logins(client, "alice", 7)

    assert session.scalar(select(func.count()).select_from(AuthAttempt)) == 5


def test_changing_the_password_is_throttled_separately(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")
    token = _login(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def change(current: str) -> Response:
        body = {"current_password": current, "new_password": NEW}
        return client.post("/auth/change-password", json=body, headers=headers)

    assert [change(WRONG).status_code for _ in range(5)] == [400] * 5
    blocked = change(PASSWORD)  # the right password, but during the lockout

    assert blocked.status_code == 429
    assert blocked.json() == BLOCKED
    assert "Retry-After" in blocked.headers
    # Logging in has its own counter, and the password was not changed.
    assert _login(client).status_code == 200
