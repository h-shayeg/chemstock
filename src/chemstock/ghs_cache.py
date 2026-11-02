"""Ask PubChem about a CAS number at most once per cache period.

The answer (also "not found") is stored in the ghs_cache table. If PubChem
cannot be reached and an older answer exists, that answer is returned and
marked as stale instead of failing.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from chemstock.ghs import GhsData, GhsStatus, HazardStatement, Pictogram
from chemstock.models import GhsCacheEntry
from chemstock.pubchem import PubChemClient, PubChemUnavailable


@dataclass(frozen=True)
class GhsResult:
    status: GhsStatus
    cid: int | None
    data: GhsData | None
    fetched_at: datetime
    stale: bool  # PubChem was not reachable; this is an older answer


def _to_json(data: GhsData | None) -> dict[str, Any] | None:
    return None if data is None else asdict(data)


def _from_json(raw: dict[str, Any] | None) -> GhsData | None:
    if raw is None:
        return None
    return GhsData(
        reported=raw["reported"],
        hazard_statements=tuple(HazardStatement(**s) for s in raw["hazard_statements"]),
        pictograms=tuple(Pictogram(**p) for p in raw["pictograms"]),
        signal_word=raw["signal_word"],
        notes=tuple(raw["notes"]),
        sources=tuple(raw["sources"]),
    )


def _from_entry(entry: GhsCacheEntry, stale: bool) -> GhsResult:
    return GhsResult(
        status=GhsStatus(entry.status),
        cid=entry.pubchem_cid,
        data=_from_json(entry.data),
        # Always UTC, whatever time zone the database session uses.
        fetched_at=entry.fetched_at.astimezone(UTC),
        stale=stale,
    )


def get_ghs(
    session: Session,
    client: PubChemClient,
    cas_number: str,
    now: datetime,
    max_age: timedelta,
) -> GhsResult:
    """GHS data for a CAS number, from the cache or freshly from PubChem.

    Raises PubChemUnavailable only if PubChem cannot be reached AND nothing
    about this CAS number was ever stored.
    """
    entry = session.get(GhsCacheEntry, cas_number)
    if entry is not None and now - entry.fetched_at < max_age:
        return _from_entry(entry, stale=False)
    try:
        lookup = client.lookup_ghs(cas_number)
    except PubChemUnavailable:
        if entry is not None:
            return _from_entry(entry, stale=True)
        raise

    values = {
        "status": lookup.status.value,
        "pubchem_cid": lookup.cid,
        "data": _to_json(lookup.data),
        "fetched_at": now,
    }
    # An upsert: two requests for the same CAS number at once must not fail.
    session.execute(
        insert(GhsCacheEntry)
        .values(cas_number=cas_number, **values)
        .on_conflict_do_update(index_elements=["cas_number"], set_=values)
    )
    session.commit()
    return GhsResult(lookup.status, lookup.cid, lookup.data, now, stale=False)
