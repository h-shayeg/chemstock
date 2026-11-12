"""The numbers and short lists shown on the home page (dashboard)."""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chemstock.compatibility import PairStatus
from chemstock.models import Chemical, InventoryItem
from chemstock.reports import load_low_stock, load_storage_conflicts
from chemstock.storage import StorageConflict

# "Expiring soon" means within this many days from today.
EXPIRY_WINDOW_DAYS = 30
# How many rows each short list on the dashboard shows.
LIST_LENGTH = 8


@dataclass(frozen=True)
class ExpiringBottle:
    item_id: int
    chemical_name: str
    location: str | None
    expiry_date: date
    days_left: int  # negative once the bottle has expired


@dataclass(frozen=True)
class DashboardSummary:
    chemical_count: int
    item_count: int
    expired_count: int
    expiring_soon_count: int  # from today up to EXPIRY_WINDOW_DAYS ahead
    low_stock_count: int
    conflict_count: int
    review_count: int
    soonest_expiring: list[ExpiringBottle]  # expired ones included, oldest first
    top_conflicts: list[StorageConflict]  # most urgent first


def _count(session: Session, statement) -> int:
    return session.scalar(statement) or 0


def load_dashboard(session: Session, today: date) -> DashboardSummary:
    cutoff = today + timedelta(days=EXPIRY_WINDOW_DAYS)
    count_items = select(func.count()).select_from(InventoryItem)

    expiring_rows = session.execute(
        select(InventoryItem, Chemical.name)
        .join(Chemical, Chemical.id == InventoryItem.chemical_id)
        .where(
            InventoryItem.expiry_date.is_not(None),
            InventoryItem.expiry_date <= cutoff,
        )
        .order_by(InventoryItem.expiry_date, InventoryItem.id)
        .limit(LIST_LENGTH)
    ).all()

    conflicts = load_storage_conflicts(session)
    return DashboardSummary(
        chemical_count=_count(session, select(func.count()).select_from(Chemical)),
        item_count=_count(session, count_items),
        expired_count=_count(
            session, count_items.where(InventoryItem.expiry_date < today)
        ),
        expiring_soon_count=_count(
            session,
            count_items.where(
                InventoryItem.expiry_date >= today,
                InventoryItem.expiry_date <= cutoff,
            ),
        ),
        low_stock_count=len(load_low_stock(session)),
        conflict_count=sum(c.status is PairStatus.CONFLICT for c in conflicts),
        review_count=sum(c.status is PairStatus.REVIEW_REQUIRED for c in conflicts),
        soonest_expiring=[
            ExpiringBottle(
                item_id=item.id,
                chemical_name=name,
                location=item.location,
                expiry_date=item.expiry_date,
                days_left=(item.expiry_date - today).days,
            )
            for item, name in expiring_rows
        ],
        top_conflicts=conflicts[:LIST_LENGTH],
    )
