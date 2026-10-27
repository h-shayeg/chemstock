import re
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from chemstock.dependencies import ROLE_RANK
from chemstock.main import app
from chemstock.models import User
from chemstock.roles import Role

VIEWER, MEMBER = Role.VIEWER, Role.MEMBER

# The only endpoints that work without logging in.
PUBLIC_OPERATIONS = {("GET", "/health"), ("POST", "/auth/login")}

# Tested in test_user_management_api.py: whether such a call is allowed also
# depends on WHICH user it targets, so the simple role table cannot express it.
USER_MANAGEMENT = {
    ("POST", "/users"),
    ("GET", "/users"),
    ("GET", "/users/{user_id}"),
    ("PATCH", "/users/{user_id}"),
}

# (method, path, JSON body, lowest role that may call it).
# Reading needs "viewer"; changing data needs "member". A test below fails if
# this table and the real API ever disagree.
ENDPOINTS: list[tuple[str, str, dict[str, object] | None, Role]] = [
    ("GET", "/chemicals", None, VIEWER),
    ("POST", "/chemicals", {"name": "Water"}, MEMBER),
    ("GET", "/chemicals/{chemical_id}", None, VIEWER),
    ("PATCH", "/chemicals/{chemical_id}", {"name": "Aqua"}, MEMBER),
    ("DELETE", "/chemicals/{chemical_id}", None, MEMBER),
    (
        "PUT",
        "/chemicals/{chemical_id}/hazard-classes",
        {"hazard_classes": ["flammable"]},
        MEMBER,
    ),
    ("GET", "/hazard-classes", None, VIEWER),
    ("GET", "/inventory-items", None, VIEWER),
    (
        "POST",
        "/inventory-items",
        {"chemical_id": 1, "quantity": "1", "unit": "L"},
        MEMBER,
    ),
    ("GET", "/inventory-items/expiring", None, VIEWER),
    ("GET", "/inventory-items/{item_id}", None, VIEWER),
    ("PATCH", "/inventory-items/{item_id}", {"quantity": "2"}, MEMBER),
    ("DELETE", "/inventory-items/{item_id}", None, MEMBER),
    ("GET", "/storage-conflicts", None, VIEWER),
    ("GET", "/auth/me", None, VIEWER),
]


def _api_operations() -> set[tuple[str, str]]:
    paths = app.openapi()["paths"]
    return {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
    }


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


PROTECTED = sorted(_api_operations() - PUBLIC_OPERATIONS)


def test_endpoint_table_matches_the_real_api() -> None:
    documented = {(method, path) for method, path, _body, _role in ENDPOINTS}

    assert documented == set(PROTECTED) - USER_MANAGEMENT


@pytest.mark.parametrize(
    ("method", "path"), PROTECTED, ids=[f"{m} {p}" for m, p in PROTECTED]
)
def test_anonymous_callers_are_rejected(
    anonymous_client: TestClient, method: str, path: str
) -> None:
    response = anonymous_client.request(method, _concrete(path))

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "body", "minimum", "role"),
    [
        pytest.param(
            method, path, body, minimum, role, id=f"{role.value}: {method} {path}"
        )
        for method, path, body, minimum in ENDPOINTS
        for role in Role
    ],
)
def test_role_permissions(
    client_as: Callable[[Role], TestClient],
    method: str,
    path: str,
    body: dict[str, object] | None,
    minimum: Role,
    role: Role,
) -> None:
    response = client_as(role).request(method, _concrete(path), json=body)

    if ROLE_RANK[role] >= ROLE_RANK[minimum]:
        # The call is allowed; it may still be a 404 or similar, but never a refusal.
        assert response.status_code not in (401, 403)
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": "Not enough permissions"}


def test_public_endpoints_need_no_token(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/health").status_code == 200
    assert anonymous_client.get("/docs").status_code == 200
    # Login is reachable without a token (an empty form is a validation error).
    assert anonymous_client.post("/auth/login").status_code == 422


def test_viewer_cannot_change_anything(client_as: Callable[[Role], TestClient]) -> None:
    viewer = client_as(Role.VIEWER)

    assert viewer.post("/chemicals", json={"name": "Water"}).status_code == 403
    assert client_as(Role.ADMIN).get("/chemicals").json() == []


def test_deactivated_user_is_locked_out_of_the_api(
    client_as: Callable[[Role], TestClient], session: Session
) -> None:
    member = client_as(Role.MEMBER)
    assert member.get("/chemicals").status_code == 200

    user = session.scalars(select(User).where(User.username == "test-member")).one()
    user.is_active = False
    session.commit()

    assert member.get("/chemicals").status_code == 401


def test_a_demoted_member_loses_write_access_immediately(
    client_as: Callable[[Role], TestClient], session: Session
) -> None:
    member = client_as(Role.MEMBER)
    assert member.post("/chemicals", json={"name": "Water"}).status_code == 201

    user = session.scalars(select(User).where(User.username == "test-member")).one()
    user.role = "viewer"
    session.commit()

    assert member.post("/chemicals", json={"name": "Ethanol"}).status_code == 403
    assert member.get("/chemicals").status_code == 200
