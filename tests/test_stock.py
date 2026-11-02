from decimal import Decimal

import pytest

from chemstock.stock import (
    Amount,
    StockedChemical,
    check_stock,
    convert,
    find_low_stock,
    tidy,
)


def chemical(
    chemical_id: int,
    level: str,
    unit: str,
    *bottles: tuple[str, str],
    name: str | None = None,
) -> StockedChemical:
    return StockedChemical(
        chemical_id=chemical_id,
        chemical_name=name or f"Chemical {chemical_id}",
        reorder_level=Decimal(level),
        reorder_unit=unit,
        bottles=tuple(Amount(Decimal(q), u) for q, u in bottles),
    )


@pytest.mark.parametrize(
    ("quantity", "from_unit", "to_unit", "expected"),
    [
        ("500", "g", "kg", "0.5"),
        ("1.5", "kg", "g", "1500"),
        ("250", "mg", "g", "0.25"),
        ("1", "mg", "kg", "0.000001"),
        ("2", "L", "mL", "2000"),
        ("750", "mL", "L", "0.75"),
        ("3", "g", "g", "3"),
    ],
)
def test_convert_within_one_kind(
    quantity: str, from_unit: str, to_unit: str, expected: str
) -> None:
    assert convert(Decimal(quantity), from_unit, to_unit) == Decimal(expected)


@pytest.mark.parametrize(("from_unit", "to_unit"), [("g", "L"), ("mL", "kg")])
def test_mass_and_volume_cannot_be_converted(from_unit: str, to_unit: str) -> None:
    assert convert(Decimal(1), from_unit, to_unit) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.5", "1.500"),
        ("1.500000", "1.500"),
        ("0", "0.000"),
        ("1E+3", "1000.000"),
        ("0.0005", "0.0005"),
        ("0.000001", "0.000001"),
    ],
)
def test_tidy_keeps_three_places_and_every_digit(value: str, expected: str) -> None:
    assert str(tidy(Decimal(value))) == expected


def test_enough_stock_is_not_reported() -> None:
    assert check_stock(chemical(1, "1", "L", ("2", "L"))) is None


def test_stock_below_the_level_is_reported() -> None:
    report = check_stock(chemical(1, "1", "L", ("0.4", "L")))

    assert report is not None
    assert report.total_quantity == Decimal("0.4")
    assert report.unit == "L"
    assert (report.item_count, report.uncounted_item_count) == (1, 0)


def test_stock_exactly_at_the_level_is_reported() -> None:
    assert check_stock(chemical(1, "1", "L", ("1", "L"))) is not None


def test_bottles_in_different_units_are_added_up() -> None:
    # 400 g + 0.5 kg + 50000 mg = 950 g, just under 1 kg.
    report = check_stock(
        chemical(1, "1", "kg", ("400", "g"), ("0.5", "kg"), ("50000", "mg"))
    )

    assert report is not None
    assert report.total_quantity == Decimal("0.95")
    assert str(report.total_quantity) == "0.950"
    assert report.item_count == 3


def test_a_chemical_without_bottles_has_run_out() -> None:
    report = check_stock(chemical(1, "100", "g"))

    assert report is not None
    assert report.total_quantity == 0
    assert report.item_count == 0


def test_a_level_of_zero_reports_only_an_empty_stock() -> None:
    assert check_stock(chemical(1, "0", "g", ("1", "mg"))) is None
    assert check_stock(chemical(1, "0", "g", ("0", "g"))) is not None


def test_bottles_of_the_other_kind_are_left_out_and_counted() -> None:
    # The level is a mass; the 2 L bottle cannot be added without the density.
    report = check_stock(chemical(1, "500", "g", ("100", "g"), ("2", "L")))

    assert report is not None
    assert report.total_quantity == Decimal("100")
    assert (report.item_count, report.uncounted_item_count) == (1, 1)


def test_enough_stock_is_not_reported_even_with_uncounted_bottles() -> None:
    assert check_stock(chemical(1, "500", "g", ("1", "kg"), ("2", "L"))) is None


def test_emptiest_chemicals_come_first() -> None:
    half = chemical(1, "10", "g", ("5", "g"))
    empty = chemical(2, "1", "L")
    nearly_empty = chemical(3, "1", "kg", ("100", "g"))
    plenty = chemical(4, "1", "L", ("5", "L"))

    result = find_low_stock([half, empty, nearly_empty, plenty])

    assert [report.chemical_id for report in result] == [2, 3, 1]


def test_equal_shares_are_sorted_by_name_then_id() -> None:
    result = find_low_stock(
        [
            chemical(1, "1", "L", name="ethanol"),
            chemical(2, "1", "L", name="Acetone"),
            chemical(3, "0", "g", name="Acetone"),
        ]
    )

    assert [report.chemical_id for report in result] == [2, 3, 1]
