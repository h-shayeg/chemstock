import pytest

from chemstock.compatibility import PairStatus
from chemstock.storage import Bottle, find_storage_conflicts, normalize_location

ACID = ("inorganic_acid",)
BASE = ("inorganic_base",)


def bottle(
    item_id: int,
    chemical_id: int,
    classes: tuple[str, ...] = (),
    location: str | None = "Shelf A",
) -> Bottle:
    return Bottle(item_id, chemical_id, f"Chemical {chemical_id}", location, classes)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Shelf B2", "shelf b2"),
        ("  Shelf   B2 ", "shelf b2"),
        ("SHELF\tB2", "shelf b2"),
        ("", ""),
        ("   ", ""),
        (None, ""),
    ],
)
def test_normalize_location(raw: str | None, expected: str) -> None:
    assert normalize_location(raw) == expected


def test_acid_and_base_on_the_same_shelf_conflict() -> None:
    acid = bottle(1, 1, ACID)
    base = bottle(2, 2, BASE)

    [conflict] = find_storage_conflicts([acid, base])

    assert conflict.status is PairStatus.CONFLICT
    assert conflict.severity == 1
    assert conflict.location == "Shelf A"
    assert (conflict.first, conflict.second) == (acid, base)
    assert [reason.rule for reason in conflict.reasons] == ["acid-base"]


def test_locations_match_after_normalization() -> None:
    result = find_storage_conflicts(
        [
            bottle(1, 1, ACID, location="Shelf B2"),
            bottle(2, 2, BASE, location="  shelf   b2 "),
        ]
    )

    assert len(result) == 1
    assert result[0].location == "Shelf B2"


def test_different_locations_do_not_conflict() -> None:
    result = find_storage_conflicts(
        [
            bottle(1, 1, ACID, location="Shelf A"),
            bottle(2, 2, BASE, location="Shelf B"),
        ]
    )

    assert result == []


def test_bottles_of_the_same_chemical_never_conflict() -> None:
    # Concentrated sulfuric acid is both an inorganic and an oxidizing acid.
    # Those two classes conflict with each other, but one chemical does not
    # conflict with itself.
    sulfuric = ("inorganic_acid", "oxidizing_acid")

    result = find_storage_conflicts([bottle(1, 1, sulfuric), bottle(2, 1, sulfuric)])

    assert result == []


@pytest.mark.parametrize("location", [None, "", "   "])
def test_bottles_without_location_are_ignored(location: str | None) -> None:
    result = find_storage_conflicts(
        [bottle(1, 1, ACID, location=location), bottle(2, 2, BASE, location=location)]
    )

    assert result == []


def test_compatible_chemicals_report_nothing() -> None:
    result = find_storage_conflicts(
        [bottle(1, 1, ("flammable",)), bottle(2, 2, ("flammable",))]
    )

    assert result == []


def test_unclassified_chemical_requires_review() -> None:
    bottles = [bottle(1, 1, ()), bottle(2, 2, ("flammable",))]

    [conflict] = find_storage_conflicts(bottles)

    assert conflict.status is PairStatus.REVIEW_REQUIRED
    assert conflict.severity is None
    assert conflict.reasons == ()


def test_isolate_conflicts_even_with_an_unclassified_chemical() -> None:
    [conflict] = find_storage_conflicts([bottle(1, 1, ("isolate",)), bottle(2, 2, ())])

    assert conflict.status is PairStatus.CONFLICT
    assert conflict.severity == 1
    assert [reason.rule for reason in conflict.reasons] == ["isolate"]


def test_multi_class_chemicals_report_highest_severity_and_all_reasons() -> None:
    sulfuric = bottle(1, 1, ("inorganic_acid", "oxidizing_acid"))
    glacial_acetic = bottle(2, 2, ("organic_acid", "flammable"))

    [conflict] = find_storage_conflicts([sulfuric, glacial_acetic])

    assert conflict.severity == 1
    assert [(reason.severity, reason.rule) for reason in conflict.reasons] == [
        (1, "oxidizing-acid-flammable"),
        (1, "oxidizing-acid-organic-acid"),
        (2, "acid-flammable"),
        (2, "inorganic-acid-organic-acid"),
    ]


def test_conflicts_are_sorted_by_severity_then_location() -> None:
    bottles = [
        # "Shelf A": only a review (alphabetically first, but least urgent).
        bottle(1, 1, (), location="Shelf A"),
        bottle(2, 2, ("flammable",), location="Shelf A"),
        # "Shelf B": separation advised (severity 2).
        bottle(3, 3, ("inorganic_acid",), location="Shelf B"),
        bottle(4, 4, ("organic_acid",), location="Shelf B"),
        # "Shelf C": reaction risk (severity 1).
        bottle(5, 5, ("inorganic_acid",), location="Shelf C"),
        bottle(6, 6, ("inorganic_base",), location="Shelf C"),
    ]

    result = find_storage_conflicts(bottles)

    assert [c.location for c in result] == ["Shelf C", "Shelf B", "Shelf A"]
    assert [c.severity for c in result] == [1, 2, None]


def test_pair_is_ordered_by_item_id() -> None:
    result = find_storage_conflicts([bottle(7, 2, BASE), bottle(3, 1, ACID)])

    assert (result[0].first.item_id, result[0].second.item_id) == (3, 7)


def test_every_conflicting_pair_is_reported() -> None:
    bottles = [
        bottle(1, 1, ACID),
        bottle(2, 2, BASE),
        bottle(3, 3, ("organic_base",)),
    ]

    result = find_storage_conflicts(bottles)

    # acid-base and acid-organic base conflict; the two bases do not.
    assert [(c.first.item_id, c.second.item_id) for c in result] == [(1, 2), (1, 3)]
