from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from chemstock.clock import get_today
from chemstock.main import app

TODAY = date(2026, 10, 25)


@pytest.fixture(autouse=True)
def _fixed_today() -> Iterator[None]:
    """Freeze "today" so these tests give the same answer on any day."""
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


def _chemical(client: TestClient) -> int:
    response = client.post("/chemicals", json={"name": "Acetone"})
    assert response.status_code == 201
    return response.json()["id"]


def _bottle(client: TestClient, chemical_id: int, days_from_today: int | None) -> int:
    payload: dict[str, object] = {
        "chemical_id": chemical_id,
        "quantity": "1",
        "unit": "L",
    }
    if days_from_today is not None:
        payload["expiry_date"] = (TODAY + timedelta(days=days_from_today)).isoformat()
    response = client.post("/inventory-items", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _expiring(client: TestClient, **params: int) -> list[dict[str, object]]:
    response = client.get("/inventory-items/expiring", params=params)
    assert response.status_code == 200
    return response.json()


def test_nothing_expiring_returns_empty_list(client: TestClient) -> None:
    # Also proves "/expiring" is not swallowed by "/{item_id}".
    assert _expiring(client) == []


def test_item_inside_window_reports_days_left(client: TestClient) -> None:
    chemical_id = _chemical(client)
    item_id = _bottle(client, chemical_id, 10)

    items = _expiring(client)

    assert [item["id"] for item in items] == [item_id]
    assert items[0]["days_until_expiry"] == 10
    assert items[0]["chemical_id"] == chemical_id


def test_default_window_is_30_days_and_inclusive(client: TestClient) -> None:
    chemical_id = _chemical(client)
    on_boundary = _bottle(client, chemical_id, 30)
    _bottle(client, chemical_id, 31)

    assert [item["id"] for item in _expiring(client)] == [on_boundary]


def test_days_parameter_changes_the_window(client: TestClient) -> None:
    chemical_id = _chemical(client)
    soon = _bottle(client, chemical_id, 5)
    later = _bottle(client, chemical_id, 60)

    assert [item["id"] for item in _expiring(client, days=7)] == [soon]
    assert [item["id"] for item in _expiring(client, days=90)] == [soon, later]


def test_expired_item_is_listed_with_negative_days(client: TestClient) -> None:
    item_id = _bottle(client, _chemical(client), -5)

    items = _expiring(client)

    assert [item["id"] for item in items] == [item_id]
    assert items[0]["days_until_expiry"] == -5


def test_item_expiring_today_is_listed_even_with_zero_days(
    client: TestClient,
) -> None:
    item_id = _bottle(client, _chemical(client), 0)

    items = _expiring(client, days=0)

    assert [item["id"] for item in items] == [item_id]
    assert items[0]["days_until_expiry"] == 0


def test_items_without_expiry_date_are_never_listed(client: TestClient) -> None:
    _bottle(client, _chemical(client), None)

    assert _expiring(client) == []
    assert _expiring(client, days=3650) == []


def test_most_urgent_items_come_first(client: TestClient) -> None:
    chemical_id = _chemical(client)
    later = _bottle(client, chemical_id, 20)
    expired = _bottle(client, chemical_id, -3)
    soon = _bottle(client, chemical_id, 4)

    assert [item["id"] for item in _expiring(client)] == [expired, soon, later]


def test_limit_and_offset_page_through_results(client: TestClient) -> None:
    chemical_id = _chemical(client)
    ids = [_bottle(client, chemical_id, days) for days in (1, 2, 3)]

    first_page = _expiring(client, limit=2)
    second_page = _expiring(client, limit=2, offset=2)

    assert [item["id"] for item in first_page] == ids[:2]
    assert [item["id"] for item in second_page] == ids[2:]


@pytest.mark.parametrize("days", [-1, 3651])
def test_days_out_of_range_is_rejected(client: TestClient, days: int) -> None:
    response = client.get("/inventory-items/expiring", params={"days": days})

    assert response.status_code == 422
