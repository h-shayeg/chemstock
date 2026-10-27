from fastapi import FastAPI

from chemstock.routers import (
    auth,
    chemicals,
    hazard_classes,
    inventory_items,
    storage_conflicts,
)

app = FastAPI(
    title="ChemStock",
    description="Laboratory chemical inventory and safety management API",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(chemicals.router)
app.include_router(hazard_classes.router)
app.include_router(inventory_items.router)
app.include_router(storage_conflicts.router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
