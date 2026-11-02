from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.clock import get_now
from chemstock.config import get_settings
from chemstock.db import get_session
from chemstock.ghs import suggest_hazard_classes
from chemstock.ghs_cache import get_ghs
from chemstock.models import Chemical, ChemicalHazardClass, InventoryItem
from chemstock.pubchem import PubChemClient, PubChemUnavailable, get_pubchem_client
from chemstock.schemas import (
    ChemicalCreate,
    ChemicalRead,
    ChemicalUpdate,
    GhsRead,
    HazardClassesUpdate,
    HazardStatementRead,
    LowStockRead,
    PictogramRead,
)
from chemstock.stock import Amount, StockedChemical, find_low_stock

router = APIRouter(prefix="/chemicals", tags=["chemicals"])

SessionDep = Annotated[Session, Depends(get_session)]
PubChemDep = Annotated[PubChemClient, Depends(get_pubchem_client)]
NowDep = Annotated[datetime, Depends(get_now)]
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


# This route must be declared BEFORE "/{chemical_id}", otherwise FastAPI would
# treat the word "low-stock" as a chemical id.
@router.get("/low-stock", response_model=list[LowStockRead])
def list_low_stock(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LowStockRead]:
    """Chemicals whose bottles add up to their reorder level or less.

    Only chemicals with a `reorder_level` take part. All bottles of a chemical
    are added up in the unit of its reorder level (`total_quantity`), so 500 g
    and 0.5 kg count the same. A chemical with no bottles left has a total of 0.

    Mass and volume cannot be added together without the density. Bottles in a
    unit of the other kind are left out of the total and counted in
    `uncounted_item_count`, so check those by hand.

    The emptiest chemicals (smallest share of their reorder level) come first.
    """
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
    reports = find_low_stock(
        StockedChemical(chemical_id, name, level, unit, tuple(bottles[chemical_id]))
        for chemical_id, (name, level, unit) in levels.items()
    )
    return [LowStockRead(**vars(report)) for report in reports[offset : offset + limit]]


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


@router.put("/{chemical_id}/hazard-classes", response_model=ChemicalRead)
def set_hazard_classes(
    chemical_id: ChemicalId, payload: HazardClassesUpdate, session: SessionDep
) -> Chemical:
    """Replace the hazard classes of a chemical with exactly the given set."""
    chemical = _get_or_404(session, chemical_id)
    wanted = {hazard.value for hazard in payload.hazard_classes}
    for link in list(chemical.hazard_links):
        if link.hazard_class not in wanted:
            chemical.hazard_links.remove(link)
    present = {link.hazard_class for link in chemical.hazard_links}
    for value in sorted(wanted - present):
        chemical.hazard_links.append(ChemicalHazardClass(hazard_class=value))
    _commit(session, "Hazard classes were changed at the same time; try again")
    session.refresh(chemical)
    return chemical


@router.get("/{chemical_id}/ghs", response_model=GhsRead)
def get_chemical_ghs(
    chemical_id: ChemicalId, session: SessionDep, pubchem: PubChemDep, now: NowDep
) -> GhsRead:
    """GHS hazard data of a chemical from PubChem, found by its CAS number.

    PubChem collects classifications from several sources; this shows the union
    of what they report. Answers are cached (`PUBCHEM_CACHE_DAYS`, default 30),
    and if PubChem cannot be reached an older answer is shown with `stale: true`.

    `suggested_hazard_classes` is only a suggestion and is never applied: a
    person decides, with `PUT /chemicals/{chemical_id}/hazard-classes`. Acids,
    bases, active metals and halogenated solvents cannot be recognized from GHS
    codes, so they are never suggested. Always check the Safety Data Sheet.

    - `409`: the chemical has no CAS number.
    - `503`: PubChem is not reachable and nothing was stored yet.
    """
    chemical = _get_or_404(session, chemical_id)
    if chemical.cas_number is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Chemical has no CAS number; PubChem is searched by CAS number",
        )
    max_age = timedelta(days=get_settings().pubchem_cache_days)
    try:
        result = get_ghs(session, pubchem, chemical.cas_number, now, max_age)
    except PubChemUnavailable:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PubChem is not reachable right now; try again later",
            headers={"Retry-After": "60"},
        ) from None
    data = result.data
    return GhsRead(
        chemical_id=chemical.id,
        cas_number=chemical.cas_number,
        status=result.status.value,
        pubchem_cid=result.cid,
        pubchem_url=(
            f"https://pubchem.ncbi.nlm.nih.gov/compound/{result.cid}"
            if result.cid is not None
            else None
        ),
        signal_word=data.signal_word if data else None,
        pictograms=[
            PictogramRead(code=p.code, name=p.name)
            for p in (data.pictograms if data else ())
        ],
        hazard_statements=[
            HazardStatementRead(code=s.code, statement=s.statement)
            for s in (data.hazard_statements if data else ())
        ],
        suggested_hazard_classes=suggest_hazard_classes(data.codes) if data else [],
        pubchem_notes=list(data.notes) if data else [],
        sources=list(data.sources) if data else [],
        fetched_at=result.fetched_at,
        stale=result.stale,
    )
