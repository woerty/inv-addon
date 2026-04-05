"""Tests for POST /api/tracked-products/{barcode}/promote-barcode."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.tracked_product import TrackedProduct
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


async def _create_synth(client: AsyncClient, picnic_id: str = "s100") -> dict:
    """Helper: create a synth-barcode tracked product."""
    resp = await client.post(
        "/api/tracked-products",
        json={
            "picnic_id": picnic_id,
            "name": "Test Product",
            "min_quantity": 1,
            "target_quantity": 4,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def _create_real(client: AsyncClient, barcode: str = "4014400900057") -> dict:
    """Helper: create a real-barcode tracked product via classic path."""
    resp = await client.post(
        "/api/tracked-products",
        json={"barcode": barcode, "min_quantity": 2, "target_quantity": 5},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_promote_happy_path(client: AsyncClient):
    await _create_synth(client)
    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": "4014400900057"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tracked"]["barcode"] == "4014400900057"
    assert data["tracked"]["picnic_id"] == "s100"
    assert data["tracked"]["min_quantity"] == 1
    assert data["tracked"]["target_quantity"] == 4
    assert data["merged"] is False

    # Old synth PK should be gone.
    async with TestingSessionLocal() as session:
        old = (
            await session.execute(
                select(TrackedProduct).where(TrackedProduct.barcode == "picnic:s100")
            )
        ).scalar_one_or_none()
        assert old is None
        new = (
            await session.execute(
                select(TrackedProduct).where(TrackedProduct.barcode == "4014400900057")
            )
        ).scalar_one_or_none()
        assert new is not None
        assert new.picnic_id == "s100"


@pytest.mark.asyncio
async def test_promote_merge_collision(client: AsyncClient):
    """When the target EAN already has a tracked rule, merge: synth wins."""
    await _create_real(client)  # barcode=4014400900057, min=2, target=5
    await _create_synth(client)  # barcode=picnic:s100, min=1, target=4

    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": "4014400900057"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tracked"]["barcode"] == "4014400900057"
    assert data["merged"] is True
    # Synth row's values win:
    assert data["tracked"]["min_quantity"] == 1
    assert data["tracked"]["target_quantity"] == 4

    # Only one row should remain.
    async with TestingSessionLocal() as session:
        rows = (await session.execute(select(TrackedProduct))).scalars().all()
        assert len(rows) == 1
        assert rows[0].barcode == "4014400900057"


@pytest.mark.asyncio
async def test_promote_not_found_404(client: AsyncClient):
    response = await client.post(
        "/api/tracked-products/picnic%3Anonexistent/promote-barcode",
        json={"new_barcode": "4014400900057"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_promote_already_real_400(client: AsyncClient):
    """Cannot promote a row that already has a real barcode."""
    await _create_real(client)
    response = await client.post(
        "/api/tracked-products/4014400900057/promote-barcode",
        json={"new_barcode": "9999999999999"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "already_real_barcode"


@pytest.mark.asyncio
async def test_promote_synth_new_barcode_400(client: AsyncClient):
    """new_barcode must be a real EAN, not another synth."""
    await _create_synth(client)
    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": "picnic:s200"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_new_barcode"


@pytest.mark.asyncio
async def test_promote_empty_new_barcode_422(client: AsyncClient):
    """Empty new_barcode should fail Pydantic validation."""
    await _create_synth(client)
    response = await client.post(
        "/api/tracked-products/picnic%3As100/promote-barcode",
        json={"new_barcode": ""},
    )
    assert response.status_code == 422
