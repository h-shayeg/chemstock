from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from chemstock.chemistry import is_valid_cas


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
    created_at: datetime
