"""add the no_storage_hazard hazard class

Revision ID: e7b3c91a4d52
Revises: dd9d060a0af3
Create Date: 2026-11-01 12:00:00

Written by hand: Alembic does not detect changes of CHECK constraints.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7b3c91a4d52"
down_revision: str | Sequence[str] | None = "dd9d060a0af3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HAZARD_CHECK = "ck_chemical_hazard_classes_hazard_class_allowed"
OLD_CLASSES = (
    "flammable",
    "oxidizer",
    "oxidizing_acid",
    "inorganic_acid",
    "organic_acid",
    "inorganic_base",
    "organic_base",
    "active_metal",
    "acid_gas_generator",
    "water_reactive",
    "halogenated_solvent",
    "isolate",
    "unclassified",
)
NEW_CLASS = "no_storage_hazard"


def _allowed(names: tuple[str, ...]) -> str:
    return "hazard_class IN (" + ", ".join(f"'{name}'" for name in names) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(HAZARD_CHECK), "chemical_hazard_classes", type_="check")
    op.create_check_constraint(
        op.f(HAZARD_CHECK),
        "chemical_hazard_classes",
        _allowed(OLD_CLASSES + (NEW_CLASS,)),
    )


def downgrade() -> None:
    # The old constraint does not know the new class. A chemical that a person
    # marked "no storage hazard" goes back to "not reviewed yet" (no row at all).
    op.execute(
        f"DELETE FROM chemical_hazard_classes WHERE hazard_class = '{NEW_CLASS}'"
    )
    op.drop_constraint(op.f(HAZARD_CHECK), "chemical_hazard_classes", type_="check")
    op.create_check_constraint(
        op.f(HAZARD_CHECK), "chemical_hazard_classes", _allowed(OLD_CLASSES)
    )
