import pytest

from chemstock.permissions import Permission, effective_permissions
from chemstock.roles import Role

CREATE = Permission.CREATE_USERS
CHANGE = Permission.CHANGE_ROLES
DEACTIVATE = Permission.DEACTIVATE_USERS
ALL = [CREATE, CHANGE, DEACTIVATE]


def test_the_enum_has_exactly_the_three_agreed_permissions() -> None:
    assert list(Permission) == ALL
    assert [item.value for item in Permission] == [
        "create_users",
        "change_roles",
        "deactivate_users",
    ]


def test_the_owner_always_has_every_permission() -> None:
    assert effective_permissions(Role.OWNER, []) == ALL
    # Whatever happens to be stored for an owner is ignored.
    assert effective_permissions(Role.OWNER, ["create_users"]) == ALL


def test_an_admin_has_everything_except_what_was_taken_away() -> None:
    assert effective_permissions(Role.ADMIN, []) == ALL
    assert effective_permissions(Role.ADMIN, ["change_roles"]) == [CREATE, DEACTIVATE]
    assert effective_permissions(Role.ADMIN, [item.value for item in ALL]) == []


@pytest.mark.parametrize("role", [Role.MEMBER, Role.VIEWER])
def test_members_and_viewers_have_no_user_management_permissions(role: Role) -> None:
    assert effective_permissions(role, []) == []
    assert effective_permissions(role, ["create_users"]) == []


def test_duplicates_are_ignored_and_the_order_is_stable() -> None:
    result = effective_permissions(Role.ADMIN, ["create_users", "create_users"])

    assert result == [CHANGE, DEACTIVATE]


def test_an_unknown_permission_name_is_an_error() -> None:
    with pytest.raises(ValueError):
        effective_permissions(Role.ADMIN, ["fly"])
