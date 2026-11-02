"""Find chemicals that are running low.

Pure logic (no database): the caller loads the chemicals and their bottles and
passes them in. A chemical takes part only if someone gave it a reorder level.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

# Every unit as (kind, size in the base unit of its kind). Mass and volume
# cannot be added together without the density, which the catalog does not have.
UNITS: dict[str, tuple[str, Decimal]] = {
    "mg": ("mass", Decimal("0.001")),
    "g": ("mass", Decimal("1")),
    "kg": ("mass", Decimal("1000")),
    "mL": ("volume", Decimal("1")),
    "L": ("volume", Decimal("1000")),
}

_THREE_PLACES = Decimal("0.001")


def convert(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal | None:
    """Express a quantity in another unit, or None if the kinds differ.

    Exact: units differ by powers of ten, and Decimal keeps every digit.
    """
    from_kind, from_size = UNITS[from_unit]
    to_kind, to_size = UNITS[to_unit]
    if from_kind != to_kind:
        return None
    return quantity * from_size / to_size


def tidy(value: Decimal) -> Decimal:
    """At least three decimal places, like the rest of the API, but exact.

    1.5 becomes 1.500 and 1000 stays 1000.000, while 0.0005 keeps all its digits.
    """
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    if isinstance(exponent, int) and exponent >= -3:
        return normalized.quantize(_THREE_PLACES)
    return normalized


@dataclass(frozen=True)
class Amount:
    """How much one bottle holds."""

    quantity: Decimal
    unit: str


@dataclass(frozen=True)
class StockedChemical:
    """A chemical with a reorder level, and every bottle of it."""

    chemical_id: int
    chemical_name: str
    reorder_level: Decimal
    reorder_unit: str
    bottles: tuple[Amount, ...]


@dataclass(frozen=True)
class LowStock:
    """A chemical whose total amount is at or below its reorder level."""

    chemical_id: int
    chemical_name: str
    reorder_level: Decimal
    unit: str  # the unit of the reorder level; the total uses it too
    total_quantity: Decimal
    item_count: int  # bottles that were added up
    uncounted_item_count: int  # bottles measured in a unit of the other kind


def check_stock(chemical: StockedChemical) -> LowStock | None:
    """Return a LowStock report if the chemical needs reordering, else None.

    Bottles measured in a unit of the other kind (grams vs litres) cannot be
    added up. They are left out of the total and counted separately, so a
    person can see that the total may be too small. Such a bottle can therefore
    cause a false alarm, but never hide a real one.
    """
    total = Decimal(0)
    counted = uncounted = 0
    for bottle in chemical.bottles:
        amount = convert(bottle.quantity, bottle.unit, chemical.reorder_unit)
        if amount is None:
            uncounted += 1
        else:
            total += amount
            counted += 1
    if total > chemical.reorder_level:
        return None
    return LowStock(
        chemical_id=chemical.chemical_id,
        chemical_name=chemical.chemical_name,
        reorder_level=chemical.reorder_level,
        unit=chemical.reorder_unit,
        total_quantity=tidy(total),
        item_count=counted,
        uncounted_item_count=uncounted,
    )


def _sort_key(report: LowStock) -> tuple[Decimal, str, int]:
    # The share of the reorder level that is left: 0 = ran out, 1 = just at it.
    if report.reorder_level > 0:
        share = report.total_quantity / report.reorder_level
    else:
        share = Decimal(0)  # a level of 0 is only reached when nothing is left
    return (share, report.chemical_name.casefold(), report.chemical_id)


def find_low_stock(chemicals: Iterable[StockedChemical]) -> list[LowStock]:
    """Every chemical at or below its reorder level, the emptiest first."""
    reports = [check_stock(chemical) for chemical in chemicals]
    return sorted((r for r in reports if r is not None), key=_sort_key)
