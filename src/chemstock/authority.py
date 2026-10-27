"""Who may change whose account. Pure logic, no database."""

from chemstock.roles import ROLE_RANK, Role


def may_assign(actor: Role, new_role: Role) -> bool:
    """A user may only hand out roles that rank strictly below their own.

    So an admin can make members and viewers, only the owner can make admins,
    and nobody can make another owner through the API.
    """
    return ROLE_RANK[new_role] < ROLE_RANK[actor]


def may_manage(actor: Role, target: Role) -> bool:
    """A user may only change accounts that rank strictly below their own."""
    return ROLE_RANK[target] < ROLE_RANK[actor]
