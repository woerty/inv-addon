import pytest
from httpx import AsyncClient


async def test_get_locations_empty(client: AsyncClient):
    response = await client.get("/api/storage-locations/")
    assert response.status_code == 200
    assert response.json() == []


async def test_create_location(client: AsyncClient):
    response = await client.post(
        "/api/storage-locations/",
        json={"location_name": "Kühlschrank"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Kühlschrank"


async def test_create_duplicate_location(client: AsyncClient):
    await client.post("/api/storage-locations/", json={"location_name": "Keller"})
    response = await client.post("/api/storage-locations/", json={"location_name": "Keller"})
    assert response.status_code == 409


async def test_delete_location(client: AsyncClient):
    resp = await client.post("/api/storage-locations/", json={"location_name": "Garage"})
    loc_id = resp.json()["id"]
    response = await client.delete(f"/api/storage-locations/{loc_id}")
    assert response.status_code == 200
    locations = await client.get("/api/storage-locations/")
    assert all(loc["name"] != "Garage" for loc in locations.json())


async def test_delete_nonexistent_location(client: AsyncClient):
    response = await client.delete("/api/storage-locations/99999")
    assert response.status_code == 404
