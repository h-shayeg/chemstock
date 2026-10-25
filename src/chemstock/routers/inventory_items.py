from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.db import get_session
from chemstock.models import InventoryItem
from chemstock.schemas import (
    InventoryItemCreate,
    InventoryItemRead,
    InventoryItemUpdate,
)

router = APIRouter(prefix="/inventory-items", tags=["inventory"])

SessionDep = Annotated[Session, Depends(get_session)]
# Upper bound = largest value of a PostgreSQL "integer" column.
ItemId = Annotated[int, Path(ge=1, le=2_147_483_647)]


def _get_or_404(session: Session, item_id: int) -> InventoryItem:
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Inventory item not found")
    return item


@router.post(
    "", response_model=InventoryItemRead, status_code=status.HTTP_201_CREATED
)
def create_inventory_item(
    payload: InventoryItemCreate, session: SessionDep
) -> InventoryItem:
    item = InventoryItem(**payload.model_dump())
    session.add(item)
    try:
        session.commit()
    except IntegrityError:
        # The foreign key is the source of truth: it also covers a chemical
        # that disappears right after the request was validated.
        session.rollback()
        raise HTTPException(422, "Chemical does not exist") from None
    session.refresh(item)
    return item


@router.get("", response_model=list[InventoryItemRead])
def list_inventory_items(
    session: SessionDep,
    chemical_id: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InventoryItem]:
    statement = select(InventoryItem).order_by(InventoryItem.id)
    if chemical_id is not None:
        statement = statement.where(InventoryItem.chemical_id == chemical_id)
    return list(session.scalars(statement.limit(limit).offset(offset)))


@router.get("/{item_id}", response_model=InventoryItemRead)
def get_inventory_item(item_id: ItemId, session: SessionDep) -> InventoryItem:
    return _get_or_404(session, item_id)


@router.patch("/{item_id}", response_model=InventoryItemRead)
def update_inventory_item(
    item_id: ItemId, payload: InventoryItemUpdate, session: SessionDep
) -> InventoryItem:
    item = _get_or_404(session, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inventory_item(item_id: ItemId, session: SessionDep) -> None:
    item = _get_or_404(session, item_id)
    session.delete(item)
    session.commit()
