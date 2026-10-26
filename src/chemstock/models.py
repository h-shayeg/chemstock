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
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chemstock.compatibility import HazardClass
from chemstock.db import Base
from chemstock.roles import Role

_HAZARD_CLASS_VALUES = ", ".join(f"'{hazard.value}'" for hazard in HazardClass)
_ROLE_VALUES = ", ".join(f"'{role.value}'" for role in Role)


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
    hazard_links: Mapped[list["ChemicalHazardClass"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    @property
    def hazard_classes(self) -> list[str]:
        """Hazard class names, sorted. An empty list means "not reviewed yet"."""
        return sorted(link.hazard_class for link in self.hazard_links)


class ChemicalHazardClass(Base):
    """One hazard class of one chemical (a chemical can have several)."""

    __tablename__ = "chemical_hazard_classes"
    __table_args__ = (
        CheckConstraint(
            f"hazard_class IN ({_HAZARD_CLASS_VALUES})",
            name="hazard_class_allowed",
        ),
    )

    chemical_id: Mapped[int] = mapped_column(
        ForeignKey("chemicals.id", ondelete="CASCADE"), primary_key=True
    )
    hazard_class: Mapped[str] = mapped_column(String(30), primary_key=True)


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


class User(Base):
    """A person who can log in. Their role decides what they may do."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({_ROLE_VALUES})", name="role_allowed"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
