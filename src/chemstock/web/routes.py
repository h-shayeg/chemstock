"""Web pages: login, logout and the dashboard."""

from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from chemstock.clock import get_today
from chemstock.config import get_settings
from chemstock.db import get_session
from chemstock.dependencies import user_from_token
from chemstock.jalali import jalali_date, jalali_long, persian_digits, persian_number
from chemstock.models import User
from chemstock.roles import Role
from chemstock.throttle import (
    LOGIN,
    TooManyAttempts,
    clear_attempts,
    get_limits,
    reserve_attempt,
)
from chemstock.tokens import create_access_token
from chemstock.users import MAX_PASSWORD_LENGTH, authenticate_user
from chemstock.web.dashboard import EXPIRY_WINDOW_DAYS, load_dashboard

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"

COOKIE_NAME = "chemstock_session"
LOGIN_PATH = "/ui/login"
HOME_PATH = "/ui"

ROLE_LABELS = {
    Role.OWNER: "مدیر اصلی",
    Role.ADMIN: "مدیر",
    Role.MEMBER: "کاربر (ویرایش)",
    Role.VIEWER: "کاربر (فقط مشاهده)",
}
WRONG_LOGIN = "نام کاربری یا رمز عبور درست نیست."
TOO_MANY_LOGINS = "تلاش ناموفق زیاد بود. چند دقیقه‌ی دیگر دوباره امتحان کنید."

# Pages are built on the server, carry personal data and use no outside
# resources: nothing is cached, nothing is loaded from another site, and no
# other site may show them in a frame.
PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
}

templates = Jinja2Templates(directory=WEB_DIR / "templates")
templates.env.filters["fa"] = persian_digits
templates.env.filters["fa_number"] = persian_number
templates.env.filters["jalali"] = jalali_date
templates.env.filters["jalali_long"] = jalali_long

router = APIRouter(prefix="/ui", include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]
TodayDep = Annotated[date, Depends(get_today)]


class LoginRequired(Exception):
    """No valid login cookie. main.py turns it into a redirect to the login page."""


def get_web_user(request: Request, session: SessionDep) -> User:
    """The logged-in user of a web page (same checks as the API's token)."""
    token = request.cookies.get(COOKIE_NAME)
    user = user_from_token(token, session) if token else None
    if user is None:
        raise LoginRequired
    return user


WebUser = Annotated[User, Depends(get_web_user)]


def login_redirect() -> RedirectResponse:
    """Send the browser to the login page and forget any stale cookie."""
    response = RedirectResponse(LOGIN_PATH, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


def _page(
    request: Request,
    template: str,
    context: dict[str, object],
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    response = templates.TemplateResponse(
        request, template, context, status_code=status_code
    )
    response.headers.update(PAGE_HEADERS)
    return response


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, session: SessionDep) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token and user_from_token(token, session) is not None:
        return RedirectResponse(HOME_PATH, status_code=status.HTTP_303_SEE_OTHER)
    return _page(request, "login.html", {"error": None, "username": ""})


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
) -> Response:
    """Same rules as POST /auth/login: same rate limits, same vague error."""
    ip = _client_ip(request)
    try:
        reserve_attempt(session, LOGIN, username, ip, get_limits())
    except TooManyAttempts as error:
        response = _page(
            request,
            "login.html",
            {"error": TOO_MANY_LOGINS, "username": username},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
        response.headers["Retry-After"] = str(error.retry_after)
        return response

    user = None
    if username and password and len(password) <= MAX_PASSWORD_LENGTH:
        user = authenticate_user(session, username, password)
    if user is None:
        return _page(
            request,
            "login.html",
            {"error": WRONG_LOGIN, "username": username},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    clear_attempts(session, LOGIN, username, ip)

    settings = get_settings()
    lifetime = timedelta(hours=settings.web_session_hours)
    token = create_access_token(
        str(user.id),
        settings.secret_key.get_secret_value(),
        lifetime,
        version=user.token_version,
    )
    response = RedirectResponse(HOME_PATH, status_code=status.HTTP_303_SEE_OTHER)
    # HttpOnly: page scripts cannot read it. SameSite=Strict: the browser does
    # not send it with requests started by other sites, which blocks cross-site
    # form posts (CSRF). Secure is set whenever the page is served over HTTPS.
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(lifetime.total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return response


@router.post("/logout")
def logout() -> RedirectResponse:
    return login_redirect()


@router.get("", response_class=HTMLResponse)
def dashboard(
    request: Request, user: WebUser, session: SessionDep, today: TodayDep
) -> HTMLResponse:
    return _page(
        request,
        "dashboard.html",
        {
            "user": user,
            "role_label": ROLE_LABELS[Role(user.role)],
            "today": today,
            "summary": load_dashboard(session, today),
            "window_days": EXPIRY_WINDOW_DAYS,
            "active": "dashboard",
        },
    )
