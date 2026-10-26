from itertools import product

import pytest

from chemstock.compatibility import (
    HAZARD_CLASS_DESCRIPTIONS,
    RULES,
    HazardClass,
    PairStatus,
    Rule,
    assess_pair,
)

H = HazardClass
ACIDS = (H.OXIDIZING_ACID, H.INORGANIC_ACID, H.ORGANIC_ACID)
BASES = (H.INORGANIC_BASE, H.ORGANIC_BASE)

# The expectations below are written independently of the rule table: they
# are the chemist's specification, so a typo in RULES cannot hide itself.
REACTION_RISK_PAIRS = [
    (H.OXIDIZER, H.FLAMMABLE),
    (H.OXIDIZER, H.ACTIVE_METAL),
    (H.OXIDIZER, H.ACID_GAS_GENERATOR),
    (H.OXIDIZER, H.WATER_REACTIVE),
    (H.OXIDIZING_ACID, H.FLAMMABLE),
    (H.OXIDIZING_ACID, H.ORGANIC_ACID),
    (H.OXIDIZING_ACID, H.INORGANIC_ACID),
    (H.HALOGENATED_SOLVENT, H.ACTIVE_METAL),
    *product(ACIDS, BASES),
    *product(ACIDS, [H.ACID_GAS_GENERATOR]),
    *product(ACIDS, [H.ACTIVE_METAL]),
    *product(ACIDS, [H.WATER_REACTIVE]),
    *product([H.OXIDIZER], ACIDS),
]

SEPARATION_ADVISED_PAIRS = [
    (H.INORGANIC_ACID, H.ORGANIC_ACID),
    (H.INORGANIC_ACID, H.FLAMMABLE),
    (H.ORGANIC_ACID, H.FLAMMABLE),
    *product([H.HALOGENATED_SOLVENT], BASES),
    *product(BASES, [H.FLAMMABLE]),
    *product(BASES, [H.OXIDIZER]),
]

NO_CONFLICT_PAIRS = [
    (H.FLAMMABLE, H.WATER_REACTIVE),  # deliberately not a rule
    (H.FLAMMABLE, H.FLAMMABLE),
    (H.OXIDIZER, H.OXIDIZER),
    (H.INORGANIC_ACID, H.INORGANIC_ACID),
    (H.ORGANIC_ACID, H.ORGANIC_ACID),
    (H.OXIDIZING_ACID, H.OXIDIZING_ACID),
    (H.INORGANIC_BASE, H.ORGANIC_BASE),
    (H.INORGANIC_BASE, H.INORGANIC_BASE),
]


@pytest.mark.parametrize(("first", "second"), REACTION_RISK_PAIRS)
def test_reaction_risk_pairs_are_severity_1(
    first: HazardClass, second: HazardClass
) -> None:
    for a, b in ((first, second), (second, first)):
        result = assess_pair([a], [b])

        assert result.status is PairStatus.CONFLICT
        assert result.severity == 1


@pytest.mark.parametrize(("first", "second"), SEPARATION_ADVISED_PAIRS)
def test_separation_advised_pairs_are_severity_2(
    first: HazardClass, second: HazardClass
) -> None:
    for a, b in ((first, second), (second, first)):
        result = assess_pair([a], [b])

        assert result.status is PairStatus.CONFLICT
        assert result.severity == 2


@pytest.mark.parametrize(("first", "second"), NO_CONFLICT_PAIRS)
def test_pairs_without_a_rule_are_compatible(
    first: HazardClass, second: HazardClass
) -> None:
    for a, b in ((first, second), (second, first)):
        result = assess_pair([a], [b])

        assert result.status is PairStatus.NO_CONFLICT
        assert result.severity is None
        assert result.reasons == ()


@pytest.mark.parametrize("other", list(HazardClass))
def test_isolate_conflicts_with_every_class(other: HazardClass) -> None:
    for a, b in ((H.ISOLATE, other), (other, H.ISOLATE)):
        result = assess_pair([a], [b])

        assert result.status is PairStatus.CONFLICT
        assert result.severity == 1
        assert "isolate" in {reason.rule for reason in result.reasons}


def test_isolate_conflicts_even_with_a_chemical_of_unknown_hazards() -> None:
    result = assess_pair([H.ISOLATE], [])

    assert result.status is PairStatus.CONFLICT
    assert result.severity == 1


def test_multi_class_pair_reports_highest_severity_and_all_reasons() -> None:
    sulfuric = [H.INORGANIC_ACID, H.OXIDIZING_ACID]  # concentrated H2SO4
    acetic = [H.ORGANIC_ACID, H.FLAMMABLE]  # glacial acetic acid

    result = assess_pair(sulfuric, acetic)

    # Only the most serious level is reported, but every reason is kept.
    assert result.status is PairStatus.CONFLICT
    assert result.severity == 1
    assert [(reason.severity, reason.rule) for reason in result.reasons] == [
        (1, "oxidizing-acid-flammable"),
        (1, "oxidizing-acid-organic-acid"),
        (2, "acid-flammable"),
        (2, "inorganic-acid-organic-acid"),
    ]


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ([], [H.FLAMMABLE]),
        ([H.UNCLASSIFIED], [H.INORGANIC_ACID]),
        ([], []),
        ([H.UNCLASSIFIED], [H.UNCLASSIFIED]),
        ([H.FLAMMABLE, H.UNCLASSIFIED], [H.FLAMMABLE]),
    ],
)
def test_incomplete_information_requires_review(
    first: list[HazardClass], second: list[HazardClass]
) -> None:
    for a, b in ((first, second), (second, first)):
        result = assess_pair(a, b)

        assert result.status is PairStatus.REVIEW_REQUIRED
        assert result.severity is None
        assert result.reasons == ()


def test_known_conflict_is_reported_even_if_other_info_is_incomplete() -> None:
    result = assess_pair([H.OXIDIZER, H.UNCLASSIFIED], [H.FLAMMABLE])

    assert result.status is PairStatus.CONFLICT
    assert result.severity == 1


def test_accepts_plain_strings_as_class_names() -> None:
    result = assess_pair(["oxidizer"], ["flammable"])

    assert result.status is PairStatus.CONFLICT


def test_unknown_class_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        assess_pair(["not_a_class"], [H.FLAMMABLE])


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.code)
def test_every_rule_fires_in_both_orders(rule: Rule) -> None:
    for x, y in product(rule.side_a, rule.side_b):
        forward = {reason.rule for reason in assess_pair([x], [y]).reasons}
        backward = {reason.rule for reason in assess_pair([y], [x]).reasons}

        assert rule.code in forward
        assert rule.code in backward


def test_rule_table_is_well_formed() -> None:
    codes = [rule.code for rule in RULES]

    assert len(codes) == len(set(codes))
    assert all(rule.severity in (1, 2) and rule.reason for rule in RULES)


def test_every_hazard_class_has_a_description() -> None:
    assert set(HAZARD_CLASS_DESCRIPTIONS) == set(HazardClass)
    assert all(HAZARD_CLASS_DESCRIPTIONS.values())
