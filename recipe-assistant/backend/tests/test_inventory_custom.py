async def test_create_custom_product_generates_eigen_barcode(client):
    resp = await client.post("/api/inventory/custom", json={"name": "Banane"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Banane"
    assert data["barcode"].startswith("EIGEN-")
    assert data["quantity"] == 0
    assert data["category"] == "Eigene Produkte"


async def test_create_custom_product_with_quantity_and_location(client):
    resp = await client.post(
        "/api/inventory/custom",
        json={"name": "Apfel", "quantity": 3, "storage_location": "Obstkorb"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["quantity"] == 3
    assert data["storage_location"]["name"] == "Obstkorb"


async def test_custom_product_appears_in_inventory(client):
    await client.post("/api/inventory/custom", json={"name": "Gurke"})
    listing = await client.get("/api/inventory/")
    names = [i["name"] for i in listing.json()]
    assert "Gurke" in names


async def test_scan_in_existing_custom_product_increments_without_lookup(client):
    created = (await client.post("/api/inventory/custom", json={"name": "Banane"})).json()
    barcode = created["barcode"]

    resp = await client.post("/api/inventory/scan-in", json={"barcode": barcode})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["name"] == "Banane"  # NOT "Testprodukt" from the mock lookup
    assert data["quantity"] == 1


async def test_scan_in_unknown_custom_barcode_errors(client):
    resp = await client.post(
        "/api/inventory/scan-in", json={"barcode": "EIGEN-DEADBEEF0000"}
    )
    assert resp.status_code == 404
    assert resp.json()["status"] == "unknown_custom_product"


async def test_add_by_barcode_unknown_custom_errors(client):
    resp = await client.post(
        "/api/inventory/barcode", json={"barcode": "EIGEN-DEADBEEF0000"}
    )
    assert resp.status_code == 404


async def test_custom_product_kept_as_zombie_at_zero(client):
    created = (await client.post("/api/inventory/custom", json={"name": "Banane", "quantity": 1})).json()
    barcode = created["barcode"]

    resp = await client.post("/api/inventory/scan-out", json={"barcode": barcode})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is False
    assert resp.json()["remaining_quantity"] == 0

    listing = await client.get("/api/inventory/")
    assert any(i["barcode"] == barcode for i in listing.json())


async def test_real_product_still_deleted_at_zero(client):
    await client.post("/api/inventory/barcode", json={"barcode": "1234567890123"})
    resp = await client.post("/api/inventory/scan-out", json={"barcode": "1234567890123"})
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
