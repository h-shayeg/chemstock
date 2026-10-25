"""Storage-compatibility rules for laboratory chemicals.

This module is pure logic (no database). From the hazard classes of two
chemicals it decides whether they should be stored apart.

It is an assistive tool, not a replacement for the Safety Data Sheet (SDS).
Hazard classes are a simplification and one chemical can belong to several of
them (for example, concentrated sulfuric acid is both an inorganic acid and an
oxidizing acid). Always check the final classification against the SDS.

Two bottles of the SAME chemical must not be compared with each other: that is
the caller's job, because this module only sees classes, not chemicals.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class HazardClass(StrEnum):
    FLAMMABLE = "flammable"
    OXIDIZER = "oxidizer"
    OXIDIZING_ACID = "oxidizing_acid"
    INORGANIC_ACID = "inorganic_acid"
    ORGANIC_ACID = "organic_acid"
    INORGANIC_BASE = "inorganic_base"
    ORGANIC_BASE = "organic_base"
    ACTIVE_METAL = "active_metal"
    ACID_GAS_GENERATOR = "acid_gas_generator"
    WATER_REACTIVE = "water_reactive"
    HALOGENATED_SOLVENT = "halogenated_solvent"
    ISOLATE = "isolate"
    # "We do not know yet". It never means "safe".
    UNCLASSIFIED = "unclassified"


H = HazardClass

HAZARD_CLASS_DESCRIPTIONS: dict[HazardClass, str] = {
    H.FLAMMABLE: "Flammable liquids and solids, and combustible materials.",
    H.OXIDIZER: "Oxidizing agents, such as nitrates, permanganates and peroxides.",
    H.OXIDIZING_ACID: (
        "Acids with strong oxidizing power: nitric, perchloric and chromic acid."
    ),
    H.INORGANIC_ACID: (
        "Inorganic (mineral) acids such as HCl and H3PO4. "
        "Concentrated H2SO4 is also an oxidizing acid."
    ),
    H.ORGANIC_ACID: "Organic acids, such as acetic acid and trifluoroacetic acid.",
    H.INORGANIC_BASE: (
        "Strong inorganic bases, such as NaOH and KOH. "
        "Carbonates and bicarbonates are excluded."
    ),
    H.ORGANIC_BASE: "Organic bases such as amines.",
    H.ACTIVE_METAL: (
        "Active metals, Al/Zn/Mg powders and hydrides. "
        "Not every reducing agent belongs here."
    ),
    H.ACID_GAS_GENERATOR: (
        "Substances that release toxic gas on contact with acids: cyanides, "
        "sulfides, azides, hypochlorites, nitrites, sulfites, arsenides, "
        "phosphides and fluorides."
    ),
    H.WATER_REACTIVE: "Substances that react dangerously with water.",
    H.HALOGENATED_SOLVENT: (
        "Halogenated organic solvents, such as dichloromethane and chloroform."
    ),
    H.ISOLATE: "Chemicals that must be stored isolated from all others (see SDS).",
    H.UNCLASSIFIED: (
        "No hazard classification entered yet. This does not mean it is safe."
    ),
}

ACIDS = frozenset({H.OXIDIZING_ACID, H.INORGANIC_ACID, H.ORGANIC_ACID})
BASES = frozenset({H.INORGANIC_BASE, H.ORGANIC_BASE})
ALL_CLASSES = frozenset(HazardClass)

# Severity 1: risk of a hazardous reaction. Severity 2: separation advised.
REACTION_RISK = 1
SEPARATION_ADVISED = 2


@dataclass(frozen=True)
class Rule:
    code: str
    severity: int
    side_a: frozenset[HazardClass]
    side_b: frozenset[HazardClass]
    reason: str

    def matches(self, a: frozenset[HazardClass], b: frozenset[HazardClass]) -> bool:
        """True if the pair triggers this rule, in either order."""
        forward = bool(self.side_a & a) and bool(self.side_b & b)
        backward = bool(self.side_a & b) and bool(self.side_b & a)
        return forward or backward


def _rule(
    code: str,
    severity: int,
    a: Iterable[HazardClass],
    b: Iterable[HazardClass],
    reason: str,
) -> Rule:
    return Rule(code, severity, frozenset(a), frozenset(b), reason)


RULES: tuple[Rule, ...] = (
    # --- Severity 1: reaction risk ---
    _rule(
        "oxidizer-flammable",
        REACTION_RISK,
        {H.OXIDIZER},
        {H.FLAMMABLE},
        "Oxidizers can fuel fires with flammable and combustible materials.",
    ),
    _rule(
        "oxidizer-active-metal",
        REACTION_RISK,
        {H.OXIDIZER},
        {H.ACTIVE_METAL},
        "Oxidizers can react violently with active metals.",
    ),
    _rule(
        "oxidizing-acid-flammable",
        REACTION_RISK,
        {H.OXIDIZING_ACID},
        {H.FLAMMABLE},
        "Oxidizing acids can ignite flammable and combustible materials.",
    ),
    _rule(
        "oxidizing-acid-organic-acid",
        REACTION_RISK,
        {H.OXIDIZING_ACID},
        {H.ORGANIC_ACID},
        "Oxidizing acids can react violently with organic acids.",
    ),
    _rule(
        "oxidizing-acid-inorganic-acid",
        REACTION_RISK,
        {H.OXIDIZING_ACID},
        {H.INORGANIC_ACID},
        "Oxidizing acids must be kept apart from other inorganic acids.",
    ),
    _rule(
        "acid-base",
        REACTION_RISK,
        ACIDS,
        BASES,
        "Acids and bases can react violently and release a lot of heat.",
    ),
    _rule(
        "acid-acid-gas-generator",
        REACTION_RISK,
        ACIDS,
        {H.ACID_GAS_GENERATOR},
        "Acids release toxic gases on contact with cyanides, sulfides, azides, "
        "hypochlorites, nitrites, sulfites, arsenides, phosphides or fluorides.",
    ),
    _rule(
        "acid-active-metal",
        REACTION_RISK,
        ACIDS,
        {H.ACTIVE_METAL},
        "Acids react with active metals and release flammable hydrogen.",
    ),
    _rule(
        "oxidizer-acid",
        REACTION_RISK,
        {H.OXIDIZER},
        ACIDS,
        "Acids can react with oxidizers and release hazardous gases.",
    ),
    _rule(
        "oxidizer-acid-gas-generator",
        REACTION_RISK,
        {H.OXIDIZER},
        {H.ACID_GAS_GENERATOR},
        "Oxidizers can react violently with cyanides, sulfides, azides and similar "
        "compounds.",
    ),
    _rule(
        "water-reactive-acid",
        REACTION_RISK,
        {H.WATER_REACTIVE},
        ACIDS,
        "Acids can react violently with water-reactive substances.",
    ),
    _rule(
        "water-reactive-oxidizer",
        REACTION_RISK,
        {H.WATER_REACTIVE},
        {H.OXIDIZER},
        "Oxidizers can react violently with water-reactive substances.",
    ),
    _rule(
        "halogenated-solvent-active-metal",
        REACTION_RISK,
        {H.HALOGENATED_SOLVENT},
        {H.ACTIVE_METAL},
        "Halogenated solvents can react violently with active metals.",
    ),
    _rule(
        "isolate",
        REACTION_RISK,
        {H.ISOLATE},
        ALL_CLASSES,
        "Must be stored isolated from all other chemicals; see the SDS.",
    ),
    # --- Severity 2: separation advised ---
    _rule(
        "inorganic-acid-organic-acid",
        SEPARATION_ADVISED,
        {H.INORGANIC_ACID},
        {H.ORGANIC_ACID},
        "Inorganic and organic acids should be stored separately.",
    ),
    _rule(
        "acid-flammable",
        SEPARATION_ADVISED,
        ACIDS,
        {H.FLAMMABLE},
        "Acids should be kept away from flammable materials.",
    ),
    _rule(
        "halogenated-solvent-base",
        SEPARATION_ADVISED,
        {H.HALOGENATED_SOLVENT},
        BASES,
        "Halogenated solvents should be kept away from bases.",
    ),
    _rule(
        "base-flammable",
        SEPARATION_ADVISED,
        BASES,
        {H.FLAMMABLE},
        "Bases should be kept away from flammable materials.",
    ),
    _rule(
        "base-oxidizer",
        SEPARATION_ADVISED,
        BASES,
        {H.OXIDIZER},
        "Bases should be kept away from oxidizers.",
    ),
    # Deliberately absent: flammable <-> water_reactive. Storage of
    # water-reactive materials depends on the specific hazard and the SDS.
)


class PairStatus(StrEnum):
    CONFLICT = "conflict"
    # Not enough hazard information to say the pair is compatible.
    REVIEW_REQUIRED = "review_required"
    NO_CONFLICT = "no_conflict"


@dataclass(frozen=True)
class Reason:
    rule: str
    severity: int
    message: str


@dataclass(frozen=True)
class PairAssessment:
    status: PairStatus
    # 1 or 2 for a conflict (the most serious matching rule), otherwise None.
    severity: int | None
    # Every matching rule, most serious first (ties broken by rule code).
    reasons: tuple[Reason, ...]


def _normalize(classes: Iterable[HazardClass | str]) -> frozenset[HazardClass]:
    """Parse class names; no classes at all means "unclassified"."""
    parsed = frozenset(HazardClass(item) for item in classes)
    return parsed or frozenset({HazardClass.UNCLASSIFIED})


def assess_pair(
    classes_a: Iterable[HazardClass | str],
    classes_b: Iterable[HazardClass | str],
) -> PairAssessment:
    """Decide whether two chemicals should be stored apart.

    Known conflicts are always reported. Without a conflict, a pair is only
    called compatible if both chemicals are classified.
    """
    a = _normalize(classes_a)
    b = _normalize(classes_b)

    reasons = sorted(
        (
            Reason(rule.code, rule.severity, rule.reason)
            for rule in RULES
            if rule.matches(a, b)
        ),
        key=lambda reason: (reason.severity, reason.rule),
    )
    if reasons:
        return PairAssessment(PairStatus.CONFLICT, reasons[0].severity, tuple(reasons))

    if HazardClass.UNCLASSIFIED in a or HazardClass.UNCLASSIFIED in b:
        return PairAssessment(PairStatus.REVIEW_REQUIRED, None, ())
    return PairAssessment(PairStatus.NO_CONFLICT, None, ())
