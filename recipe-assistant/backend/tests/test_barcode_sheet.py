from app.services.barcode_sheet import render_barcode_sheet


def test_render_returns_pdf_bytes():
    pdf = render_barcode_sheet([("EIGEN-ABC123", "Banane"), ("4006381333931", "Pizza")])
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"


def test_render_empty_selection_still_returns_pdf():
    pdf = render_barcode_sheet([])
    assert pdf[:4] == b"%PDF"


async def test_barcode_sheet_endpoint_returns_pdf(client):
    await client.post("/api/inventory/custom", json={"name": "Banane"})
    listing = await client.get("/api/inventory/")
    barcode = listing.json()[0]["barcode"]
    await client.put(f"/api/inventory/{barcode}", json={"include_in_sheet": True})

    resp = await client.get("/api/inventory/barcode-sheet.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


async def test_barcode_sheet_endpoint_empty_is_ok(client):
    resp = await client.get("/api/inventory/barcode-sheet.pdf")
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"
