import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_inventory_empty(client: AsyncClient):
    response = await client.get("/api/inventory/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_add_item_by_barcode(client: AsyncClient):
    response = await client.post(
        "/api/inventory/barcode",
        json={"barcode": "4014400900057", "storage_location": None},
    )
    assert response.status_code == 201
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_add_duplicate_barcode_increments_quantity(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})
    response = await client.get("/api/inventory/")
    items = response.json()
    matching = [i for i in items if i["barcode"] == "1234567890123"]
    assert len(matching) == 1
    assert matching[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_update_item_quantity(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "1111111111111"})
    response = await client.put("/api/inventory/1111111111111", json={"quantity": 5})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "1111111111111"]
    assert matching[0]["quantity"] == 5


@pytest.mark.asyncio
async def test_update_quantity_to_zero_deletes(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "2222222222222"})
    response = await client.put("/api/inventory/2222222222222", json={"quantity": 0})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "2222222222222"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_delete_item(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "3333333333333"})
    response = await client.delete("/api/inventory/3333333333333")
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "3333333333333"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_remove_decrements_quantity(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "4444444444444"})
    await client.post("/api/inventory/barcode", json={"barcode": "4444444444444"})
    response = await client.post("/api/inventory/remove", json={"barcode": "4444444444444"})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "4444444444444"]
    assert matching[0]["quantity"] == 1


@pytest.mark.asyncio
async def test_remove_last_item_deletes(client: AsyncClient):
    await client.post("/api/inventory/barcode", json={"barcode": "5555555555555"})
    response = await client.post("/api/inventory/remove", json={"barcode": "5555555555555"})
    assert response.status_code == 200
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "5555555555555"]
    assert len(matching) == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client: AsyncClient):
    response = await client.delete("/api/inventory/9999999999999")
    assert response.status_code == 404


# ---- /scan-out endpoint (scanner API contract) ----
#
# See docs/superpowers/specs/2026-04-05-scanner-api-design.md for the contract.
# Response bodies are FLAT (no {"detail": ...} wrapper) so remote terminal
# clients can branch on the `status` field directly.

from app.config import Settings, get_settings
from app.main import app as fastapi_app


def _override_settings_with_token(token: str):
    """Install a settings override for the duration of one test."""
    def _factory():
        return Settings(scanner_token=token)
    fastapi_app.dependency_overrides[get_settings] = _factory


def _clear_settings_override():
    fastapi_app.dependency_overrides.pop(get_settings, None)


