from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.models import RevokedPermission, User
from chemstock.permissions import Permission
from chemstock.roles import Role

PASSWORD = "a long enough password"
ALL = [permission.value for permission in Permission]
ClientFactory = Callable[[Role], TestClient]


def _add(session: Session, username: str, role: str) -> int:
    """Insert a user directly (no password hashing, so it is fast)."""
    user = User(username=username, hashed_password="x", role=role)
    session.add(user)
    session.commit()
    return user.id


def _my_id(client: TestClient) -> int:
    return client.get("/auth/me").json()["id"]


def _set(owner: TestClient, user_id: int, permissions: object) -> Response:
    return owner.put(
        f"/users/{user_id}/permissions", json={"permissions": permissions}
    )


def _permissions_of(client: TestClient, user_id: int) -> list[str]:
    return client.get(f"/users/{user_id}").json()["permissions"]


def _new_user_body(username: str) -> dict[str, str]:
    return {"username": username, "password": PASSWORD, "role": "viewer"}


def _attempt(admin: TestClient, session: Session, action: Permission) -> int:
    """Try the one thing that `action` guards, as this admin; return the status."""
    if action is Permission.CREATE_USERS:
        return admin.post("/users", json=_new_user_body("newcomer")).status_code
    victim = _add(session, f"victim-{action.value}", "member")
    if action is Permission.CHANGE_ROLES:
        change: dict[str, object] = {"role": "viewer"}
    else:
        change = {"is_active": False}
    return admin.patch(f"/users/{victim}", json=change).status_code


def test_default_permissions_by_role(client_as: ClientFactory) -> None:
    expected = {Role.OWNER: ALL, Role.ADMIN: ALL, Role.MEMBER: [], Role.VIEWER: []}

    for role, permissions in expected.items():
        assert client_as(role).get("/auth/me").json()["permissions"] == permissions


def test_the_owner_sets_the_permissions_of_an_admin(
    client_as: ClientFactory, session: Session
) -> None:
    owner = client_as(Role.OWNER)
    ann = _add(session, "ann", "admin")

    only_create = _set(owner, ann, ["create_users"])
    nothing = _set(owner, ann, [])
    everything = _set(
        owner, ann, ["deactivate_users", "create_users", "change_roles"]
    )

    assert only_create.status_code == 200
    assert only_create.json()["permissions"] == ["create_users"]
    assert nothing.json()["permissions"] == []
    assert everything.json()["permissions"] == ALL
    assert _permissions_of(owner, ann) == ALL


def test_duplicate_permissions_are_ignored(
    client_as: ClientFactory, session: Session
) -> None:
    owner = client_as(Role.OWNER)
    ann = _add(session, "ann", "admin")

    response = _set(owner, ann, ["create_users", "create_users"])

    assert response.json()["permissions"] == ["create_users"]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.MEMBER, Role.VIEWER])
def test_only_the_owner_may_set_permissions(
    client_as: ClientFactory, session: Session, role: Role
) -> None:
    ann = _add(session, "ann", "admin")

    assert _set(client_as(role), ann, ["create_users"]).status_code == 403

    assert _permissions_of(client_as(Role.OWNER), ann) == ALL


@pytest.mark.parametrize("role", ["owner", "member", "viewer"])
def test_permissions_only_exist_for_admins(
    client_as: ClientFactory, session: Session, role: str
) -> None:
    owner = client_as(Role.OWNER)
    target = _my_id(owner) if role == "owner" else _add(session, "target", role)

    assert _set(owner, target, ["create_users"]).status_code == 422


def test_unknown_or_invalid_ids(client_as: ClientFactory) -> None:
    owner = client_as(Role.OWNER)

    assert _set(owner, 999, ["create_users"]).status_code == 404
    assert _set(owner, 0, ["create_users"]).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"permissions": ["fly"]},
        {"permissions": "create_users"},
        {"permissions": [None]},
        {},
        {"permissions": ["create_users"], "role": "owner"},
    ],
    ids=["unknown", "not-a-list", "null-item", "missing", "extra-key"],
)
def test_invalid_bodies_are_rejected_and_change_nothing(
    client_as: ClientFactory, session: Session, body: dict[str, object]
) -> None:
    owner = client_as(Role.OWNER)
    ann = _add(session, "ann", "admin")

    response = owner.put(f"/users/{ann}/permissions", json=body)

    assert response.status_code == 422
    assert _permissions_of(owner, ann) == ALL


