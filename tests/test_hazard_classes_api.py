import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from chemstock.compatibility import HAZARD_CLASS_DESCRIPTIONS, HazardClass
from chemstock.models import ChemicalHazardClass


def _chemical(client: TestClient, name: str = "Acetone") -> int:
    response = client.post("/chemicals", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _put(client: TestClient, chemical_id: int, classes: object) -> Response:
    return client.put(
        f"/chemicals/{chemical_id}/hazard-classes", json={"hazard_classes": classes}
    )


def test_list_hazard_classes_describes_every_class(client: TestClient) -> None:
    response = client.get("/hazard-classes")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == [hazard.value for hazard in HazardClass]
    assert body[0]["description"] == HAZARD_CLASS_DESCRIPTIONS[HazardClass.FLAMMABLE]
    assert all(item["description"] for item in body)


def test_new_chemical_has_no_hazard_classes(client: TestClient) -> None:
    created = client.post("/chemicals", json={"name": "Water"}).json()

    assert created["hazard_classes"] == []


def test_put_sets_hazard_classes_sorted(client: TestClient) -> None:
    chemical_id = _chemical(client)

    response = _put(client, chemical_id, ["organic_acid", "flammable"])

    assert response.status_code == 200
    assert response.json()["hazard_classes"] == ["flammable", "organic_acid"]
    stored = client.get(f"/chemicals/{chemical_id}").json()
    assert stored["hazard_classes"] == ["flammable", "organic_acid"]


def test_put_replaces_previous_classes(client: TestClient) -> None:
    chemical_id = _chemical(client)
    _put(client, chemical_id, ["flammable", "oxidizer"])

    response = _put(client, chemical_id, ["oxidizer", "water_reactive"])

    assert response.json()["hazard_classes"] == ["oxidizer", "water_reactive"]


def test_put_empty_list_clears_classes(client: TestClient) -> None:
    chemical_id = _chemical(client)
    _put(client, chemical_id, ["flammable"])

    response = _put(client, chemical_id, [])

    assert response.status_code == 200
    assert response.json()["hazard_classes"] == []


def test_put_ignores_duplicates(client: TestClient) -> None:
    chemical_id = _chemical(client)

    response = _put(client, chemical_id, ["flammable", "flammable"])

    assert response.json()["hazard_classes"] == ["flammable"]


def test_unclassified_is_accepted_on_its_own(client: TestClient) -> None:
    response = _put(client, _chemical(client), ["unclassified"])

    assert response.status_code == 200
    assert response.json()["hazard_classes"] == ["unclassified"]


@pytest.mark.parametrize(
    "body",
    [
        {"hazard_classes": ["unclassified", "flammable"]},
        {"hazard_classes": ["not_a_class"]},
        {"hazard_classes": "flammable"},
        {"hazard_classes": [None]},
        {},
    ],
    ids=["unclassified-mixed", "unknown-class", "not-a-list", "null-item", "missing"],
)
def test_put_rejects_invalid_bodies(client: TestClient, body: object) -> None:
    chemical_id = _chemical(client)
    _put(client, chemical_id, ["flammable"])

    response = client.put(f"/chemicals/{chemical_id}/hazard-classes", json=body)

    assert response.status_code == 422
    # A rejected request must not change anything.
    stored = client.get(f"/chemicals/{chemical_id}").json()
    assert stored["hazard_classes"] == ["flammable"]


def test_put_for_unknown_chemical_returns_404(client: TestClient) -> None:
    assert _put(client, 999, ["flammable"]).status_code == 404


def test_put_rejects_out_of_range_id(client: TestClient) -> None:
    assert _put(client, 0, ["flammable"]).status_code == 422


def test_list_includes_hazard_classes_of_each_chemical(client: TestClient) -> None:
    acetone = _chemical(client, "Acetone")
    _chemical(client, "Water")
    _put(client, acetone, ["flammable"])

    body = client.get("/chemicals").json()

    assert {item["name"]: item["hazard_classes"] for item in body} == {
        "Acetone": ["flammable"],
        "Water": [],
    }


def test_deleting_a_chemical_removes_its_hazard_classes(
    client: TestClient, session: Session
) -> None:
    chemical_id = _chemical(client)
    _put(client, chemical_id, ["flammable", "oxidizer"])

    assert client.delete(f"/chemicals/{chemical_id}").status_code == 204

    remaining = session.scalar(select(func.count()).select_from(ChemicalHazardClass))
    assert remaining == 0


def test_database_rejects_unknown_hazard_class(
    client: TestClient, session: Session
) -> None:
    chemical_id = _chemical(client)
    session.add(ChemicalHazardClass(chemical_id=chemical_id, hazard_class="nope"))

    with pytest.raises(IntegrityError):
        session.commit()
