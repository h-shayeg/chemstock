"""Reports that read the database: low stock and storage conflicts.

Shared by the API routers and the web pages, so both always show the same
numbers. The decisions themselves are pure logic in chemstock.stock and
chemstock.storage; this module only loads the rows they need.
"""

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from chemstock.models import Chemical, InventoryItem
from chemstock.stock import Amount, LowStock, StockedChemical, find_low_stock
from chemstock.storage import Bottle, StorageConflict, find_storage_conflicts


def load_low_stock(session: Session) -> list[LowStock]:
    """Every chemical at or below its reorder level, the emptiest first."""
    # One query (a single snapshot of the database): every chemical with a
    # reorder level, once per bottle, or once with no bottle at all.
    rows = session.execute(
        select(
            Chemical.id,
            Chemical.name,
            Chemical.reorder_level,
            Chemical.reorder_unit,
            InventoryItem.quantity,
            InventoryItem.unit,
        )
        .outerjoin(InventoryItem, InventoryItem.chemical_id == Chemical.id)
        .where(Chemical.reorder_level.is_not(None))
    ).all()
    levels: dict[int, tuple[str, Decimal, str]] = {}
    bottles: dict[int, list[Amount]] = defaultdict(list)
    for row in rows:
        levels[row.id] = (row.name, row.reorder_level, row.reorder_unit)
        if row.quantity is not None:
            bottles[row.id].append(Amount(row.quantity, row.unit))
    return find_low_stock(
        StockedChemical(chemical_id, name, level, unit, tuple(bottles[chemical_id]))
        for chemical_id, (name, level, unit) in levels.items()
    )


def load_storage_conflicts(session: Session) -> list[StorageConflict]:
    """Every pair of bottles at the same location that needs attention.

    Most urgent first (see chemstock.storage.find_storage_conflicts).
    """
    rows = session.execute(
        select(InventoryItem, Chemical)
        .join(Chemical, Chemical.id == InventoryItem.chemical_id)
        .where(InventoryItem.location.is_not(None))
    ).all()
    bottles = [
        Bottle(
            item_id=item.id,
            chemical_id=chemical.id,
            chemical_name=chemical.name,
            location=item.location,
            hazard_classes=tuple(chemical.hazard_classes),
        )
        for item, chemical in rows
    ]
    return find_storage_conflicts(bottles)