@pytest.mark.parametrize("missing", list(Permission), ids=lambda item: item.value)
def test_each_permission_guards_exactly_its_own_action(
    client_as: ClientFactory, session: Session, missing: Permission
) -> None:
    owner, admin = client_as(Role.OWNER), client_as(Role.ADMIN)
    allowed = [item.value for item in Permission if item is not missing]
    assert _set(owner, _my_id(admin), allowed).status_code == 200

    for action in Permission:
        status = _attempt(admin, session, action)
        if action is missing:
            assert status == 403, action
        else:
            assert status in (200, 201), action


def test_the_refusal_names_the_missing_permission(client_as: ClientFactory) -> None:
    owner, admin = client_as(Role.OWNER), client_as(Role.ADMIN)
    _set(owner, _my_id(admin), [])

    response = admin.post("/users", json=_new_user_body("newcomer"))

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing permission: create_users"}


def test_changing_role_and_status_together_needs_both_permissions(
    client_as: ClientFactory, session: Session
) -> None:
    owner, admin = client_as(Role.OWNER), client_as(Role.ADMIN)
    _set(owner, _my_id(admin), ["deactivate_users"])
    victim = _add(session, "victim", "member")

    response = admin.patch(
        f"/users/{victim}", json={"role": "viewer", "is_active": False}
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Missing permission: change_roles"}
    unchanged = owner.get(f"/users/{victim}").json()
    assert (unchanged["role"], unchanged["is_active"]) == ("member", True)


def test_revoking_a_permission_takes_effect_immediately(
    client_as: ClientFactory,
) -> None:
    owner, admin = client_as(Role.OWNER), client_as(Role.ADMIN)
    assert admin.post("/users", json=_new_user_body("first")).status_code == 201

    assert _set(owner, _my_id(admin), ["change_roles"]).status_code == 200

    # Same login, no new token: the database is asked on every request.
    assert admin.post("/users", json=_new_user_body("second")).status_code == 403


def test_the_owner_keeps_every_permission_whatever_is_stored(
    client_as: ClientFactory, session: Session
) -> None:
    owner = client_as(Role.OWNER)
    session.add_all(
        RevokedPermission(user_id=_my_id(owner), permission=name) for name in ALL
    )
    session.commit()

    assert owner.get("/auth/me").json()["permissions"] == ALL
    assert owner.post("/users", json=_new_user_body("someone")).status_code == 201


def test_a_fully_restricted_admin_can_still_read_and_do_inventory_work(
    client_as: ClientFactory,
) -> None:
    owner, admin = client_as(Role.OWNER), client_as(Role.ADMIN)
    assert _set(owner, _my_id(admin), []).status_code == 200

    assert admin.get("/users").status_code == 200
    assert admin.get(f"/users/{_my_id(admin)}").status_code == 200
    assert admin.post("/chemicals", json={"name": "Water"}).status_code == 201


def test_restrictions_are_remembered_when_an_admin_comes_back(
    client_as: ClientFactory, session: Session
) -> None:
    owner = client_as(Role.OWNER)
    ann = _add(session, "ann", "admin")
    _set(owner, ann, ["create_users"])

    demoted = owner.patch(f"/users/{ann}", json={"role": "member"})
    promoted = owner.patch(f"/users/{ann}", json={"role": "admin"})

    assert demoted.json()["permissions"] == []
    assert promoted.json()["permissions"] == ["create_users"]


def test_database_rejects_an_unknown_permission(session: Session) -> None:
    ann = _add(session, "ann", "admin")
    session.add(RevokedPermission(user_id=ann, permission="fly"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_permission_can_be_revoked_only_once(session: Session) -> None:
    ann = _add(session, "ann", "admin")
    session.add(RevokedPermission(user_id=ann, permission="create_users"))
    session.commit()
    session.add(RevokedPermission(user_id=ann, permission="create_users"))

    with pytest.raises(IntegrityError):
        session.commit()
