from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.tokens import create_access_token
from chemstock.users import create_user

PASSWORD = "a long enough password"


def _login(
    client: TestClient, username: str = "alice", password: str = PASSWORD
) -> Response:
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


def _me(client: TestClient, token: str) -> Response:
    return client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})


def _token(subject: str, *, now: datetime | None = None, key: str | None = None) -> str:
    secret = key or get_settings().secret_key.get_secret_value()
    return create_access_token(subject, secret, timedelta(minutes=5), now=now)


def test_login_returns_a_bearer_token(client: TestClient, session: Session) -> None:
    create_user(session, "alice", PASSWORD, "member")

    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert body["access_token"]


def test_token_identifies_the_user(client: TestClient, session: Session) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    token = _login(client).json()["access_token"]

    response = _me(client, token)

    assert response.status_code == 200
    body = response.json()
    assert (body["id"], body["username"], body["role"]) == (user.id, "alice", "member")
    assert body["is_active"] is True
    assert "hashed_password" not in body


def test_login_ignores_case_and_spaces_of_the_username(
    client: TestClient, session: Session
) -> None:
    create_user(session, "alice", PASSWORD, "member")

    assert _login(client, "  ALICE ").status_code == 200


@pytest.mark.parametrize(
    ("username", "password"),
    [("alice", "a completely wrong password"), ("ghost", PASSWORD)],
    ids=["wrong-password", "unknown-user"],
)
def test_failed_logins_look_identical(
    client: TestClient, session: Session, username: str, password: str
) -> None:
    create_user(session, "alice", PASSWORD, "member")

    response = _login(client, username, password)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json() == {"detail": "Incorrect username or password"}


def test_inactive_user_cannot_log_in(client: TestClient, session: Session) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    user.is_active = False
    session.commit()

    assert _login(client).status_code == 401


def test_overlong_password_is_rejected(client: TestClient, session: Session) -> None:
    create_user(session, "alice", PASSWORD, "member")

    assert _login(client, password="x" * 1000).status_code == 401


def test_login_requires_both_form_fields(client: TestClient) -> None:
    response = client.post("/auth/login", data={"username": "alice"})

    assert response.status_code == 422


def test_login_does_not_accept_a_json_body(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"username": "alice", "password": PASSWORD}
    )

    assert response.status_code == 422


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_me_rejects_garbage_tokens(client: TestClient, token: str) -> None:
    assert _me(client, token).status_code == 401


def test_me_rejects_an_expired_token(client: TestClient, session: Session) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    token = _token(str(user.id), now=datetime(2020, 1, 1, tzinfo=UTC))

    assert _me(client, token).status_code == 401


def test_me_rejects_a_token_signed_with_another_key(
    client: TestClient, session: Session
) -> None:
    user = create_user(session, "alice", PASSWORD, "member")

    assert _me(client, _token(str(user.id), key="z" * 64)).status_code == 401


@pytest.mark.parametrize(
    "subject",
    ["alice", "0", "-1", "9" * 20, " 1", "999"],
    ids=["name", "zero", "negative", "huge", "space", "no-such-user"],
)
def test_me_rejects_a_subject_that_is_not_a_known_user(
    client: TestClient, subject: str
) -> None:
    assert _me(client, _token(subject)).status_code == 401


def test_deactivated_user_loses_access_immediately(
    client: TestClient, session: Session
) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    token = _login(client).json()["access_token"]
    assert _me(client, token).status_code == 200

    user.is_active = False
    session.commit()

    assert _me(client, token).status_code == 401


def test_role_change_takes_effect_immediately(
    client: TestClient, session: Session
) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    token = _login(client).json()["access_token"]

    user.role = "viewer"
    session.commit()

    assert _me(client, token).json()["role"] == "viewer"


def test_deleted_user_loses_access(client: TestClient, session: Session) -> None:
    user = create_user(session, "alice", PASSWORD, "member")
    token = _login(client).json()["access_token"]

    session.delete(user)
    session.commit()

    assert _me(client, token).status_code == 401
