"""add reorder level to chemicals

Revision ID: 5f2a8c1e9d34
Revises: e7b3c91a4d52
Create Date: 2026-11-02 12:00:00

Written by hand: Alembic does not detect CHECK constraints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f2a8c1e9d34"
down_revision: str | Sequence[str] | None = "e7b3c91a4d52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chemicals",
        sa.Column("reorder_level", sa.Numeric(precision=12, scale=3), nullable=True),
    )
    op.add_column(
        "chemicals", sa.Column("reorder_unit", sa.String(length=10), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_chemicals_reorder_level_with_unit"),
        "chemicals",
        "(reorder_level IS NULL) = (reorder_unit IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_chemicals_reorder_level_non_negative"),
        "chemicals",
        "reorder_level >= 0",
    )
    op.create_check_constraint(
        op.f("ck_chemicals_reorder_unit_allowed"),
        "chemicals",
        "reorder_unit IN ('mg', 'g', 'kg', 'mL', 'L')",
    )


def downgrade() -> None:
    # Dropping the columns also drops their CHECK constraints.
    op.drop_column("chemicals", "reorder_unit")
    op.drop_column("chemicals", "reorder_level")