@pytest.mark.asyncio
async def test_scan_out_decrements_quantity(client: AsyncClient):
    """200 OK, structured body, deleted=False when qty > 1."""
    await client.post("/api/inventory/barcode", json={"barcode": "6000000000001"})
    await client.post("/api/inventory/barcode", json={"barcode": "6000000000001"})
    await client.post("/api/inventory/barcode", json={"barcode": "6000000000001"})

    response = await client.post("/api/inventory/scan-out", json={"barcode": "6000000000001"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["barcode"] == "6000000000001"
    assert body["name"] == "Testprodukt"
    assert body["remaining_quantity"] == 2
    assert body["deleted"] is False


@pytest.mark.asyncio
async def test_scan_out_deletes_last_unit(client: AsyncClient):
    """200 OK, deleted=True, item no longer in inventory."""
    await client.post("/api/inventory/barcode", json={"barcode": "6000000000002"})

    response = await client.post("/api/inventory/scan-out", json={"barcode": "6000000000002"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["remaining_quantity"] == 0
    assert body["deleted"] is True

    inv = await client.get("/api/inventory/")
    assert not [i for i in inv.json() if i["barcode"] == "6000000000002"]


@pytest.mark.asyncio
async def test_scan_out_returns_404_for_unknown_barcode(client: AsyncClient):
    """404 with flat body; no {"detail": ...} wrapper."""
    response = await client.post("/api/inventory/scan-out", json={"barcode": "9999999999999"})

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "not_found"
    assert body["barcode"] == "9999999999999"
    assert "error" in body
    # Make sure we're NOT wrapping in FastAPI's default {"detail": ...}
    assert "detail" not in body


@pytest.mark.asyncio
async def test_scan_out_requires_token_when_configured(client: AsyncClient):
    """With scanner_token set, missing header → 401 with flat body."""
    _override_settings_with_token("supersecret")
    try:
        await client.post("/api/inventory/barcode", json={"barcode": "6000000000003"})

        response = await client.post(
            "/api/inventory/scan-out", json={"barcode": "6000000000003"}
        )

        assert response.status_code == 401
        body = response.json()
        assert body["status"] == "unauthorized"
        assert "error" in body
        assert "detail" not in body
    finally:
        _clear_settings_override()


@pytest.mark.asyncio
async def test_scan_out_accepts_correct_token(client: AsyncClient):
    """With scanner_token set, matching header → 200."""
    _override_settings_with_token("supersecret")
    try:
        await client.post("/api/inventory/barcode", json={"barcode": "6000000000004"})

        response = await client.post(
            "/api/inventory/scan-out",
            json={"barcode": "6000000000004"},
            headers={"X-Scanner-Token": "supersecret"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        _clear_settings_override()


@pytest.mark.asyncio
async def test_scan_out_rejects_wrong_token(client: AsyncClient):
    """With scanner_token set, wrong header → 401 (not a timing leak via != comparison)."""
    _override_settings_with_token("supersecret")
    try:
        await client.post("/api/inventory/barcode", json={"barcode": "6000000000005"})

        response = await client.post(
            "/api/inventory/scan-out",
            json={"barcode": "6000000000005"},
            headers={"X-Scanner-Token": "wrong"},
        )

        assert response.status_code == 401
        assert response.json()["status"] == "unauthorized"
    finally:
        _clear_settings_override()


@pytest.mark.asyncio
async def test_scan_out_ignores_token_when_unconfigured(client: AsyncClient):
    """Empty scanner_token → endpoint accepts requests with or without header."""
    # No override: conftest uses default Settings() → scanner_token == ""
    await client.post("/api/inventory/barcode", json={"barcode": "6000000000006"})

    response = await client.post(
        "/api/inventory/scan-out",
        json={"barcode": "6000000000006"},
        headers={"X-Scanner-Token": "arbitrary-value"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ---- /scan-in endpoint (scanner API contract) ----
#
# See docs/superpowers/specs/2026-04-05-scanner-api-design.md. Parallels
# /scan-out: flat JSON, same auth model, optional storage_location_id that
# references storage_locations.id (not name — scanner clients pick from a
# cached list, auto-create on typo would be wrong).


async def _create_location(client: AsyncClient, name: str) -> int:
    """Create a storage location via the public API and return its id."""
    response = await client.post("/api/storage-locations/", json={"location_name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_scan_in_creates_new_item_without_location(client: AsyncClient):
    """Unknown barcode, no storage_location_id → 200, created:true, location null."""
    response = await client.post(
        "/api/inventory/scan-in", json={"barcode": "7000000000001"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["barcode"] == "7000000000001"
    assert body["name"] == "Testprodukt"  # from conftest mock
    assert body["quantity"] == 1
    assert body["storage_location"] is None
    assert body["created"] is True


@pytest.mark.asyncio
async def test_scan_in_creates_new_item_with_location(client: AsyncClient):
    """Unknown barcode + valid id → 200, created:true, storage_location populated."""
    loc_id = await _create_location(client, "Kühlschrank")

    response = await client.post(
        "/api/inventory/scan-in",
        json={"barcode": "7000000000002", "storage_location_id": loc_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["created"] is True
    assert body["storage_location"] == {"id": loc_id, "name": "Kühlschrank"}


@pytest.mark.asyncio
async def test_scan_in_increments_existing_quantity(client: AsyncClient):
    """Existing barcode → 200, created:false, quantity +1."""
    await client.post("/api/inventory/scan-in", json={"barcode": "7000000000003"})
    await client.post("/api/inventory/scan-in", json={"barcode": "7000000000003"})

    response = await client.post(
        "/api/inventory/scan-in", json={"barcode": "7000000000003"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["created"] is False
    assert body["quantity"] == 3


@pytest.mark.asyncio
async def test_scan_in_preserves_existing_location(client: AsyncClient):
    """Existing item has location A; scan-in with location B must not overwrite."""
    loc_a = await _create_location(client, "Speisekammer")
    loc_b = await _create_location(client, "Tiefkühler")

    # First scan sets location A
    await client.post(
        "/api/inventory/scan-in",
        json={"barcode": "7000000000004", "storage_location_id": loc_a},
    )

    # Second scan tries to move to B — should be refused silently,
    # response should echo the item's ACTUAL (still A) location.
    response = await client.post(
        "/api/inventory/scan-in",
        json={"barcode": "7000000000004", "storage_location_id": loc_b},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is False
    assert body["quantity"] == 2
    assert body["storage_location"] == {"id": loc_a, "name": "Speisekammer"}

    # Double-check DB state via the inventory list
    inv = await client.get("/api/inventory/")
    matching = [i for i in inv.json() if i["barcode"] == "7000000000004"]
    assert len(matching) == 1
    assert matching[0]["storage_location"]["id"] == loc_a


@pytest.mark.asyncio
async def test_scan_in_rejects_unknown_storage_location_id(client: AsyncClient):
    """Non-null storage_location_id that doesn't exist → 400, no state change."""
    response = await client.post(
        "/api/inventory/scan-in",
        json={"barcode": "7000000000005", "storage_location_id": 9999},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "invalid_storage_location"
    assert body["storage_location_id"] == 9999
    assert "error" in body
    assert "detail" not in body

    # Ensure no item was created despite the failure
    inv = await client.get("/api/inventory/")
    assert not [i for i in inv.json() if i["barcode"] == "7000000000005"]


@pytest.mark.asyncio
async def test_scan_in_requires_token_when_configured(client: AsyncClient):
    _override_settings_with_token("supersecret")
    try:
        response = await client.post(
            "/api/inventory/scan-in", json={"barcode": "7000000000006"}
        )
        assert response.status_code == 401
        body = response.json()
        assert body["status"] == "unauthorized"
        assert "detail" not in body
    finally:
        _clear_settings_override()


@pytest.mark.asyncio
async def test_scan_in_accepts_correct_token(client: AsyncClient):
    _override_settings_with_token("supersecret")
    try:
        response = await client.post(
            "/api/inventory/scan-in",
            json={"barcode": "7000000000007"},
            headers={"X-Scanner-Token": "supersecret"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        _clear_settings_override()
