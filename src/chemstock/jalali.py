"""Persian (Jalali / Solar Hijri) dates and Persian digits for the web pages.

The database keeps ordinary (Gregorian) dates; only what people see is
converted. The calendar conversion itself is done by the jdatetime library.
"""

from datetime import date

import jdatetime

MONTH_NAMES = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)

_TO_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def persian_digits(value: object) -> str:
    """Write every Western digit (0-9) of the value as a Persian digit."""
    return str(value).translate(_TO_PERSIAN_DIGITS)


def persian_number(value: int) -> str:
    """A whole number with Persian digits and the Persian thousands separator."""
    return persian_digits(f"{value:,}").replace(",", "٬")


def to_jalali(day: date) -> jdatetime.date:
    return jdatetime.date.fromgregorian(date=day)


def jalali_date(day: date) -> str:
    """Short form, year first, as on Iranian forms: ۱۴۰۵/۰۸/۲۱."""
    j = to_jalali(day)
    return persian_digits(f"{j.year:04d}/{j.month:02d}/{j.day:02d}")


def jalali_long(day: date) -> str:
    """Long form with the month's name: ۲۱ آبان ۱۴۰۵."""
    j = to_jalali(day)
    month = MONTH_NAMES[j.month - 1]
    return f"{persian_digits(j.day)} {month} {persian_digits(j.year)}"
