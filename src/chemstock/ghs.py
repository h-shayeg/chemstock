"""Read GHS hazard data from a PubChem record and suggest hazard classes.

Pure logic (no network, no database). ``chemstock.pubchem`` downloads the
"GHS Classification" section of a compound from PubChem (PUG View); this module
turns it into hazard statements, pictograms and a signal word.

PubChem collects the classification from several sources (the EU regulation,
the ECHA C&L inventory, national agencies). They do not always agree, so this
module keeps the union of everything that is reported: for storage, missing a
hazard is worse than seeing one too many.

Suggestions are only a starting point for a person. Acids, bases, active metals
and halogenated solvents cannot be recognized from GHS codes, so they are never
suggested, and neither is ``no_storage_hazard``.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from chemstock.compatibility import HazardClass

# "H225: Highly flammable ... [Danger Flammable liquids]" or
# "H225 (> 99.9%): ...". Combined codes look like "H300+H310+H330".
_STATEMENT = re.compile(
    r"^(?P<codes>(?:EUH|H)\d{3}[A-Za-z]{0,2}(?:\s*\+\s*(?:EUH|H)\d{3}[A-Za-z]{0,2})*)"
    r"(?:\s*\([^)]*\))?\s*:\s*(?P<text>.*?)\s*(?:\[[^\]]*\])?\s*$"
)
_CODE = re.compile(r"(?:EUH|H)\d{3}[A-Za-z]{0,2}")
_PICTOGRAM = re.compile(r"\b(GHS0\d)\b")

# Which GHS hazard statements point to which storage hazard class.
_SUGGESTIONS: dict[HazardClass, frozenset[str]] = {
    # Flammable gases, aerosols, liquids (incl. combustible) and solids.
    HazardClass.FLAMMABLE: frozenset(
        {"H220", "H221", "H222", "H223", "H224", "H225", "H226", "H227", "H228"}
    ),
    # Oxidizing gases, liquids and solids.
    HazardClass.OXIDIZER: frozenset({"H270", "H271", "H272"}),
    # Releases flammable or toxic gas with water, or reacts violently with it.
    HazardClass.WATER_REACTIVE: frozenset({"H260", "H261", "EUH014", "EUH029"}),
    # Releases toxic or very toxic gas with acids.
    HazardClass.ACID_GAS_GENERATOR: frozenset({"EUH031", "EUH032"}),
    # Explosives, self-reactive substances and organic peroxides that may
    # explode when heated, and pyrophoric substances.
    HazardClass.ISOLATE: frozenset(
        {f"H{number}" for number in range(200, 209)} | {"H240", "H241", "H250"}
    ),
}

NOT_SUGGESTED_NOTE = (
    "Acids, bases, active metals and halogenated solvents cannot be recognized "
    "from GHS codes. Check the Safety Data Sheet and add those classes yourself."
)


class GhsStatus(StrEnum):
    CLASSIFIED = "classified"  # PubChem lists GHS hazard statements
    NOT_CLASSIFIED = "not_classified"  # it has a GHS section, but no hazards
    NO_DATA = "no_data"  # the compound exists, but has no GHS section
    NOT_FOUND = "not_found"  # PubChem does not know this CAS number


@dataclass(frozen=True)
class HazardStatement:
    code: str  # one code ("H225") or a combination ("H300+H310")
    statement: str


@dataclass(frozen=True)
class Pictogram:
    code: str  # "GHS02"
    name: str  # "Flammable"


@dataclass(frozen=True)
class GhsData:
    reported: bool  # PubChem has a GHS classification section for it
    hazard_statements: tuple[HazardStatement, ...]
    pictograms: tuple[Pictogram, ...]
    signal_word: str | None  # "Danger", "Warning" or None
    notes: tuple[str, ...]  # remarks from PubChem, e.g. how many reports agree
    sources: tuple[str, ...]  # who classified it (names from PubChem)

    @property
    def codes(self) -> frozenset[str]:
        """Every single code, with combinations split up."""
        return frozenset(
            code for item in self.hazard_statements for code in _CODE.findall(item.code)
        )


def _ghs_entries(node: Any, inside: bool = False) -> Iterator[dict[str, Any]]:
    """Every "Information" entry below a "GHS Classification" heading."""
    if isinstance(node, dict):
        inside = inside or node.get("TOCHeading") == "GHS Classification"
        if inside:
            for info in node.get("Information", []):
                if isinstance(info, dict):
                    yield info
        for key, value in node.items():
            if key != "Information":
                yield from _ghs_entries(value, inside)
    elif isinstance(node, list):
        for item in node:
            yield from _ghs_entries(item, inside)


def _strings(info: dict[str, Any]) -> Iterator[dict[str, Any]]:
    value = info.get("Value")
    if isinstance(value, dict):
        for item in value.get("StringWithMarkup", []):
            if isinstance(item, dict):
                yield item


def parse_ghs(record: dict[str, Any]) -> GhsData:
    """Read the PubChem PUG View answer for the heading "GHS Classification"."""
    statements: dict[str, HazardStatement] = {}
    pictograms: dict[str, Pictogram] = {}
    signals: set[str] = set()
    notes: list[str] = []
    references: set[object] = set()
    entries = 0

    for info in _ghs_entries(record):
        entries += 1
        references.add(info.get("ReferenceNumber"))
        name = info.get("Name")
        for item in _strings(info):
            text = " ".join(str(item.get("String", "")).split())
            if name == "GHS Hazard Statements":
                match = _STATEMENT.match(text)
                if match:
                    code = re.sub(r"\s+", "", match["codes"])
                    statements.setdefault(code, HazardStatement(code, match["text"]))
            elif name == "Pictogram(s)":
                for mark in item.get("Markup", []):
                    if not isinstance(mark, dict) or mark.get("Type") != "Icon":
                        continue
                    found = _PICTOGRAM.search(str(mark.get("URL", "")))
                    if found:
                        code = found.group(1)
                        label = str(mark.get("Extra", "")).strip() or code
                        pictograms.setdefault(code, Pictogram(code, label))
            elif name == "Signal" and text in ("Danger", "Warning"):
                signals.add(text)
            elif name == "Note" and text and text not in notes:
                notes.append(text)

    listed = record.get("Record", {}).get("Reference", [])
    sources = {
        str(ref["SourceName"])
        for ref in listed
        if isinstance(ref, dict)
        and ref.get("ReferenceNumber") in references
        and ref.get("SourceName")
    }
    signal = "Danger" if "Danger" in signals else ("Warning" if signals else None)
    return GhsData(
        reported=entries > 0,
        hazard_statements=tuple(sorted(statements.values(), key=lambda s: s.code)),
        pictograms=tuple(sorted(pictograms.values(), key=lambda p: p.code)),
        signal_word=signal,
        notes=tuple(notes),
        sources=tuple(sorted(sources)),
    )


def suggest_hazard_classes(codes: frozenset[str]) -> list[HazardClass]:
    """Hazard classes the GHS codes point to, sorted. Never "no_storage_hazard"."""
    return sorted(
        hazard for hazard, triggers in _SUGGESTIONS.items() if codes & triggers
    )
