"""What an admin may do in user management. Pure logic, no database.

Only admins have permissions that can be restricted. The owner always has all of
them, and members and viewers have none (they cannot manage users at all).
"""

from collections.abc import Iterable
from enum import StrEnum

from chemstock.roles import Role


class Permission(StrEnum):
    CREATE_USERS = "create_users"  # POST /users
    CHANGE_ROLES = "change_roles"  # PATCH /users/{id} with a "role"
    DEACTIVATE_USERS = "deactivate_users"  # PATCH /users/{id} with "is_active"


def effective_permissions(role: Role, revoked: Iterable[str]) -> list[Permission]:
    """The permissions a user has, in the order of the Permission enum.

    `revoked` is what was taken away; it only matters for admins.
    """
    if role is Role.OWNER:
        return list(Permission)
    if role is Role.ADMIN:
        taken = {Permission(name) for name in revoked}
        return [item for item in Permission if item not in taken]
    return []
