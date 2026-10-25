from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from chemstock.db import Base


class Chemical(Base):
    """A chemical substance in the catalog (not a physical bottle)."""

    __tablename__ = "chemicals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    cas_number: Mapped[str | None] = mapped_column(String(12), unique=True)
    formula: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class InventoryItem(Base):
    """A physical container (bottle) of a chemical in the lab."""

    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("unit IN ('mg', 'g', 'kg', 'mL', 'L')", name="unit_allowed"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    chemical_id: Mapped[int] = mapped_column(
        ForeignKey("chemicals.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(10))
    location: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
