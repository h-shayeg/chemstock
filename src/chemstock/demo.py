"""Example data, so the API can be tried out in a minute.

``python -m chemstock.cli seed-demo`` fills an EMPTY database with a small,
realistic lab: a few chemicals with hazard classes, and bottles placed so that
every report has something to show (storage conflicts, a chemical that still
needs review, expiring and expired bottles, low stock).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from chemstock.models import Chemical, ChemicalHazardClass, InventoryItem


class DemoError(Exception):
    """The demo data cannot be added (the database is not empty)."""


@dataclass(frozen=True)
class DemoChemical:
    name: str
    cas_number: str
    formula: str
    hazard_classes: tuple[str, ...]  # empty = not reviewed yet
    reorder: tuple[str, str] | None = None  # (level, unit)


@dataclass(frozen=True)
class DemoBottle:
    cas_number: str  # which chemical
    quantity: str
    unit: str
    location: str
    expires_in_days: int | None  # from today; negative = already expired


FLAMMABLES = "Flammables cabinet"
ACIDS = "Acid cabinet"
SHELF = "Shelf B2"

CHEMICALS = (
    DemoChemical("Acetone", "67-64-1", "C3H6O", ("flammable",), ("2", "L")),
    DemoChemical("Ethanol", "64-17-5", "C2H6O", ("flammable",), ("1", "L")),
    # Toluene is not classified yet: it shows "review_required", and
    # GET /chemicals/{id}/ghs suggests "flammable" for it.
    DemoChemical("Toluene", "108-88-3", "C7H8", ()),
    DemoChemical(
        "Nitric acid 65%",
        "7697-37-2",
        "HNO3",
        ("inorganic_acid", "oxidizing_acid"),
    ),
    DemoChemical("Hydrochloric acid 37%", "7647-01-0", "HCl", ("inorganic_acid",)),
    DemoChemical(
        "Sodium hydroxide", "1310-73-2", "NaOH", ("inorganic_base",), ("500", "g")
    ),
    DemoChemical("Sodium nitrate", "7631-99-4", "NaNO3", ("oxidizer",)),
    DemoChemical("Sodium sulfide", "1313-82-2", "Na2S", ("acid_gas_generator",)),
    DemoChemical(
        "Dichloromethane",
        "75-09-2",
        "CH2Cl2",
        ("halogenated_solvent",),
        ("2", "L"),
    ),
    DemoChemical(
        "Sodium chloride",
        "7647-14-5",
        "NaCl",
        ("no_storage_hazard",),
        ("500", "g"),
    ),
)

BOTTLES = (
    DemoBottle("67-64-1", "2.5", "L", FLAMMABLES, 400),
    DemoBottle("67-64-1", "500", "mL", FLAMMABLES, 20),  # expires soon
    DemoBottle("64-17-5", "400", "mL", FLAMMABLES, None),  # low stock
    DemoBottle("108-88-3", "1", "L", FLAMMABLES, 200),  # needs review
    DemoBottle("7697-37-2", "1", "L", ACIDS, 300),
    DemoBottle("7647-01-0", "2.5", "L", ACIDS, -10),  # already expired
    DemoBottle("1310-73-2", "250", "g", ACIDS, None),  # wrong cabinet, low stock
    DemoBottle("7631-99-4", "500", "g", SHELF, 700),
    DemoBottle("1313-82-2", "100", "g", SHELF, 60),  # next to an oxidizer
    DemoBottle("75-09-2", "1", "L", "Solvent shelf", 45),  # low stock
    DemoBottle("7647-14-5", "1", "kg", SHELF, None),
)


@dataclass(frozen=True)
class DemoSummary:
    chemicals: int
    bottles: int


def seed_demo(session: Session, today: date) -> DemoSummary:
    """Add the demo chemicals and bottles. Refuses if any chemical exists."""
    if session.scalar(select(exists().where(Chemical.id.is_not(None)))):
        raise DemoError(
            "the database already has chemicals; "
            "demo data is only added to an empty database"
        )

    by_cas: dict[str, Chemical] = {}
    for item in CHEMICALS:
        level, unit = item.reorder or (None, None)
        chemical = Chemical(
            name=item.name,
            cas_number=item.cas_number,
            formula=item.formula,
            reorder_level=Decimal(level) if level is not None else None,
            reorder_unit=unit,
        )
        chemical.hazard_links = [
            ChemicalHazardClass(hazard_class=hazard) for hazard in item.hazard_classes
        ]
        session.add(chemical)
        by_cas[item.cas_number] = chemical
    session.flush()  # gives every chemical its id

    for bottle in BOTTLES:
        days = bottle.expires_in_days
        session.add(
            InventoryItem(
                chemical_id=by_cas[bottle.cas_number].id,
                quantity=Decimal(bottle.quantity),
                unit=bottle.unit,
                location=bottle.location,
                expiry_date=today + timedelta(days=days) if days is not None else None,
            )
        )
    session.commit()
    return DemoSummary(chemicals=len(CHEMICALS), bottles=len(BOTTLES))
