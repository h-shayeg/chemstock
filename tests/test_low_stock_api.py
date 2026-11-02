import pytest
from fastapi.testclient import TestClient


def _chemical(client: TestClient, name: str, **fields: object) -> int:
    response = client.post("/chemicals", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _bottle(client: TestClient, chemical_id: int, quantity: str, unit: str) -> None:
    payload = {"chemical_id": chemical_id, "quantity": quantity, "unit": unit}
    response = client.post("/inventory-items", json=payload)
    assert response.status_code == 201, response.text


def _low_stock(client: TestClient, **params: int) -> list[dict[str, object]]:
    response = client.get("/chemicals/low-stock", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- the reorder level on a chemical ---------------------------------------


def test_a_new_chemical_has_no_reorder_level(client: TestClient) -> None:
    response = client.post("/chemicals", json={"name": "Water"})

    body = response.json()
    assert body["reorder_level"] is None
    assert body["reorder_unit"] is None


def test_a_chemical_can_be_created_with_a_reorder_level(client: TestClient) -> None:
    payload = {"name": "Acetone", "reorder_level": "1.5", "reorder_unit": "L"}

    body = client.post("/chemicals", json=payload).json()

    assert body["reorder_level"] == "1.500"
    assert body["reorder_unit"] == "L"


@pytest.mark.parametrize(
    "fields",
    [
        {"reorder_level": "1"},  # no unit
        {"reorder_unit": "L"},  # no level
        {"reorder_level": "-1", "reorder_unit": "L"},
        {"reorder_level": "1", "reorder_unit": "gallon"},
        {"reorder_level": "0.0001", "reorder_unit": "L"},  # more than 3 places
    ],
)
def test_invalid_reorder_levels_are_rejected(
    client: TestClient, fields: dict[str, str]
) -> None:
    response = client.post("/chemicals", json={"name": "Acetone", **fields})

    assert response.status_code == 422


def test_patch_sets_and_removes_the_reorder_level(client: TestClient) -> None:
    chemical_id = _chemical(client, "Acetone")

    set_level = client.patch(
        f"/chemicals/{chemical_id}",
        json={"reorder_level": "500", "reorder_unit": "mL"},
    )
    removed = client.patch(
        f"/chemicals/{chemical_id}",
        json={"reorder_level": None, "reorder_unit": None},
    )

    assert set_level.status_code == 200
    assert set_level.json()["reorder_level"] == "500.000"
    assert removed.status_code == 200
    assert removed.json()["reorder_level"] is None
    assert removed.json()["reorder_unit"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"reorder_level": "2"},  # the two fields must be sent together
        {"reorder_unit": "g"},
        {"reorder_level": None, "reorder_unit": "L"},
        {"reorder_level": "2", "reorder_unit": None},
    ],
)
def test_patch_rejects_half_a_reorder_level(
    client: TestClient, fields: dict[str, str | None]
) -> None:
    chemical_id = _chemical(client, "Acetone", reorder_level="1", reorder_unit="L")

    response = client.patch(f"/chemicals/{chemical_id}", json=fields)

    assert response.status_code == 422
    unchanged = client.get(f"/chemicals/{chemical_id}").json()
    assert (unchanged["reorder_level"], unchanged["reorder_unit"]) == ("1.000", "L")


def test_patch_of_other_fields_keeps_the_reorder_level(client: TestClient) -> None:
    chemical_id = _chemical(client, "Acetone", reorder_level="1", reorder_unit="L")

    body = client.patch(f"/chemicals/{chemical_id}", json={"name": "Propanone"}).json()

    assert (body["reorder_level"], body["reorder_unit"]) == ("1.000", "L")


# --- the low-stock report ----------------------------------------------------


def test_nothing_is_low_at_start(client: TestClient) -> None:
    # Also proves "/low-stock" is not swallowed by "/{chemical_id}".
    assert _low_stock(client) == []


def test_chemicals_without_a_reorder_level_are_never_reported(
    client: TestClient,
) -> None:
    _chemical(client, "Water")  # no level, no bottles

    assert _low_stock(client) == []


def test_a_chemical_below_its_level_is_reported(client: TestClient) -> None:
    chemical_id = _chemical(client, "Acetone", reorder_level="1", reorder_unit="L")
    _bottle(client, chemical_id, "300", "mL")
    _bottle(client, chemical_id, "0.2", "L")

    assert _low_stock(client) == [
        {
            "chemical_id": chemical_id,
            "chemical_name": "Acetone",
            "reorder_level": "1.000",
            "unit": "L",
            "total_quantity": "0.500",
            "item_count": 2,
            "uncounted_item_count": 0,
        }
    ]


def test_a_chemical_with_enough_stock_is_not_reported(client: TestClient) -> None:
    chemical_id = _chemical(client, "Acetone", reorder_level="1", reorder_unit="L")
    _bottle(client, chemical_id, "600", "mL")
    _bottle(client, chemical_id, "0.5", "L")

    assert _low_stock(client) == []


def test_a_chemical_with_no_bottles_has_run_out(client: TestClient) -> None:
    chemical_id = _chemical(
        client, "Sodium chloride", reorder_level="100", reorder_unit="g"
    )

    [report] = _low_stock(client)

    assert report["chemical_id"] == chemical_id
    assert report["total_quantity"] == "0.000"
    assert report["item_count"] == 0


def test_bottles_of_the_other_kind_are_counted_separately(
    client: TestClient,
) -> None:
    chemical_id = _chemical(client, "Ethanol", reorder_level="1", reorder_unit="kg")
    _bottle(client, chemical_id, "200", "g")
    _bottle(client, chemical_id, "2.5", "L")  # a volume: needs the density

    [report] = _low_stock(client)

    assert report["total_quantity"] == "0.200"
    assert (report["item_count"], report["uncounted_item_count"]) == (1, 1)


def test_using_up_a_bottle_brings_a_chemical_into_the_report(
    client: TestClient,
) -> None:
    chemical_id = _chemical(client, "Acetone", reorder_level="1", reorder_unit="L")
    response = client.post(
        "/inventory-items",
        json={"chemical_id": chemical_id, "quantity": "2", "unit": "L"},
    )
    item_id = response.json()["id"]
    assert _low_stock(client) == []

    client.patch(f"/inventory-items/{item_id}", json={"quantity": "0.25"})

    assert [r["chemical_id"] for r in _low_stock(client)] == [chemical_id]


def test_emptiest_chemicals_come_first(client: TestClient) -> None:
    half = _chemical(client, "Acetone", reorder_level="1", reorder_unit="L")
    _bottle(client, half, "0.5", "L")
    empty = _chemical(client, "Ethanol", reorder_level="1", reorder_unit="L")
    tenth = _chemical(client, "Toluene", reorder_level="1", reorder_unit="L")
    _bottle(client, tenth, "100", "mL")

    ids = [report["chemical_id"] for report in _low_stock(client)]

    assert ids == [empty, tenth, half]


def test_limit_and_offset_page_through_results(client: TestClient) -> None:
    ids = [
        _chemical(client, name, reorder_level="1", reorder_unit="g")
        for name in ("A", "B", "C")
    ]

    first_page = _low_stock(client, limit=2)
    second_page = _low_stock(client, limit=2, offset=2)

    assert [r["chemical_id"] for r in first_page] == ids[:2]
    assert [r["chemical_id"] for r in second_page] == ids[2:]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}])
def test_paging_out_of_range_is_rejected(
    client: TestClient, params: dict[str, int]
) -> None:
    response = client.get("/chemicals/low-stock", params=params)

    assert response.status_code == 422
