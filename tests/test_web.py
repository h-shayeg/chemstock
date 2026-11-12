"""The Persian web pages: login, logout and the dashboard."""

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.orm import Session

from chemstock.clock import get_today
from chemstock.main import app
from chemstock.models import Chemical, ChemicalHazardClass, InventoryItem, User
from chemstock.security import hash_password
from chemstock.web.dashboard import load_dashboard
from chemstock.web.routes import COOKIE_NAME, TOO_MANY_LOGINS, WRONG_LOGIN

PASSWORD = "a long enough password"
TODAY = date(2026, 11, 12)  # 21 Aban 1405


@pytest.fixture
def fixed_today() -> Iterator[None]:
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


def _user(
    session: Session, username: str = "anbar", role: str = "member"
) -> User:
    user = User(username=username, hashed_password=hash_password(PASSWORD), role=role)
    session.add(user)
    session.commit()
    return user


def _login(
    client: TestClient, username: str = "anbar", password: str = PASSWORD
) -> Response:
    return client.post(
        "/ui/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def _chemical(
    session: Session,
    name: str,
    classes: tuple[str, ...] = (),
    reorder: tuple[str, str] | None = None,
) -> Chemical:
    chemical = Chemical(name=name)
    if reorder is not None:
        chemical.reorder_level = Decimal(reorder[0])
        chemical.reorder_unit = reorder[1]
    chemical.hazard_links = [ChemicalHazardClass(hazard_class=c) for c in classes]
    session.add(chemical)
    session.flush()
    return chemical


def _bottle(
    session: Session,
    chemical: Chemical,
    location: str | None,
    expiry: date | None,
    quantity: str = "1",
    unit: str = "L",
) -> InventoryItem:
    item = InventoryItem(
        chemical_id=chemical.id,
        quantity=Decimal(quantity),
        unit=unit,
        location=location,
        expiry_date=expiry,
    )
    session.add(item)
    session.flush()
    return item


def _arrange_store(session: Session) -> None:
    """Acid and base on one shelf (a conflict), plus an unreviewed chemical
    there (two "review required" pairs), and a salt that is running low."""
    acid = _chemical(session, "Hydrochloric acid", ("inorganic_acid",))
    base = _chemical(session, "Sodium hydroxide", ("inorganic_base",))
    acetone = _chemical(session, "Acetone")  # no hazard classes yet
    salt = _chemical(session, "Sodium chloride", reorder=("1", "kg"))
    _bottle(session, acid, "Shelf B2", TODAY - timedelta(days=10))  # expired
    _bottle(session, base, "Shelf B2", TODAY + timedelta(days=5))  # expiring
    _bottle(session, acetone, "Shelf B2", None)
    _bottle(session, salt, None, TODAY + timedelta(days=100), "500", "g")
    session.commit()


# ---------------------------------------------------------------- login


