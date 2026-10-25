from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.db import get_session
from chemstock.models import Chemical
from chemstock.schemas import ChemicalCreate, ChemicalRead, ChemicalUpdate

router = APIRouter(prefix="/chemicals", tags=["chemicals"])

SessionDep = Annotated[Session, Depends(get_session)]
# Upper bound = largest value of a PostgreSQL "integer" column.
ChemicalId = Annotated[int, Path(ge=1, le=2_147_483_647)]

CAS_CONFLICT = "A chemical with this CAS number already exists"
IN_USE_CONFLICT = "Chemical still has inventory items; remove them first"


def _get_or_404(session: Session, chemical_id: int) -> Chemical:
    chemical = session.get(Chemical, chemical_id)
    if chemical is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chemical not found")
    return chemical


def _commit(session: Session, conflict_detail: str) -> None:
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=conflict_detail
        ) from None


@router.post("", response_model=ChemicalRead, status_code=status.HTTP_201_CREATED)
def create_chemical(payload: ChemicalCreate, session: SessionDep) -> Chemical:
    chemical = Chemical(**payload.model_dump())
    session.add(chemical)
    _commit(session, CAS_CONFLICT)
    session.refresh(chemical)
    return chemical


@router.get("", response_model=list[ChemicalRead])
def list_chemicals(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Chemical]:
    statement = select(Chemical).order_by(Chemical.id).limit(limit).offset(offset)
    return list(session.scalars(statement))


@router.get("/{chemical_id}", response_model=ChemicalRead)
def get_chemical(chemical_id: ChemicalId, session: SessionDep) -> Chemical:
    return _get_or_404(session, chemical_id)


@router.patch("/{chemical_id}", response_model=ChemicalRead)
def update_chemical(
    chemical_id: ChemicalId, payload: ChemicalUpdate, session: SessionDep
) -> Chemical:
    chemical = _get_or_404(session, chemical_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(chemical, field, value)
    _commit(session, CAS_CONFLICT)
    session.refresh(chemical)
    return chemical


@router.delete("/{chemical_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chemical(chemical_id: ChemicalId, session: SessionDep) -> None:
    chemical = _get_or_404(session, chemical_id)
    session.delete(chemical)
    _commit(session, IN_USE_CONFLICT)
