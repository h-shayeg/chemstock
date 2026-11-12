from datetime import date

import pytest

from chemstock.jalali import jalali_date, jalali_long, persian_digits, persian_number


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 11, 12), "۱۴۰۵/۰۸/۲۱"),
        (date(2026, 3, 21), "۱۴۰۵/۰۱/۰۱"),  # Nowruz
        (date(2026, 3, 20), "۱۴۰۴/۱۲/۲۹"),  # last day of 1404 (not a leap year)
        (date(2025, 3, 20), "۱۴۰۳/۱۲/۳۰"),  # 1403 is a leap year: 30 Esfand
    ],
)
def test_jalali_date(day: date, expected: str) -> None:
    assert jalali_date(day) == expected


def test_jalali_long_uses_the_month_name() -> None:
    assert jalali_long(date(2026, 11, 12)) == "۲۱ آبان ۱۴۰۵"
    assert jalali_long(date(2026, 3, 21)) == "۱ فروردین ۱۴۰۵"


def test_persian_digits_change_only_digits() -> None:
    assert persian_digits("CAS 67-64-1") == "CAS ۶۷-۶۴-۱"
    assert persian_digits(30) == "۳۰"


def test_persian_number_uses_the_persian_thousands_separator() -> None:
    assert persian_number(0) == "۰"
    assert persian_number(482) == "۴۸۲"
    assert persian_number(1236) == "۱٬۲۳۶"
    assert persian_number(1234567) == "۱٬۲۳۴٬۵۶۷"
