from decimal import Decimal

import pytest
from fastapi.testclient import TestClient


def _new_chemical(client: TestClient, name: str = "Acetone") -> int:
    response = client.post("/chemicals", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _bottle_payload(chemical_id: int, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "chemical_id": chemical_id,
        "quantity": "2.5",
        "unit": "L",
        "location": "Shelf B2",
        "expiry_date": "2027-03-01",
    }
    payload.update(overrides)
    return payload


def _new_item(
    client: TestClient, chemical_id: int, **overrides: object
) -> dict[str, object]:
    payload = _bottle_payload(chemical_id, **overrides)
    response = client.post("/inventory-items", json=payload)
    assert response.status_code == 201
    return response.json()


def test_create_inventory_item_returns_created_resource(client: TestClient) -> None:
    chemical_id = _new_chemical(client)

    response = client.post("/inventory-items", json=_bottle_payload(chemical_id))

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["chemical_id"] == chemical_id
    assert Decimal(str(body["quantity"])) == Decimal("2.5")
    assert body["unit"] == "L"
    assert body["location"] == "Shelf B2"
    assert body["expiry_date"] == "2027-03-01"
    assert "created_at" in body


def test_create_without_optional_fields(client: TestClient) -> None:
    chemical_id = _new_chemical(client)
    payload = {"chemical_id": chemical_id, "quantity": "100", "unit": "g"}

    response = client.post("/inventory-items", json=payload)

    assert response.status_code == 201
    assert response.json()["location"] is None
    assert response.json()["expiry_date"] is None


def test_create_for_unknown_chemical_returns_422(client: TestClient) -> None:
    response = client.post("/inventory-items", json=_bottle_payload(999))

    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": "-1"},
        {"unit": "gallon"},
        {"quantity": "1.2345"},
        {"unit": None},
    ],
    ids=["negative-quantity", "unknown-unit", "too-many-decimals", "null-unit"],
)
def test_create_rejects_invalid_values(
    client: TestClient, overrides: dict[str, object]
) -> None:
    chemical_id = _new_chemical(client)

    response = client.post(
        "/inventory-items", json=_bottle_payload(chemical_id, **overrides)
    )

    assert response.status_code == 422


def test_get_inventory_item_by_id(client: TestClient) -> None:
    item = _new_item(client, _new_chemical(client))

    response = client.get(f"/inventory-items/{item['id']}")

    assert response.status_code == 200
    assert response.json() == item


def test_get_unknown_inventory_item_returns_404(client: TestClient) -> None:
    assert client.get("/inventory-items/999").status_code == 404


def test_list_can_filter_by_chemical(client: TestClient) -> None:
    first = _new_chemical(client, "Acetone")
    second = _new_chemical(client, "Ethanol")
    _new_item(client, first)
    _new_item(client, first, location="Shelf C1")
    _new_item(client, second)

    everything = client.get("/inventory-items").json()
    only_first = client.get("/inventory-items", params={"chemical_id": first}).json()

    assert len(everything) == 3
    assert [item["chemical_id"] for item in only_first] == [first, first]


def test_patch_changes_only_given_fields(client: TestClient) -> None:
    item = _new_item(client, _new_chemical(client))

    response = client.patch(f"/inventory-items/{item['id']}", json={"quantity": "0.5"})

    body = response.json()
    assert response.status_code == 200
    assert Decimal(str(body["quantity"])) == Decimal("0.5")
    assert body["unit"] == "L"
    assert body["location"] == "Shelf B2"


def test_patch_can_clear_optional_fields(client: TestClient) -> None:
    item = _new_item(client, _new_chemical(client))

    response = client.patch(
        f"/inventory-items/{item['id']}",
        json={"location": None, "expiry_date": None},
    )

    assert response.status_code == 200
    assert response.json()["location"] is None
    assert response.json()["expiry_date"] is None


@pytest.mark.parametrize(
    "payload",
    [{"quantity": None}, {"unit": None}, {"unit": "gallon"}, {"chemical_id": 2}],
    ids=["null-quantity", "null-unit", "unknown-unit", "chemical-cannot-change"],
)
def test_patch_rejects_invalid_values(
    client: TestClient, payload: dict[str, object]
) -> None:
    item = _new_item(client, _new_chemical(client))

    response = client.patch(f"/inventory-items/{item['id']}", json=payload)

    assert response.status_code == 422


def test_patch_unknown_inventory_item_returns_404(client: TestClient) -> None:
    response = client.patch("/inventory-items/999", json={"quantity": "1"})

    assert response.status_code == 404


def test_delete_removes_inventory_item(client: TestClient) -> None:
    item = _new_item(client, _new_chemical(client))

    assert client.delete(f"/inventory-items/{item['id']}").status_code == 204
    assert client.get(f"/inventory-items/{item['id']}").status_code == 404


def test_delete_unknown_inventory_item_returns_404(client: TestClient) -> None:
    assert client.delete("/inventory-items/999").status_code == 404


def test_chemical_can_be_deleted_once_its_items_are_gone(client: TestClient) -> None:
    chemical_id = _new_chemical(client)
    item = _new_item(client, chemical_id)

    assert client.delete(f"/chemicals/{chemical_id}").status_code == 409
    assert client.delete(f"/inventory-items/{item['id']}").status_code == 204
    assert client.delete(f"/chemicals/{chemical_id}").status_code == 204