def test_root_sends_the_browser_to_the_web_pages(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_dashboard_needs_a_login(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/ui", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


def test_login_page_is_persian_right_to_left(anonymous_client: TestClient) -> None:
    response = anonymous_client.get("/ui/login")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="fa" dir="rtl">' in response.text
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_login_sets_a_cookie_scripts_cannot_read(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session)

    response = _login(anonymous_client)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=28800" in cookie  # 8 hours, the default web session
    assert "Secure" not in cookie  # plain HTTP inside the faculty network


def test_wrong_password_shows_a_persian_error_and_sets_no_cookie(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session)

    response = _login(anonymous_client, password="not the right password")

    assert response.status_code == 401
    assert WRONG_LOGIN in response.text
    assert "set-cookie" not in response.headers
    assert 'value="anbar"' in response.text  # the username is kept


def test_unknown_and_inactive_users_get_the_same_answer(
    anonymous_client: TestClient, session: Session
) -> None:
    user = _user(session, "former")
    user.is_active = False
    session.commit()

    unknown = _login(anonymous_client, "nobody")
    inactive = _login(anonymous_client, "former")

    assert unknown.status_code == inactive.status_code == 401
    assert WRONG_LOGIN in unknown.text
    assert WRONG_LOGIN in inactive.text


def test_an_empty_form_is_just_a_failed_login(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post("/ui/login", data={}, follow_redirects=False)

    assert response.status_code == 401
    assert WRONG_LOGIN in response.text


def test_too_many_failures_lock_the_login(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session)
    for _ in range(5):  # LOGIN_MAX_ATTEMPTS_PER_USERNAME defaults to 5
        assert _login(anonymous_client, password="wrong guess 123").status_code == 401

    response = _login(anonymous_client)  # even the right password is refused

    assert response.status_code == 429
    assert TOO_MANY_LOGINS in response.text
    assert int(response.headers["retry-after"]) > 0
    assert "set-cookie" not in response.headers


def test_the_login_page_skips_ahead_when_already_logged_in(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session)
    _login(anonymous_client)

    response = anonymous_client.get("/ui/login", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui"


# ---------------------------------------------------------- staying logged in


def test_logout_ends_the_session(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session)
    _login(anonymous_client)

    response = anonymous_client.post("/ui/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"
    assert anonymous_client.get("/ui", follow_redirects=False).status_code == 303


def test_a_password_change_ends_web_sessions_too(
    anonymous_client: TestClient, session: Session
) -> None:
    user = _user(session)
    _login(anonymous_client)
    assert anonymous_client.get("/ui").status_code == 200

    user.token_version = user.token_version + 1
    session.commit()
    response = anonymous_client.get("/ui", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"
    assert f'{COOKIE_NAME}=""' in response.headers["set-cookie"]  # forgotten


def test_a_deactivated_user_is_logged_out(
    anonymous_client: TestClient, session: Session
) -> None:
    user = _user(session)
    _login(anonymous_client)

    user.is_active = False
    session.commit()

    assert anonymous_client.get("/ui", follow_redirects=False).status_code == 303


def test_a_forged_cookie_is_not_a_login(anonymous_client: TestClient) -> None:
    anonymous_client.cookies.set(COOKIE_NAME, "not-a-real-token")

    response = anonymous_client.get("/ui", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/ui/login"


# ------------------------------------------------------------------ dashboard


def test_dashboard_numbers(session: Session) -> None:
    _arrange_store(session)

    summary = load_dashboard(session, TODAY)

    assert summary.chemical_count == 4
    assert summary.item_count == 4
    assert summary.expired_count == 1
    assert summary.expiring_soon_count == 1
    assert summary.low_stock_count == 1
    assert summary.conflict_count == 1
    assert summary.review_count == 2
    assert [b.chemical_name for b in summary.soonest_expiring] == [
        "Hydrochloric acid",
        "Sodium hydroxide",
    ]
    assert [b.days_left for b in summary.soonest_expiring] == [-10, 5]
    assert summary.top_conflicts[0].severity == 1  # the conflict comes first


def test_an_empty_store_gives_zeros(session: Session) -> None:
    summary = load_dashboard(session, TODAY)

    assert summary.item_count == summary.conflict_count == summary.review_count == 0
    assert summary.soonest_expiring == []
    assert summary.top_conflicts == []


@pytest.mark.usefixtures("fixed_today")
def test_dashboard_page(anonymous_client: TestClient, session: Session) -> None:
    _user(session)
    _arrange_store(session)
    _login(anonymous_client)

    response = anonymous_client.get("/ui")

    assert response.status_code == 200
    page = response.text
    assert "anbar" in page
    assert "کاربر (ویرایش)" in page  # the member role in Persian
    assert "۲۱ آبان ۱۴۰۵" in page  # today, in the Persian calendar
    assert "۱۴۰۵/۰۸/۱۱" in page  # the acid expired ten days ago
    assert "۱۰ روز گذشته" in page
    assert "۵ روز مانده" in page
    assert "خطر واکنش" in page
    assert "نیاز به بررسی" in page
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.usefixtures("fixed_today")
def test_a_viewer_may_see_the_dashboard(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session, "guest", role="viewer")
    _login(anonymous_client, "guest")

    response = anonymous_client.get("/ui")

    assert response.status_code == 200
    assert "کاربر (فقط مشاهده)" in response.text


@pytest.mark.usefixtures("fixed_today")
def test_names_are_shown_as_text_never_as_html(
    anonymous_client: TestClient, session: Session
) -> None:
    _user(session)
    chemical = _chemical(session, "<script>alert(1)</script>")
    _bottle(session, chemical, "<b>shelf</b>", TODAY)
    session.commit()
    _login(anonymous_client)

    page = anonymous_client.get("/ui").text

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "&lt;b&gt;shelf&lt;/b&gt;" in page


# ------------------------------------------------------- files and the API


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/ui/static/app.css", "text/css"),
        ("/ui/static/fonts/Vazirmatn-UI-Regular.woff2", "font/woff2"),
        ("/ui/static/fonts/Vazirmatn-UI-Bold.woff2", "font/woff2"),
        ("/ui/static/fonts/OFL.txt", "text/plain"),
    ],
)
def test_style_sheet_and_font_are_served_by_the_app(
    anonymous_client: TestClient, path: str, content_type: str
) -> None:
    response = anonymous_client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)


def test_web_pages_stay_out_of_the_api_documentation(
    anonymous_client: TestClient,
) -> None:
    paths = anonymous_client.get("/openapi.json").json()["paths"]

    assert not [path for path in paths if path == "/" or path.startswith("/ui")]
