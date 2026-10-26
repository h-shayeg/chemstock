from enum import StrEnum


class Role(StrEnum):
    """What a user may do."""

    ADMIN = "admin"  # everything, including managing users
    MEMBER = "member"  # read and change inventory data
    VIEWER = "viewer"  # read only
