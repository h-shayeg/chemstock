import pytest
from pydantic import ValidationError

from chemstock.schemas import ChemicalCreate


def test_create_accepts_minimal_payload() -> None:
    chemical = ChemicalCreate(name="Acetone")

    assert chemical.cas_number is None
    assert chemical.formula is None


def test_create_strips_whitespace() -> None:
    chemical = ChemicalCreate(name="  Acetone  ", cas_number=" 67-64-1 ")

    assert chemical.name == "Acetone"
    assert chemical.cas_number == "67-64-1"


def test_create_rejects_invalid_cas() -> None:
    with pytest.raises(ValidationError):
        ChemicalCreate(name="Water", cas_number="7732-18-4")


def test_create_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        ChemicalCreate(name="   ")
