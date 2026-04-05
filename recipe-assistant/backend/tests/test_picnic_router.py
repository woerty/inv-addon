import pytest
from httpx import AsyncClient

from app.services.picnic.client import get_picnic_client
from app.main import app
from tests.fixtures.picnic.fake_client import FakePicnicClient


@pytest.fixture(autouse=True)
def override_picnic_client(monkeypatch):
    fake = FakePicnicClient()
    app.dependency_overrides[get_picnic_client] = lambda: fake
    # Enable feature flag (use either PICNIC_MAIL or PICNIC_EMAIL alias - test both in separate tests if needed)
    monkeypatch.setenv("PICNIC_MAIL", "test@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "secret")
    # Clear settings cache
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_picnic_client, None)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_status_enabled(client: AsyncClient):
    response = await client.get("/api/picnic/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["account"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_import_fetch_returns_candidates(client: AsyncClient):
    response = await client.post("/api/picnic/import/fetch")
    assert response.status_code == 200
    data = response.json()
    assert len(data["deliveries"]) == 1


@pytest.mark.asyncio
async def test_import_commit_then_refetch_is_empty(client: AsyncClient):
    fetch = await client.post("/api/picnic/import/fetch")
    delivery = fetch.json()["deliveries"][0]
    decisions = [
        {
            "picnic_id": item["picnic_id"],
            "action": "create_new",
            "storage_location": "Küche",
        }
        for item in delivery["items"]
    ]
    commit = await client.post(
        "/api/picnic/import/commit",
        json={"delivery_id": delivery["delivery_id"], "decisions": decisions},
    )
    assert commit.status_code == 200
    assert commit.json()["created"] == 2

    # Dedup: second fetch should return empty
    refetch = await client.post("/api/picnic/import/fetch")
    assert refetch.json()["deliveries"] == []


@pytest.mark.asyncio
async def test_shopping_list_crud_and_sync(client: AsyncClient, override_picnic_client):
    add = await client.post(
        "/api/picnic/shopping-list",
        json={"name": "Milch", "quantity": 2, "picnic_id": "s100"},
    )
    assert add.status_code == 201
    item_id = add.json()["id"]
    assert add.json()["picnic_status"] == "mapped"

    listing = await client.get("/api/picnic/shopping-list")
    assert len(listing.json()) == 1

    sync = await client.post("/api/picnic/shopping-list/sync")
    assert sync.status_code == 200
    assert sync.json()["added_count"] == 1
    assert ("s100", 2) in override_picnic_client.added_products

    delete = await client.delete(f"/api/picnic/shopping-list/{item_id}")
    assert delete.status_code == 200
