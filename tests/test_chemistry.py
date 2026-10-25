import pytest

from chemstock.chemistry import is_valid_cas


@pytest.mark.parametrize(
    "cas",
    [
        "7732-18-5",  # water
        "67-64-1",  # acetone
        "64-17-5",  # ethanol
        "7647-14-5",  # sodium chloride
    ],
)
def test_valid_cas_numbers(cas: str) -> None:
    assert is_valid_cas(cas)


@pytest.mark.parametrize(
    "cas",
    [
        "7732-18-4",  # wrong check digit
        "",
        "abc",
        "7732185",  # missing hyphens
        "7732-18-55",
        "1-23-4",
        " 7732-18-5",  # leading space
        "\u06f7\u06f7\u06f3\u06f2-\u06f1\u06f8-\u06f5",  # Persian digits
    ],
)
def test_invalid_cas_numbers(cas: str) -> None:
    assert not is_valid_cas(cas)
