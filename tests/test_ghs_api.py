import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chemstock.clock import get_now
from chemstock.config import get_settings
from chemstock.main import app
from chemstock.pubchem import PubChemClient, get_pubchem_client

DATA = Path(__file__).parent / "data"
BASE = "https://pubchem.example/rest"
ACETONE_CAS = "67-64-1"
START = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)

ACETONE_ANSWERS = {
    f"{BASE}/pug/compound/name/67-64-1/cids/JSON": (
        200,
        json.dumps({"IdentifierList": {"CID": [180]}}).encode(),
    ),
    f"{BASE}/pug_view/data/compound/180/JSON?heading=GHS+Classification": (
        200,
        (DATA / "pubchem_acetone_ghs.json").read_bytes(),
    ),
}


class FakePubChem:
    """A PubChem that can be switched off, and counts the requests it gets."""

    def __init__(self) -> None:
        self.online = True
        self.requests = 0

    def __call__(self, url: str) -> tuple[int, bytes]:
        if not self.online:
            raise OSError("network is down")
        self.requests += 1
        return ACETONE_ANSWERS.get(url, (404, b'{"Fault": {}}'))


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def pubchem() -> Iterator[FakePubChem]:
    fake = FakePubChem()
    app.dependency_overrides[get_pubchem_client] = lambda: PubChemClient(
        fake, base_url=BASE
    )
    yield fake  # conftest puts the offline client back afterwards


@pytest.fixture
def clock() -> Iterator[Clock]:
    fake = Clock()
    app.dependency_overrides[get_now] = fake
    yield fake
    app.dependency_overrides.pop(get_now, None)


def _chemical(client: TestClient, **fields: object) -> int:
    response = client.post("/chemicals", json={"name": "Acetone", **fields})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _ghs(client: TestClient, chemical_id: int) -> dict[str, object]:
    response = client.get(f"/chemicals/{chemical_id}/ghs")
    assert response.status_code == 200, response.text
    return response.json()


def test_ghs_data_of_a_classified_chemical(
    client: TestClient, pubchem: FakePubChem, clock: Clock
) -> None:
    chemical_id = _chemical(client, cas_number=ACETONE_CAS)

    body = _ghs(client, chemical_id)

    assert body["chemical_id"] == chemical_id
    assert body["cas_number"] == ACETONE_CAS
    assert body["status"] == "classified"
    assert body["pubchem_cid"] == 180
    assert body["pubchem_url"] == "https://pubchem.ncbi.nlm.nih.gov/compound/180"
    assert body["signal_word"] == "Danger"
    assert body["pictograms"] == [
        {"code": "GHS02", "name": "Flammable"},
        {"code": "GHS07", "name": "Irritant"},
    ]
    assert body["hazard_statements"][0] == {
        "code": "H225",
        "statement": "Highly Flammable liquid and vapor",
    }
    assert body["suggested_hazard_classes"] == ["flammable"]
    assert len(body["sources"]) == 2
    assert body["fetched_at"] == "2026-11-02T12:00:00Z"
    assert body["stale"] is False


def test_suggestions_are_never_applied(
    client: TestClient, pubchem: FakePubChem, clock: Clock
) -> None:
    chemical_id = _chemical(client, cas_number=ACETONE_CAS)

    _ghs(client, chemical_id)

    chemical = client.get(f"/chemicals/{chemical_id}").json()
    assert chemical["hazard_classes"] == []


def test_the_answer_is_cached(
    client: TestClient, pubchem: FakePubChem, clock: Clock
) -> None:
    chemical_id = _chemical(client, cas_number=ACETONE_CAS)
    first = _ghs(client, chemical_id)

    clock.now = START + timedelta(days=29)
    second = _ghs(client, chemical_id)

    assert pubchem.requests == 2  # CID lookup + GHS record, once
    assert second == first


def test_an_old_answer_is_refreshed(
    client: TestClient, pubchem: FakePubChem, clock: Clock
) -> None:
    chemical_id = _chemical(client, cas_number=ACETONE_CAS)
    _ghs(client, chemical_id)

    clock.now = START + timedelta(days=30)
    body = _ghs(client, chemical_id)

    assert pubchem.requests == 4
    assert body["fetched_at"] == "2026-12-02T12:00:00Z"


def test_the_cache_period_is_configurable(
    client: TestClient,
    pubchem: FakePubChem,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PUBCHEM_CACHE_DAYS", "1")
    get_settings.cache_clear()
    try:
        chemical_id = _chemical(client, cas_number=ACETONE_CAS)
        _ghs(client, chemical_id)
        clock.now = START + timedelta(days=1)
        _ghs(client, chemical_id)
    finally:
        monkeypatch.delenv("PUBCHEM_CACHE_DAYS")
        get_settings.cache_clear()

    assert pubchem.requests == 4


def test_an_old_answer_is_shown_when_pubchem_is_down(
    client: TestClient, pubchem: FakePubChem, clock: Clock
) -> None:
    chemical_id = _chemical(client, cas_number=ACETONE_CAS)
    _ghs(client, chemical_id)

    clock.now = START + timedelta(days=90)
    pubchem.online = False
    body = _ghs(client, chemical_id)

    assert body["stale"] is True
    assert body["status"] == "classified"
    assert body["fetched_at"] == "2026-11-02T12:00:00Z"


def test_pubchem_down_and_nothing_cached_returns_503(client: TestClient) -> None:
    # Without the "pubchem" fixture the tests use an offline PubChem (conftest).
    chemical_id = _chemical(client, cas_number=ACETONE_CAS)

    response = client.get(f"/chemicals/{chemical_id}/ghs")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"


def test_an_unknown_cas_number_is_reported_and_cached(
    client: TestClient, pubchem: FakePubChem, clock: Clock
) -> None:
    chemical_id = _chemical(client, name="Formaldehyde", cas_number="50-00-0")

    first = _ghs(client, chemical_id)
    second = _ghs(client, chemical_id)

    assert first["status"] == "not_found"
    assert first["pubchem_cid"] is None
    assert first["pubchem_url"] is None
    assert first["hazard_statements"] == []
    assert first["suggested_hazard_classes"] == []
    assert second == first
    assert pubchem.requests == 1


def test_a_chemical_without_cas_number_returns_409(
    client: TestClient, pubchem: FakePubChem
) -> None:
    chemical_id = _chemical(client)  # no CAS number

    response = client.get(f"/chemicals/{chemical_id}/ghs")

    assert response.status_code == 409
    assert pubchem.requests == 0


def test_an_unknown_chemical_returns_404(
    client: TestClient, pubchem: FakePubChem
) -> None:
    assert client.get("/chemicals/999/ghs").status_code == 404
    assert pubchem.requests == 0
