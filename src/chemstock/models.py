from datetime import datetime

from sqlalchemy import DateTime, String, func
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
