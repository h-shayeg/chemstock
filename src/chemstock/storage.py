"""Find bottles that are stored together although they should be stored apart.

Pure logic (no database): the caller loads the bottles and passes them in.
Same caveat as ``chemstock.compatibility``: this is an assistive tool, not a
replacement for the Safety Data Sheet (SDS).
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from chemstock.compatibility import PairStatus, Reason, assess_pair


@dataclass(frozen=True)
class Bottle:
    item_id: int
    chemical_id: int
    chemical_name: str
    location: str | None
    hazard_classes: tuple[str, ...]


@dataclass(frozen=True)
class StorageConflict:
    status: PairStatus  # CONFLICT or REVIEW_REQUIRED, never NO_CONFLICT
    severity: int | None  # 1 or 2 for a conflict, None for "review required"
    location: str
    first: Bottle  # the bottle with the smaller id
    second: Bottle
    reasons: tuple[Reason, ...]


def normalize_location(location: str | None) -> str:
    """Canonical form used to decide whether two bottles share a location.

    Spaces are collapsed and case is ignored, so "Shelf B2" and " shelf  b2 "
    are the same place. An empty result means "no location".
    """
    return " ".join((location or "").split()).casefold()


def _sort_key(conflict: StorageConflict) -> tuple[int, str, int, int]:
    # Severity 1 first, then severity 2, then "review required".
    rank = conflict.severity if conflict.severity is not None else 3
    return (
        rank,
        normalize_location(conflict.location),
        conflict.first.item_id,
        conflict.second.item_id,
    )


def find_storage_conflicts(bottles: Iterable[Bottle]) -> list[StorageConflict]:
    """Return every pair of bottles at the same location that needs attention.

    Rules of the game:
    - bottles without a location are ignored;
    - two bottles of the same chemical are never compared with each other;
    - pairs the rules consider compatible are not reported;
    - pairs with missing hazard information are reported as "review required".
    """
    by_location: dict[str, list[Bottle]] = defaultdict(list)
    for bottle in sorted(bottles, key=lambda item: item.item_id):
        key = normalize_location(bottle.location)
        if key:
            by_location[key].append(bottle)

    found: list[StorageConflict] = []
    for group in by_location.values():
        for first, second in combinations(group, 2):
            if first.chemical_id == second.chemical_id:
                continue
            result = assess_pair(first.hazard_classes, second.hazard_classes)
            if result.status is PairStatus.NO_CONFLICT:
                continue
            found.append(
                StorageConflict(
                    status=result.status,
                    severity=result.severity,
                    location=" ".join((first.location or "").split()),
                    first=first,
                    second=second,
                    reasons=result.reasons,
                )
            )
    return sorted(found, key=_sort_key)
