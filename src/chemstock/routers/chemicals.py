from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.db import get_session
from chemstock.models import Chemical
from chemstock.schemas import ChemicalCreate, ChemicalRead

router = APIRouter(prefix="/chemicals", tags=["chemicals"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=ChemicalRead, status_code=status.HTTP_201_CREATED)
def create_chemical(payload: ChemicalCreate, session: SessionDep) -> Chemical:
    chemical = Chemical(**payload.model_dump())
    session.add(chemical)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A chemical with this CAS number already exists",
        ) from None
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
