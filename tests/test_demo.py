from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chemstock import cli
from chemstock.chemistry import is_valid_cas
from chemstock.clock import get_today
from chemstock.demo import BOTTLES, CHEMICALS, DemoError, seed_demo
from chemstock.main import app
from chemstock.models import Chemical, InventoryItem
from chemstock.schemas import HazardClassesUpdate

TODAY = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def _fixed_today() -> Iterator[None]:
    app.dependency_overrides[get_today] = lambda: TODAY
    yield
    app.dependency_overrides.pop(get_today, None)


@pytest.fixture
def demo(session: Session) -> None:
    seed_demo(session, TODAY)


def test_the_demo_data_itself_is_valid() -> None:
    cas_numbers = [item.cas_number for item in CHEMICALS]

    assert all(is_valid_cas(cas) for cas in cas_numbers)
    assert len(set(cas_numbers)) == len(cas_numbers)
    assert {bottle.cas_number for bottle in BOTTLES} <= set(cas_numbers)
    for item in CHEMICALS:  # the same rules as the API
        HazardClassesUpdate(hazard_classes=list(item.hazard_classes))


def test_every_chemical_and_bottle_is_added(session: Session, demo: None) -> None:
    assert session.scalar(select(func.count(Chemical.id))) == len(CHEMICALS)
    assert session.scalar(select(func.count(InventoryItem.id))) == len(BOTTLES)


def test_storage_report_shows_conflicts_and_a_review(
    client: TestClient, demo: None
) -> None:
    report = client.get("/storage-conflicts", params={"limit": 200}).json()

    rules = {reason["rule"] for item in report for reason in item["reasons"]}
    assert {"acid-base", "oxidizing-acid-inorganic-acid"} <= rules
    assert "oxidizer-acid-gas-generator" in rules
    reviews = [item for item in report if item["status"] == "review_required"]
    assert {item["location"] for item in reviews} == {"Flammables cabinet"}


def test_expiry_report_shows_an_expired_and_an_expiring_bottle(
    client: TestClient, demo: None
) -> None:
    report = client.get("/inventory-items/expiring").json()

    assert [item["days_until_expiry"] for item in report] == [-10, 20]


def test_low_stock_report_shows_three_chemicals(client: TestClient, demo: None) -> None:
    names = {
        item["chemical_name"] for item in client.get("/chemicals/low-stock").json()
    }

    assert names == {"Ethanol", "Sodium hydroxide", "Dichloromethane"}


def test_demo_data_is_only_added_to_an_empty_database(
    session: Session, demo: None
) -> None:
    with pytest.raises(DemoError):
        seed_demo(session, TODAY)

    assert session.scalar(select(func.count(Chemical.id))) == len(CHEMICALS)


def test_seed_demo_command(
    session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["seed-demo"]) == 0
    assert "Added 10 chemicals and 11 bottles" in capsys.readouterr().out

    assert cli.main(["seed-demo"]) == 1
    assert "only added to an empty database" in capsys.readouterr().err
