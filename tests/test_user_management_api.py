from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.orm import Session

from chemstock.models import User
from chemstock.roles import Role

PASSWORD = "a long enough password"
ClientFactory = Callable[[Role], TestClient]


def _add(session: Session, username: str, role: str, *, active: bool = True) -> int:
    """Insert a user directly (no password hashing, so it is fast)."""
    user = User(username=username, hashed_password="x", role=role, is_active=active)
    session.add(user)
    session.commit()
    return user.id


def _row(session: Session, user_id: int) -> User:
    """Read a user fresh from the database (the API changed it, not this session)."""
    session.expire_all()
    return session.get_one(User, user_id)


def _create(
    client: TestClient, username: str, role: str, password: str = PASSWORD
) -> Response:
    return client.post(
        "/users", json={"username": username, "password": password, "role": role}
    )


def _names(client: TestClient, **params: int) -> list[str]:
    response = client.get("/users", params=params)
    assert response.status_code == 200
    return [user["username"] for user in response.json()]


@pytest.mark.parametrize("role", [Role.VIEWER, Role.MEMBER])
def test_viewers_and_members_cannot_use_user_management(
    client_as: ClientFactory, role: Role
) -> None:
    client = client_as(role)

    assert client.get("/users").status_code == 403
    assert client.get("/users/1").status_code == 403
    assert _create(client, "bob", "viewer").status_code == 403
    assert client.patch("/users/1", json={"is_active": False}).status_code == 403


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OWNER])
def test_admin_and_owner_can_list_and_read_users(
    client_as: ClientFactory, role: Role
) -> None:
    client = client_as(role)

    listing = client.get("/users")

    assert listing.status_code == 200
    [me] = listing.json()
    assert me["username"] == f"test-{role.value}"
    assert "hashed_password" not in me
    one = client.get(f"/users/{me['id']}")
    assert one.status_code == 200
    assert one.json() == me


def test_list_users_supports_pagination(
    client_as: ClientFactory, session: Session
) -> None:
    client = client_as(Role.ADMIN)
    for name in ("bob", "carol", "dave"):
        _add(session, name, "viewer")

    assert _names(client, limit=2) == ["test-admin", "bob"]
    assert _names(client, limit=2, offset=2) == ["carol", "dave"]
    assert client.get("/users", params={"limit": 0}).status_code == 422


def test_unknown_or_invalid_user_ids(client_as: ClientFactory) -> None:
    client = client_as(Role.ADMIN)

    assert client.get("/users/999").status_code == 404
    assert client.patch("/users/999", json={"is_active": False}).status_code == 404
    assert client.get("/users/0").status_code == 422


def test_admin_creates_a_member_who_can_then_log_in(
    client_as: ClientFactory, anonymous_client: TestClient
) -> None:
    created = _create(client_as(Role.ADMIN), "Bob", "member")

    assert created.status_code == 201
    body = created.json()
    assert (body["username"], body["role"]) == ("bob", "member")
    assert body["is_active"] is True
    assert "hashed_password" not in body
    assert "password" not in body
    login = anonymous_client.post(
        "/auth/login", data={"username": "bob", "password": PASSWORD}
    )
    assert login.status_code == 200


@pytest.mark.parametrize(
    ("actor", "new_role", "expected"),
    [
        (Role.ADMIN, "member", 201),
        (Role.ADMIN, "viewer", 201),
        (Role.ADMIN, "admin", 403),
        (Role.ADMIN, "owner", 403),
        (Role.OWNER, "member", 201),
        (Role.OWNER, "viewer", 201),
        (Role.OWNER, "admin", 201),
        (Role.OWNER, "owner", 403),
    ],
)
def test_who_may_create_which_role(
    client_as: ClientFactory, actor: Role, new_role: str, expected: int
) -> None:
    response = _create(client_as(actor), "newcomer", new_role)

    assert response.status_code == expected


def test_duplicate_username_returns_conflict(client_as: ClientFactory) -> None:
    client = client_as(Role.ADMIN)
    assert _create(client, "bob", "member").status_code == 201

    assert _create(client, "BOB", "viewer").status_code == 409


@pytest.mark.parametrize(
    ("username", "password"),
    [("ab", PASSWORD), ("has space", PASSWORD), ("bob", "short")],
    ids=["short-username", "bad-characters", "short-password"],
)
def test_invalid_new_user_is_rejected_without_echoing_the_password(
    client_as: ClientFactory, username: str, password: str
) -> None:
    response = _create(client_as(Role.ADMIN), username, "member", password)

    assert response.status_code == 422
    assert password not in response.text


def test_unknown_role_is_rejected(client_as: ClientFactory) -> None:
    assert _create(client_as(Role.ADMIN), "bob", "root").status_code == 422


def test_validation_errors_do_not_echo_submitted_data(
    client_as: ClientFactory,
) -> None:
    secret = "super secret passphrase"

    # The role is missing, so FastAPI's default answer would repeat the body.
    response = client_as(Role.ADMIN).post(
        "/users", json={"username": "bob", "password": secret}
    )

    assert response.status_code == 422
    assert secret not in response.text


def test_admin_can_change_roles_between_member_and_viewer(
    client_as: ClientFactory, session: Session
) -> None:
    client = client_as(Role.ADMIN)
    bob = _add(session, "bob", "member")

    to_viewer = client.patch(f"/users/{bob}", json={"role": "viewer"})
    to_member = client.patch(f"/users/{bob}", json={"role": "member"})

    assert (to_viewer.status_code, to_viewer.json()["role"]) == (200, "viewer")
    assert (to_member.status_code, to_member.json()["role"]) == (200, "member")


