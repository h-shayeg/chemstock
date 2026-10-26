from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from chemstock.chemistry import is_valid_cas
from chemstock.compatibility import HazardClass


def _check_cas(value: str | None) -> str | None:
    if value is not None and not is_valid_cas(value):
        raise ValueError("invalid CAS Registry Number")
    return value


class ChemicalCreate(BaseModel):
    """Data a client sends to create a chemical."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    cas_number: str | None = Field(default=None, max_length=12)
    formula: str | None = Field(default=None, max_length=100)

    @field_validator("cas_number")
    @classmethod
    def validate_cas_number(cls, value: str | None) -> str | None:
        return _check_cas(value)


class ChemicalUpdate(BaseModel):
    """Partial update: only the fields the client sends are changed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    cas_number: str | None = Field(default=None, max_length=12)
    formula: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def name_cannot_be_null(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("name cannot be null")
        return value

    @field_validator("cas_number")
    @classmethod
    def validate_cas_number(cls, value: str | None) -> str | None:
        return _check_cas(value)


class ChemicalRead(BaseModel):
    """Data the API returns for a chemical."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cas_number: str | None
    formula: str | None
    hazard_classes: list[HazardClass]
    created_at: datetime


Unit = Literal["mg", "g", "kg", "mL", "L"]


class InventoryItemCreate(BaseModel):
    """Data a client sends to register a bottle."""

    model_config = ConfigDict(str_strip_whitespace=True)

    chemical_id: int = Field(ge=1, le=2_147_483_647)
    quantity: Decimal = Field(ge=0, max_digits=12, decimal_places=3)
    unit: Unit
    location: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None


class InventoryItemUpdate(BaseModel):
    """Partial update of a bottle. The chemical itself cannot be changed."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    quantity: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=3
    )
    unit: Unit | None = None
    location: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None

    @field_validator("quantity", "unit")
    @classmethod
    def required_fields_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("this field cannot be null")
        return value


class InventoryItemRead(BaseModel):
    """Data the API returns for a bottle."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chemical_id: int
    quantity: Decimal
    unit: str
    location: str | None
    expiry_date: date | None
    created_at: datetime


class ExpiringItemRead(InventoryItemRead):
    """A bottle in the expiry report. Negative days mean already expired."""

    days_until_expiry: int


class HazardClassesUpdate(BaseModel):
    """The complete set of hazard classes of a chemical (replaces the old set)."""

    hazard_classes: list[HazardClass] = Field(max_length=50)

    @field_validator("hazard_classes")
    @classmethod
    def remove_duplicates(cls, value: list[HazardClass]) -> list[HazardClass]:
        unique = sorted(set(value))
        if HazardClass.UNCLASSIFIED in unique and len(unique) > 1:
            raise ValueError(
                "'unclassified' cannot be combined with other hazard classes"
            )
        return unique


class HazardClassRead(BaseModel):
    """A hazard class and what it means."""

    name: HazardClass
    description: str


class ConflictItem(BaseModel):
    """One of the two bottles of a storage conflict."""

    inventory_item_id: int
    chemical_id: int
    chemical_name: str
    hazard_classes: list[str]


class ConflictReason(BaseModel):
    """One rule that applies to a pair of bottles."""

    rule: str
    severity: int
    message: str


class StorageConflictRead(BaseModel):
    """Two bottles in the same place that should be stored apart."""

    status: Literal["conflict", "review_required"]
    severity: int | None
    location: str
    items: list[ConflictItem]
    reasons: list[ConflictReason]
