import pytest
from fastapi.testclient import TestClient

WATER = {"name": "Water", "cas_number": "7732-18-5", "formula": "H2O"}


def test_create_chemical_returns_created_resource(client: TestClient) -> None:
    response = client.post("/chemicals", json=WATER)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["name"] == "Water"
    assert body["cas_number"] == "7732-18-5"
    assert body["formula"] == "H2O"
    assert "created_at" in body


def test_chemicals_without_cas_number_can_coexist(client: TestClient) -> None:
    first = client.post("/chemicals", json={"name": "Buffer A"})
    second = client.post("/chemicals", json={"name": "Buffer B"})

    assert first.status_code == 201
    assert second.status_code == 201


def test_duplicate_cas_number_returns_conflict(client: TestClient) -> None:
    assert client.post("/chemicals", json=WATER).status_code == 201

    response = client.post("/chemicals", json={**WATER, "name": "Aqua"})

    assert response.status_code == 409
    # The failed insert must not break later requests.
    assert len(client.get("/chemicals").json()) == 1


def test_invalid_cas_number_is_rejected(client: TestClient) -> None:
    payload = {"name": "Water", "cas_number": "7732-18-4"}  # wrong check digit

    response = client.post("/chemicals", json=payload)

    assert response.status_code == 422


def test_missing_name_is_rejected(client: TestClient) -> None:
    response = client.post("/chemicals", json={"cas_number": "7732-18-5"})

    assert response.status_code == 422


def test_list_is_empty_at_start(client: TestClient) -> None:
    response = client.get("/chemicals")

    assert response.status_code == 200
    assert response.json() == []


def test_list_supports_pagination(client: TestClient) -> None:
    for name in ("A", "B", "C"):
        client.post("/chemicals", json={"name": name})

    first_page = client.get("/chemicals", params={"limit": 2}).json()
    second_page = client.get("/chemicals", params={"limit": 2, "offset": 2}).json()

    assert [c["name"] for c in first_page] == ["A", "B"]
    assert [c["name"] for c in second_page] == ["C"]


@pytest.mark.parametrize("limit", [0, 201])
def test_list_rejects_out_of_range_limit(client: TestClient, limit: int) -> None:
    response = client.get("/chemicals", params={"limit": limit})

    assert response.status_code == 422
