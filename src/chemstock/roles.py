from enum import StrEnum


class Role(StrEnum):
    """What a user may do. A higher rank may do everything a lower rank may do."""

    OWNER = "owner"  # the one main admin; the only one who manages admins
    ADMIN = "admin"  # manages members and viewers
    MEMBER = "member"  # reads and changes inventory data
    VIEWER = "viewer"  # read only


ROLE_RANK = {Role.OWNER: 4, Role.ADMIN: 3, Role.MEMBER: 2, Role.VIEWER: 1}
