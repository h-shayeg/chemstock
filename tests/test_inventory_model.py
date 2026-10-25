from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.models import Chemical, InventoryItem


def _make_chemical(session: Session) -> Chemical:
    chemical = Chemical(name="Acetone", cas_number="67-64-1")
    session.add(chemical)
    session.commit()
    return chemical


def test_inventory_item_round_trip(session: Session) -> None:
    chemical = _make_chemical(session)
    session.add(
        InventoryItem(
            chemical_id=chemical.id,
            quantity=Decimal("2.500"),
            unit="L",
            location="Shelf B2",
            expiry_date=date(2027, 3, 1),
        )
    )
    session.commit()

    item = session.scalars(select(InventoryItem)).one()
    assert item.chemical_id == chemical.id
    assert item.quantity == Decimal("2.500")
    assert item.unit == "L"
    assert item.location == "Shelf B2"
    assert item.expiry_date == date(2027, 3, 1)


@pytest.mark.parametrize(
    ("quantity", "unit"),
    [(Decimal("-1"), "g"), (Decimal("1"), "gallon")],
    ids=["negative-quantity", "unknown-unit"],
)
def test_database_rejects_invalid_quantity_or_unit(
    session: Session, quantity: Decimal, unit: str
) -> None:
    chemical = _make_chemical(session)
    session.add(InventoryItem(chemical_id=chemical.id, quantity=quantity, unit=unit))

    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_item_for_unknown_chemical(session: Session) -> None:
    session.add(InventoryItem(chemical_id=999, quantity=Decimal("1"), unit="g"))

    with pytest.raises(IntegrityError):
        session.commit()
