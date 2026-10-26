from fastapi import APIRouter

from chemstock.compatibility import HAZARD_CLASS_DESCRIPTIONS, HazardClass
from chemstock.schemas import HazardClassRead

router = APIRouter(prefix="/hazard-classes", tags=["hazard classes"])


@router.get("", response_model=list[HazardClassRead])
def list_hazard_classes() -> list[HazardClassRead]:
    """Every hazard class a chemical can be given, with its meaning."""
    return [
        HazardClassRead(name=hazard, description=HAZARD_CLASS_DESCRIPTIONS[hazard])
        for hazard in HazardClass
    ]
