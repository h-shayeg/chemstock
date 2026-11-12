from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from chemstock.dependencies import require_access
from chemstock.routers import (
    auth,
    chemicals,
    hazard_classes,
    inventory_items,
    storage_conflicts,
    users,
)
from chemstock.web import routes as web

app = FastAPI(
    title="ChemStock",
    description="Laboratory chemical inventory and safety management API",
    version="1.0.0",
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


# The Persian web pages (see chemstock.web). Their style sheet and font are
# served from here too, so the pages work without internet access.
app.mount("/ui/static", StaticFiles(directory=web.STATIC_DIR), name="static")
app.include_router(web.router)


@app.exception_handler(web.LoginRequired)
async def login_required_handler(
    request: Request, exc: web.LoginRequired
) -> RedirectResponse:
    return web.login_redirect()


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(web.HOME_PATH)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
