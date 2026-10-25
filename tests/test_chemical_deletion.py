from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from chemstock.models import InventoryItem


def test_delete_chemical_in_use_returns_conflict(
    client: TestClient, session: Session
) -> None:
    chemical_id = client.post("/chemicals", json={"name": "Water"}).json()["id"]
    session.add(InventoryItem(chemical_id=chemical_id, quantity=Decimal("1"), unit="L"))
    session.commit()

    response = client.delete(f"/chemicals/{chemical_id}")

    assert response.status_code == 409
    assert client.get(f"/chemicals/{chemical_id}").status_code == 200
