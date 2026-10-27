from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from chemstock.dependencies import require_access
from chemstock.routers import (
    auth,
    chemicals,
    hazard_classes,
    inventory_items,
    storage_conflicts,
    users,
)

app = FastAPI(
    title="ChemStock",
    description="Laboratory chemical inventory and safety management API",
    version="0.1.0",
)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Like FastAPI's default 422, but without echoing the submitted data.

    The default answer repeats the input of every invalid field and, for a
    missing field, the whole request body, which can contain a password.
    """
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


# Everything below needs a logged-in user; the role decides what is allowed.
protected = [Depends(require_access)]

# Login is public, "/auth/me" checks the token by itself, and "/users" has its
# own, stricter rules (see routers/users.py).
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(chemicals.router, dependencies=protected)
app.include_router(hazard_classes.router, dependencies=protected)
app.include_router(inventory_items.router, dependencies=protected)
app.include_router(storage_conflicts.router, dependencies=protected)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
