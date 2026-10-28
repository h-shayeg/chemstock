from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.orm import Session

from chemstock.config import get_settings
from chemstock.tokens import create_access_token
from chemstock.users import create_user

OLD = "the old long password"
NEW = "a brand new long password"


def _login(
    client: TestClient, username: str = "alice", password: str = OLD
) -> Response:
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


def _token(client: TestClient, username: str = "alice", password: str = OLD) -> str:
    response = _login(client, username, password)
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _change(
    client: TestClient, token: str, current: str = OLD, new: str = NEW
) -> Response:
    return client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=_auth(token),
    )


def _me(client: TestClient, token: str) -> int:
    return client.get("/auth/me", headers=_auth(token)).status_code


def _secret() -> str:
    return get_settings().secret_key.get_secret_value()


def test_password_can_be_changed_and_only_the_new_one_works(
    anonymous_client: TestClient, session: Session
) -> None:
    create_user(session, "alice", OLD, "member")
    token = _token(anonymous_client)

    response = _change(anonymous_client, token)

    assert response.status_code == 204
    assert _login(anonymous_client, password=OLD).status_code == 401
    assert _login(anonymous_client, password=NEW).status_code == 200


def test_old_tokens_stop_working_after_the_change(
    anonymous_client: TestClient, session: Session
) -> None:
    create_user(session, "alice", OLD, "member")
    old_token = _token(anonymous_client)
    assert _me(anonymous_client, old_token) == 200

    _change(anonymous_client, old_token)

    assert _me(anonymous_client, old_token) == 401
    assert _me(anonymous_client, _token(anonymous_client, password=NEW)) == 200


def test_the_token_version_counts_every_change(
    anonymous_client: TestClient, session: Session
) -> None:
    user = create_user(session, "alice", OLD, "member")
    assert user.token_version == 0

    _change(anonymous_client, _token(anonymous_client), OLD, NEW)
    session.refresh(user)
    assert user.token_version == 1

    _change(anonymous_client, _token(anonymous_client, password=NEW), NEW, OLD)
    session.refresh(user)
    assert user.token_version == 2


def test_wrong_current_password_changes_nothing(
    anonymous_client: TestClient, session: Session
) -> None:
    create_user(session, "alice", OLD, "member")
    token = _token(anonymous_client)

    response = _change(anonymous_client, token, current="not the right one")

    assert response.status_code == 400
    assert _login(anonymous_client, password=OLD).status_code == 200
    assert _me(anonymous_client, token) == 200


def test_overlong_current_password_is_rejected(
    anonymous_client: TestClient, session: Session
) -> None:
    create_user(session, "alice", OLD, "member")

    response = _change(anonymous_client, _token(anonymous_client), current="x" * 1000)

    assert response.status_code == 400


@pytest.mark.parametrize(
    "new_password",
    ["short", "x" * 129, OLD],
    ids=["too-short", "too-long", "same-as-current"],
)
def test_unacceptable_new_password_changes_nothing(
    anonymous_client: TestClient, session: Session, new_password: str
) -> None:
    create_user(session, "alice", OLD, "member")
    token = _token(anonymous_client)

    response = _change(anonymous_client, token, new=new_password)

    assert response.status_code == 422
    assert _login(anonymous_client, password=OLD).status_code == 200
    assert _me(anonymous_client, token) == 200


def test_changing_the_password_needs_a_login(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        "/auth/change-password",
        json={"current_password": OLD, "new_password": NEW},
    )

    assert response.status_code == 401


def test_other_users_keep_their_tokens(
    anonymous_client: TestClient, session: Session
) -> None:
    create_user(session, "alice", OLD, "member")
    create_user(session, "bob", OLD, "member")
    alice = _token(anonymous_client, "alice")
    bob = _token(anonymous_client, "bob")

    _change(anonymous_client, alice)

    assert _me(anonymous_client, bob) == 200


def test_passwords_never_appear_in_error_answers(
    anonymous_client: TestClient, session: Session
) -> None:
    create_user(session, "alice", OLD, "member")
    token = _token(anonymous_client)
    wrong = _change(anonymous_client, token, current="a wrong current password")
    weak = _change(anonymous_client, token, new="short")
    missing = anonymous_client.post(
        "/auth/change-password", json={"current_password": OLD}, headers=_auth(token)
    )

    assert missing.status_code == 422
    for response, secret in (
        (wrong, "a wrong current password"),
        (weak, "short"),
        (missing, OLD),
    ):
        assert secret not in response.text


def test_token_without_a_version_is_refused(
    anonymous_client: TestClient, session: Session
) -> None:
    user = create_user(session, "alice", OLD, "member")
    claims = {"sub": str(user.id), "exp": datetime.now(UTC) + timedelta(minutes=5)}

    token = jwt.encode(claims, _secret(), algorithm="HS256")

    assert _me(anonymous_client, token) == 401


def test_token_with_the_wrong_version_is_refused(
    anonymous_client: TestClient, session: Session
) -> None:
    user = create_user(session, "alice", OLD, "member")
    expires = timedelta(minutes=5)
    right = create_access_token(str(user.id), _secret(), expires, version=0)
    wrong = create_access_token(str(user.id), _secret(), expires, version=5)

    assert _me(anonymous_client, right) == 200
    assert _me(anonymous_client, wrong) == 401
