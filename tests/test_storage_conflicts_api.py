import pytest
from fastapi.testclient import TestClient


def _chemical(
    client: TestClient, name: str, classes: list[str] | None = None
) -> int:
    response = client.post("/chemicals", json={"name": name})
    assert response.status_code == 201
    chemical_id = response.json()["id"]
    if classes is not None:
        update = client.put(
            f"/chemicals/{chemical_id}/hazard-classes",
            json={"hazard_classes": classes},
        )
        assert update.status_code == 200
    return chemical_id


def _bottle(client: TestClient, chemical_id: int, location: str | None) -> int:
    payload: dict[str, object] = {
        "chemical_id": chemical_id,
        "quantity": "1",
        "unit": "L",
    }
    if location is not None:
        payload["location"] = location
    response = client.post("/inventory-items", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def _acid_and_base(client: TestClient) -> tuple[int, int]:
    acid = _chemical(client, "Hydrochloric acid", ["inorganic_acid"])
    base = _chemical(client, "Sodium hydroxide", ["inorganic_base"])
    return acid, base


def test_no_bottles_means_no_conflicts(client: TestClient) -> None:
    response = client.get("/storage-conflicts")

    assert response.status_code == 200
    assert response.json() == []


def test_acid_and_base_on_the_same_shelf(client: TestClient) -> None:
    acid, base = _acid_and_base(client)
    acid_bottle = _bottle(client, acid, "Shelf B2")
    base_bottle = _bottle(client, base, "Shelf B2")

    response = client.get("/storage-conflicts")

    assert response.status_code == 200
    [conflict] = response.json()
    assert conflict["status"] == "conflict"
    assert conflict["severity"] == 1
    assert conflict["location"] == "Shelf B2"
    assert conflict["items"] == [
        {
            "inventory_item_id": acid_bottle,
            "chemical_id": acid,
            "chemical_name": "Hydrochloric acid",
            "hazard_classes": ["inorganic_acid"],
        },
        {
            "inventory_item_id": base_bottle,
            "chemical_id": base,
            "chemical_name": "Sodium hydroxide",
            "hazard_classes": ["inorganic_base"],
        },
    ]
    assert [reason["rule"] for reason in conflict["reasons"]] == ["acid-base"]


def test_same_shelf_written_differently(client: TestClient) -> None:
    acid, base = _acid_and_base(client)
    _bottle(client, acid, "Shelf B2")
    _bottle(client, base, "shelf  b2")

    [conflict] = client.get("/storage-conflicts").json()

    assert conflict["location"] == "Shelf B2"


def test_different_shelves_do_not_conflict(client: TestClient) -> None:
    acid, base = _acid_and_base(client)
    _bottle(client, acid, "Shelf A")
    _bottle(client, base, "Shelf B")

    assert client.get("/storage-conflicts").json() == []


def test_unclassified_chemicals_require_review(client: TestClient) -> None:
    first = _chemical(client, "Mystery powder")
    second = _chemical(client, "Mystery liquid")
    _bottle(client, first, "Shelf A")
    _bottle(client, second, "Shelf A")

    [conflict] = client.get("/storage-conflicts").json()

    assert conflict["status"] == "review_required"
    assert conflict["severity"] is None
    assert conflict["reasons"] == []


@pytest.mark.parametrize("location", [None, "   "])
def test_bottles_without_location_are_ignored(
    client: TestClient, location: str | None
) -> None:
    acid, base = _acid_and_base(client)
    _bottle(client, acid, location)
    _bottle(client, base, location)

    assert client.get("/storage-conflicts").json() == []


def test_status_filter(client: TestClient) -> None:
    acid, base = _acid_and_base(client)
    _bottle(client, acid, "Shelf A")
    _bottle(client, base, "Shelf A")
    _bottle(client, _chemical(client, "Mystery powder"), "Shelf B")
    _bottle(client, _chemical(client, "Mystery liquid"), "Shelf B")

    everything = client.get("/storage-conflicts").json()
    conflicts = client.get("/storage-conflicts", params={"status": "conflict"}).json()
    reviews = client.get(
        "/storage-conflicts", params={"status": "review_required"}
    ).json()

    assert [item["status"] for item in everything] == ["conflict", "review_required"]
    assert [item["status"] for item in conflicts] == ["conflict"]
    assert [item["status"] for item in reviews] == ["review_required"]


@pytest.mark.parametrize("status", ["compatible", "no_conflict"])
def test_invalid_status_is_rejected(client: TestClient, status: str) -> None:
    response = client.get("/storage-conflicts", params={"status": status})

    assert response.status_code == 422


def test_pagination(client: TestClient) -> None:
    acid, base = _acid_and_base(client)
    for shelf in ("Shelf A", "Shelf B"):
        _bottle(client, acid, shelf)
        _bottle(client, base, shelf)

    first = client.get("/storage-conflicts", params={"limit": 1}).json()
    second = client.get("/storage-conflicts", params={"limit": 1, "offset": 1}).json()
    beyond = client.get("/storage-conflicts", params={"offset": 2}).json()

    assert [item["location"] for item in first] == ["Shelf A"]
    assert [item["location"] for item in second] == ["Shelf B"]
    assert beyond == []


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_out_of_range_is_rejected(client: TestClient, limit: int) -> None:
    response = client.get("/storage-conflicts", params={"limit": limit})

    assert response.status_code == 422


def test_moving_a_bottle_resolves_the_conflict(client: TestClient) -> None:
    acid, base = _acid_and_base(client)
    _bottle(client, acid, "Shelf B2")
    base_bottle = _bottle(client, base, "Shelf B2")
    assert len(client.get("/storage-conflicts").json()) == 1

    moved = client.patch(
        f"/inventory-items/{base_bottle}", json={"location": "Shelf C"}
    )

    assert moved.status_code == 200
    assert client.get("/storage-conflicts").json() == []
