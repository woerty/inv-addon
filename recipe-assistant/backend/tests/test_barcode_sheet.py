import pytest

from app.services.barcode_sheet import render_barcode_sheet
from app.services import barcode_sheet as bs


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


# --- barcode fit-to-cell (own-product codes were overflowing) ---


def test_fit_scale_keeps_size_when_already_fits():
    assert bs._fit_scale(40.0, 56.0) == 1.0


def test_fit_scale_never_exceeds_one():
    assert bs._fit_scale(10.0, 56.0) == 1.0


def test_fit_scale_shrinks_proportionally_when_too_wide():
    assert bs._fit_scale(92.0, 56.0) == pytest.approx(56.0 / 92.0)


def test_long_custom_barcode_stays_within_its_cell():
    # An 18-char EIGEN- code is ~93mm wide at the default bar width and used to
    # overflow the ~62mm cell. It must now be scaled down to sit inside the
    # cell's padded area.
    cell_w, _ = bs._cell_size()
    x = 12.0  # arbitrary cell left edge
    barcode, scale_x, bc_x = bs._barcode_layout("EIGEN-ABC123456789", x, cell_w)
    scaled_w = barcode.width * scale_x
    assert scale_x < 1.0
    assert bc_x >= x + bs.CELL_PAD - 1e-6
    assert bc_x + scaled_w <= x + cell_w - bs.CELL_PAD + 1e-6


def test_retail_ean_stays_within_its_cell():
    cell_w, _ = bs._cell_size()
    x = 12.0
    barcode, scale_x, bc_x = bs._barcode_layout("4006381333931", x, cell_w)
    scaled_w = barcode.width * scale_x
    assert bc_x >= x + bs.CELL_PAD - 1e-6
    assert bc_x + scaled_w <= x + cell_w - bs.CELL_PAD + 1e-6


def test_longer_barcode_is_scaled_down_more():
    cell_w, _ = bs._cell_size()
    _, ean_scale, _ = bs._barcode_layout("4006381333931", 12.0, cell_w)
    _, custom_scale, _ = bs._barcode_layout("EIGEN-ABC123456789", 12.0, cell_w)
    assert custom_scale < ean_scale
