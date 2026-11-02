"""create ghs_cache table

Revision ID: 9c3e5b7a1f20
Revises: 5f2a8c1e9d34
Create Date: 2026-11-02 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c3e5b7a1f20"
down_revision: str | Sequence[str] | None = "5f2a8c1e9d34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ghs_cache",
        sa.Column("cas_number", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("pubchem_cid", sa.Integer(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('classified', 'not_classified', 'no_data', 'not_found')",
            name=op.f("ck_ghs_cache_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("cas_number", name=op.f("pk_ghs_cache")),
    )


def downgrade() -> None:
    op.drop_table("ghs_cache")
