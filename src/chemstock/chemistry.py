import re

_CAS_PATTERN = re.compile(r"[0-9]{2,7}-[0-9]{2}-[0-9]")


def is_valid_cas(cas: str) -> bool:
    """Return True if ``cas`` is a well-formed CAS Registry Number.

    A CAS number looks like ``7732-18-5``. The last digit is a check digit:
    multiply the other digits by 1, 2, 3, ... starting from the right, add
    them up, and the sum modulo 10 must equal the check digit.
    """
    if not _CAS_PATTERN.fullmatch(cas):
        return False
    digits = cas.replace("-", "")
    body, check_digit = digits[:-1], int(digits[-1])
    total = sum(
        position * int(digit)
        for position, digit in enumerate(reversed(body), start=1)
    )
    return total % 10 == check_digit