def test_admin_can_deactivate_and_reactivate_a_member(
    client_as: ClientFactory, session: Session
) -> None:
    client = client_as(Role.ADMIN)
    bob = _add(session, "bob", "member")

    off = client.patch(f"/users/{bob}", json={"is_active": False})
    assert off.status_code == 200
    assert off.json()["is_active"] is False
    assert _row(session, bob).is_active is False

    on = client.patch(f"/users/{bob}", json={"is_active": True})
    assert on.json()["is_active"] is True


def test_a_deactivated_user_cannot_log_in(
    client_as: ClientFactory, anonymous_client: TestClient
) -> None:
    admin = client_as(Role.ADMIN)
    bob = _create(admin, "bob", "member").json()["id"]
    credentials = {"username": "bob", "password": PASSWORD}
    assert anonymous_client.post("/auth/login", data=credentials).status_code == 200

    admin.patch(f"/users/{bob}", json={"is_active": False})

    assert anonymous_client.post("/auth/login", data=credentials).status_code == 401


@pytest.mark.parametrize(
    ("actor", "target_role", "change"),
    [
        (Role.ADMIN, "admin", {"is_active": False}),
        (Role.ADMIN, "admin", {"role": "member"}),
        (Role.ADMIN, "owner", {"is_active": False}),
        (Role.ADMIN, "owner", {"role": "admin"}),
        (Role.ADMIN, "member", {"role": "admin"}),
        (Role.ADMIN, "member", {"role": "owner"}),
        (Role.OWNER, "member", {"role": "owner"}),
        (Role.OWNER, "admin", {"role": "owner"}),
    ],
)
def test_forbidden_changes_are_refused_and_change_nothing(
    client_as: ClientFactory,
    session: Session,
    actor: Role,
    target_role: str,
    change: dict[str, object],
) -> None:
    target = _add(session, "target", target_role)

    response = client_as(actor).patch(f"/users/{target}", json=change)

    assert response.status_code == 403
    row = _row(session, target)
    assert (row.role, row.is_active) == (target_role, True)


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OWNER])
def test_nobody_can_change_their_own_account(
    client_as: ClientFactory, session: Session, role: Role
) -> None:
    client = client_as(role)
    my_id = client.get("/auth/me").json()["id"]

    for change in ({"is_active": False}, {"role": "viewer"}):
        assert client.patch(f"/users/{my_id}", json=change).status_code == 403

    row = _row(session, my_id)
    assert (row.role, row.is_active) == (role.value, True)


def test_the_owner_controls_admins(
    client_as: ClientFactory, session: Session
) -> None:
    owner = client_as(Role.OWNER)
    ann = _add(session, "ann", "admin")

    demoted = owner.patch(f"/users/{ann}", json={"role": "member"})
    promoted = owner.patch(f"/users/{ann}", json={"role": "admin"})
    off = owner.patch(f"/users/{ann}", json={"is_active": False})
    on = owner.patch(f"/users/{ann}", json={"is_active": True})

    codes = [response.status_code for response in (demoted, promoted, off, on)]
    assert codes == [200, 200, 200, 200]
    assert (demoted.json()["role"], promoted.json()["role"]) == ("member", "admin")
    assert (off.json()["is_active"], on.json()["is_active"]) == (False, True)


def test_the_owner_can_promote_a_member_to_admin(
    client_as: ClientFactory, session: Session
) -> None:
    bob = _add(session, "bob", "member")

    response = client_as(Role.OWNER).patch(f"/users/{bob}", json={"role": "admin"})

    assert response.status_code == 200
    assert _row(session, bob).role == "admin"


def test_the_owner_survives_every_attempt_to_change_the_account(
    client_as: ClientFactory, session: Session
) -> None:
    owner = client_as(Role.OWNER)
    owner_id = owner.get("/auth/me").json()["id"]
    admin = client_as(Role.ADMIN)

    for change in ({"is_active": False}, {"role": "admin"}, {"role": "viewer"}):
        assert admin.patch(f"/users/{owner_id}", json=change).status_code == 403
        assert owner.patch(f"/users/{owner_id}", json=change).status_code == 403

    row = _row(session, owner_id)
    assert (row.role, row.is_active) == ("owner", True)


def test_admins_cannot_deactivate_each_other(
    client_as: ClientFactory, session: Session
) -> None:
    first = client_as(Role.ADMIN)
    second = _add(session, "second-admin", "admin")

    response = first.patch(f"/users/{second}", json={"is_active": False})

    assert response.status_code == 403
    assert _row(session, second).is_active is True


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"role": None},
        {"is_active": None},
        {"role": "root"},
        {"username": "x"},
        {"password": "a new password here"},
    ],
    ids=["empty", "null-role", "null-flag", "unknown-role", "fixed-name", "password"],
)
def test_invalid_updates_are_rejected_and_change_nothing(
    client_as: ClientFactory, session: Session, body: dict[str, object]
) -> None:
    client = client_as(Role.ADMIN)
    bob = _add(session, "bob", "member")

    assert client.patch(f"/users/{bob}", json=body).status_code == 422

    row = _row(session, bob)
    assert (row.role, row.is_active) == ("member", True)
