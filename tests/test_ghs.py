import json
from pathlib import Path
from typing import Any

import pytest

from chemstock.compatibility import HazardClass
from chemstock.ghs import HazardStatement, Pictogram, parse_ghs, suggest_hazard_classes

DATA = Path(__file__).parent / "data"


def load(name: str) -> dict[str, Any]:
    return json.loads((DATA / name).read_text())


def ghs_record(*information: dict[str, Any]) -> dict[str, Any]:
    """A PUG View answer with these entries under "GHS Classification"."""
    return {
        "Record": {
            "Section": [
                {"TOCHeading": "GHS Classification", "Information": list(information)}
            ],
            "Reference": [{"ReferenceNumber": 1, "SourceName": "Test source"}],
        }
    }


def statements(*texts: str) -> dict[str, Any]:
    items = [{"String": text} for text in texts]
    return {
        "ReferenceNumber": 1,
        "Name": "GHS Hazard Statements",
        "Value": {"StringWithMarkup": items},
    }


def signal(word: str) -> dict[str, Any]:
    return {
        "ReferenceNumber": 1,
        "Name": "Signal",
        "Value": {"StringWithMarkup": [{"String": word}]},
    }


# --- real-shaped PubChem answers (see tests/data) ---------------------------


def test_acetone_is_read_completely() -> None:
    data = parse_ghs(load("pubchem_acetone_ghs.json"))

    assert data.reported is True
    assert data.hazard_statements == (
        HazardStatement("H225", "Highly Flammable liquid and vapor"),
        HazardStatement("H319", "Causes serious eye irritation"),
        HazardStatement("H336", "May cause drowsiness or dizziness"),
    )
    assert data.pictograms == (
        Pictogram("GHS02", "Flammable"),
        Pictogram("GHS07", "Irritant"),
    )
    assert data.signal_word == "Danger"
    assert data.codes == {"H225", "H319", "H336"}
    assert data.sources == (
        "European Chemicals Agency (ECHA)",
        "Regulation (EC) No 1272/2008 of the European Parliament and of the Council",
    )
    assert data.notes == (
        "This chemical does not meet GHS hazard criteria for < 0.1% (2 of 5005) "
        "of reports.",
    )


def test_sucrose_has_a_ghs_section_but_no_hazards() -> None:
    data = parse_ghs(load("pubchem_sucrose_ghs.json"))

    assert data.reported is True
    assert data.hazard_statements == ()
    assert data.pictograms == ()
    assert data.signal_word is None
    assert data.sources == ("European Chemicals Agency (ECHA)",)


# --- details of the parser ---------------------------------------------------


def test_an_empty_answer_reports_nothing() -> None:
    data = parse_ghs({})

    assert data.reported is False
    assert data.hazard_statements == ()
    assert data.sources == ()


def test_percentages_and_class_names_are_removed_and_duplicates_merged() -> None:
    data = parse_ghs(
        ghs_record(
            statements(
                "H290 (12.5%): May be corrosive to metals [Warning Corrosive]",
                "H290: May be corrosive to metals",
            )
        )
    )

    assert data.hazard_statements == (
        HazardStatement("H290", "May be corrosive to metals"),
    )


def test_combined_codes_are_kept_together_and_split_for_matching() -> None:
    data = parse_ghs(
        ghs_record(
            statements(
                "H300+H310+H330 (5%): Fatal if swallowed, in contact with skin or "
                "if inhaled [Danger Acute toxicity]"
            )
        )
    )

    assert [s.code for s in data.hazard_statements] == ["H300+H310+H330"]
    assert data.codes == {"H300", "H310", "H330"}


def test_eu_codes_are_read() -> None:
    data = parse_ghs(ghs_record(statements("EUH014: Reacts violently with water")))

    assert data.hazard_statements == (
        HazardStatement("EUH014", "Reacts violently with water"),
    )


def test_text_that_is_not_a_hazard_statement_is_ignored() -> None:
    data = parse_ghs(ghs_record(statements("Not Classified", "H2O is water")))

    assert data.hazard_statements == ()
    assert data.reported is True


@pytest.mark.parametrize(
    ("words", "expected"),
    [(["Warning"], "Warning"), (["Warning", "Danger"], "Danger"), (["Maybe"], None)],
)
def test_the_strongest_signal_word_wins(words: list[str], expected: str) -> None:
    data = parse_ghs(ghs_record(*(signal(word) for word in words)))

    assert data.signal_word == expected


def test_entries_outside_the_ghs_classification_are_ignored() -> None:
    record = {
        "Record": {
            "Section": [
                {
                    "TOCHeading": "Some other heading",
                    "Information": [statements("H225: Highly flammable")],
                }
            ]
        }
    }

    assert parse_ghs(record).reported is False


def test_unexpected_shapes_do_not_crash() -> None:
    record = ghs_record(
        "not a dict",  # type: ignore[arg-type]
        {"Name": "GHS Hazard Statements"},  # no Value
        {"Name": "GHS Hazard Statements", "Value": {"StringWithMarkup": ["text"]}},
        {"Name": "Pictogram(s)", "Value": {"StringWithMarkup": [{"Markup": [1]}]}},
    )

    data = parse_ghs(record)

    assert data.hazard_statements == ()
    assert data.pictograms == ()


# --- suggestions -------------------------------------------------------------


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        ({"H225", "H319", "H336"}, [HazardClass.FLAMMABLE]),  # acetone
        ({"H272", "H302"}, [HazardClass.OXIDIZER]),
        ({"H271"}, [HazardClass.OXIDIZER]),
        ({"H260", "H314"}, [HazardClass.WATER_REACTIVE]),
        ({"EUH014"}, [HazardClass.WATER_REACTIVE]),
        ({"EUH032", "H300"}, [HazardClass.ACID_GAS_GENERATOR]),
        ({"H201"}, [HazardClass.ISOLATE]),
        ({"H250"}, [HazardClass.ISOLATE]),
        ({"H226", "H272"}, [HazardClass.FLAMMABLE, HazardClass.OXIDIZER]),
    ],
)
def test_suggestions(codes: set[str], expected: list[HazardClass]) -> None:
    assert suggest_hazard_classes(frozenset(codes)) == expected


@pytest.mark.parametrize(
    "codes",
    [
        set(),  # nothing reported: still not "safe"
        {"H290", "H314"},  # corrosive: an acid or a base, GHS cannot tell
        {"H302", "H319"},  # harmful, irritant: no storage class
    ],
)
def test_nothing_is_suggested_when_ghs_cannot_tell(codes: set[str]) -> None:
    assert suggest_hazard_classes(frozenset(codes)) == []


def test_no_storage_hazard_is_never_suggested() -> None:
    every_code = frozenset(f"H{number}" for number in range(200, 500))

    assert HazardClass.NO_STORAGE_HAZARD not in suggest_hazard_classes(every_code)
