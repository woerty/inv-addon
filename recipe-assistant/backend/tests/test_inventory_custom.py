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
