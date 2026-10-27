"""add the owner role

Revision ID: c4a1f0d2e7b9
Revises: 132b1f0f85fe
Create Date: 2026-10-27 12:00:00

Written by hand: Alembic does not detect changes of CHECK constraints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a1f0d2e7b9"
down_revision: str | Sequence[str] | None = "132b1f0f85fe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_CHECK = "ck_users_role_allowed"


def upgrade() -> None:
    op.drop_constraint(op.f(ROLE_CHECK), "users", type_="check")
    op.create_check_constraint(
        op.f(ROLE_CHECK), "users", "role IN ('owner', 'admin', 'member', 'viewer')"
    )
    # At most one owner: a unique index that only covers the owner rows.
    op.create_index(
        "uq_users_single_owner",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_single_owner", table_name="users")
    # The old constraint does not know the owner role, so demote the owner first.
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'owner'")
    op.drop_constraint(op.f(ROLE_CHECK), "users", type_="check")
    op.create_check_constraint(
        op.f(ROLE_CHECK), "users", "role IN ('admin', 'member', 'viewer')"
    )
