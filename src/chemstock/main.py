from fastapi import Depends, FastAPI

from chemstock.dependencies import require_access
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

# Everything below needs a logged-in user; the role decides what is allowed.
protected = [Depends(require_access)]

# Login is public, and "/auth/me" checks the token by itself.
app.include_router(auth.router)
app.include_router(chemicals.router, dependencies=protected)
app.include_router(hazard_classes.router, dependencies=protected)
app.include_router(inventory_items.router, dependencies=protected)
app.include_router(storage_conflicts.router, dependencies=protected)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
