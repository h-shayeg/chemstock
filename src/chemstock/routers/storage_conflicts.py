from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from chemstock.db import get_session
from chemstock.models import Chemical, InventoryItem
from chemstock.schemas import ConflictItem, ConflictReason, StorageConflictRead
from chemstock.storage import Bottle, StorageConflict, find_storage_conflicts

router = APIRouter(prefix="/storage-conflicts", tags=["storage"])

SessionDep = Annotated[Session, Depends(get_session)]


def _to_item(bottle: Bottle) -> ConflictItem:
    return ConflictItem(
        inventory_item_id=bottle.item_id,
        chemical_id=bottle.chemical_id,
        chemical_name=bottle.chemical_name,
        hazard_classes=list(bottle.hazard_classes),
    )


def _to_schema(conflict: StorageConflict) -> StorageConflictRead:
    return StorageConflictRead(
        status=conflict.status.value,
        severity=conflict.severity,
        location=conflict.location,
        items=[_to_item(conflict.first), _to_item(conflict.second)],
        reasons=[
            ConflictReason(
                rule=reason.rule, severity=reason.severity, message=reason.message
            )
            for reason in conflict.reasons
        ],
    )


@router.get("", response_model=list[StorageConflictRead])
def list_storage_conflicts(
    session: SessionDep,
    status_filter: Annotated[
        Literal["conflict", "review_required"] | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StorageConflictRead]:
    """Pairs of bottles at the same location that should be stored apart.

    Two bottles share a location when their `location` text is equal after
    collapsing spaces and ignoring case. Bottles without a location, and two
    bottles of the same chemical, are never compared.

    - `conflict`: a storage rule applies. `severity` 1 = reaction risk,
      2 = separation advised. If several rules match, the highest severity is
      reported and every reason is listed.
    - `review_required`: not enough hazard information to call the pair
      compatible (a chemical has no hazard classes yet). It is never "safe".

    Most urgent first. This is an assistive tool, not a replacement for the
    Safety Data Sheet (SDS).
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
    conflicts = find_storage_conflicts(bottles)
    if status_filter is not None:
        conflicts = [c for c in conflicts if c.status.value == status_filter]
    return [_to_schema(conflict) for conflict in conflicts[offset : offset + limit]]
