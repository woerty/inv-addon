import pytest
from httpx import AsyncClient

from app.main import app
from app.services.picnic.client import get_picnic_client
from tests.conftest import TestingSessionLocal
from tests.fixtures.picnic.fake_client import FakePicnicClient


@pytest.fixture(autouse=True)
def override_picnic_client(monkeypatch):
    fake = FakePicnicClient()
    app.dependency_overrides[get_picnic_client] = lambda: fake
    monkeypatch.setenv("PICNIC_MAIL", "test@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "secret")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_picnic_client, None)
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_resolve_preview_hit(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products/resolve-preview",
        json={"barcode": "4014400900057"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is True
    assert data["picnic_id"] == "s100"
    assert data["picnic_name"] == "Ja! Vollmilch 1 L"


@pytest.mark.asyncio
async def test_resolve_preview_miss(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products/resolve-preview",
        json={"barcode": "0000000000000"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["resolved"] is False
    assert data["reason"] == "not_in_picnic_catalog"


@pytest.mark.asyncio
async def test_create_tracked_product(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["barcode"] == "4014400900057"
    assert data["picnic_id"] == "s100"
    assert data["min_quantity"] == 1
    assert data["target_quantity"] == 4
    assert data["current_quantity"] == 0
    assert data["below_threshold"] is True  # qty=0 < min=1


@pytest.mark.asyncio
async def test_create_adds_to_picnic_cart_if_below_threshold(
    client: AsyncClient, override_picnic_client: FakePicnicClient
):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 201

    # Restock should have called add_product with the full target (4 - 0)
    assert ("s100", 4) in override_picnic_client.added_products


@pytest.mark.asyncio
async def test_create_not_in_picnic_catalog_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "0000000000000", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 422
    # FastAPI wraps HTTPException(detail={...}) into {"detail": {...}}
    detail = response.json()["detail"]
    assert detail["error"] == "picnic_product_not_found"


@pytest.mark.asyncio
async def test_create_target_le_min_returns_422(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 5, "target_quantity": 3},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_duplicate_returns_409(client: AsyncClient):
    payload = {
        "barcode": "4014400900057",
        "min_quantity": 1,
        "target_quantity": 4,
    }
    await client.post("/api/tracked-products", json=payload)
    response = await client.post("/api/tracked-products", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_tracked_products_joins_current_quantity(client: AsyncClient):
    # Seed inventory with a quantity
    await client.post(
        "/api/inventory/barcode", json={"barcode": "4014400900057"}
    )
    await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )

    response = await client.get("/api/tracked-products")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["current_quantity"] == 1
    assert items[0]["below_threshold"] is False  # qty=1 == min=1


@pytest.mark.asyncio
async def test_patch_tracked_product_updates_and_rechecks(
    client: AsyncClient, override_picnic_client: FakePicnicClient
):
    # Seed qty=1 inventory and rule min=1 target=2 → not below threshold
    await client.post(
        "/api/inventory/barcode", json={"barcode": "4014400900057"}
    )
    await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 2},
    )
    # No cart additions yet (qty=1 >= min=1)
    assert override_picnic_client.added_products == []

    # Raise min_quantity to 3 → now below threshold, check should fire
    response = await client.patch(
        "/api/tracked-products/4014400900057",
        json={"min_quantity": 3, "target_quantity": 5},
    )
    assert response.status_code == 200
    assert response.json()["below_threshold"] is True

    # Restock should have added delta = target(5) - current(1) = 4 to cart
    assert ("s100", 4) in override_picnic_client.added_products


@pytest.mark.asyncio
async def test_delete_tracked_product(client: AsyncClient):
    await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    response = await client.delete("/api/tracked-products/4014400900057")
    assert response.status_code == 200

    listing = await client.get("/api/tracked-products")
    assert listing.json() == []


@pytest.mark.asyncio
async def test_patch_nonexistent_returns_404(client: AsyncClient):
    response = await client.patch(
        "/api/tracked-products/nope", json={"min_quantity": 1, "target_quantity": 2}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_feature_disabled_returns_503(client: AsyncClient, monkeypatch):
    monkeypatch.delenv("PICNIC_MAIL", raising=False)
    monkeypatch.delenv("PICNIC_PASSWORD", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    response = await client.get("/api/tracked-products")
    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "picnic_not_configured"


@pytest.mark.asyncio
async def test_create_synth_barcode_from_picnic_id(client: AsyncClient):
    """Subscribe from store browser: no barcode, just picnic_id + name."""
    response = await client.post(
        "/api/tracked-products",
        json={
            "picnic_id": "s100",
            "name": "Ja! Vollmilch 1 L",
            "min_quantity": 1,
            "target_quantity": 4,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["barcode"] == "picnic:s100"
    assert data["picnic_id"] == "s100"
    assert data["name"] == "Ja! Vollmilch 1 L"
    assert data["min_quantity"] == 1
    assert data["target_quantity"] == 4


@pytest.mark.asyncio
async def test_create_synth_duplicate_returns_409(client: AsyncClient):
    payload = {
        "picnic_id": "s100",
        "name": "Ja! Vollmilch 1 L",
        "min_quantity": 1,
        "target_quantity": 4,
    }
    await client.post("/api/tracked-products", json=payload)
    response = await client.post("/api/tracked-products", json=payload)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_create_synth_missing_picnic_id_returns_422(client: AsyncClient):
    """barcode=null without picnic_id should fail validation."""
    response = await client.post(
        "/api/tracked-products",
        json={"min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_with_real_barcode_still_works(client: AsyncClient):
    """Existing creation path (barcode + Picnic GTIN lookup) must remain unchanged."""
    response = await client.post(
        "/api/tracked-products",
        json={"barcode": "4014400900057", "min_quantity": 1, "target_quantity": 4},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["barcode"] == "4014400900057"
    assert data["picnic_id"] == "s100"
