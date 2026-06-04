"""Render a printable A4 sheet of Code128 barcodes for inventory items.

Used for products whose packaging (and barcode) gets thrown away, e.g. loose
fruit defined as custom EIGEN- products, or a pizza box. Print the sheet, stick
the codes near the fridge, scan to add/remove.
"""

from __future__ import annotations

import io

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

COLS = 3
ROWS = 8
MARGIN = 12 * mm
CELL_PAD = 3 * mm
BAR_WIDTH = 0.4 * mm
BAR_HEIGHT = 12 * mm


def _cell_size() -> tuple[float, float]:
    """Width and height of one grid cell on the A4 sheet."""
    page_w, page_h = A4
    return (page_w - 2 * MARGIN) / COLS, (page_h - 2 * MARGIN) / ROWS


def _fit_scale(natural_width: float, avail_width: float) -> float:
    """Horizontal scale so ``natural_width`` fits ``avail_width`` (never enlarges)."""
    if natural_width <= 0:
        return 1.0
    return min(1.0, avail_width / natural_width)


def _barcode_layout(
    barcode: str, x: float, cell_w: float
) -> tuple[code128.Code128, float, float]:
    """Build a Code128 and work out how to fit it in the cell at left edge ``x``.

    Returns ``(barcode, scale_x, bc_x)``: the code, the horizontal scale to apply,
    and the (scaled) left edge so it is centred within the cell's padded area.
    Long custom ``EIGEN-`` codes are wider than a cell at the default bar width,
    so they get scaled down on the X axis only -- the bar-width ratios (and thus
    scannability) are preserved while the bar height stays put.
    """
    bc = code128.Code128(barcode, barHeight=BAR_HEIGHT, barWidth=BAR_WIDTH)
    avail_w = cell_w - 2 * CELL_PAD
    scale_x = _fit_scale(bc.width, avail_w)
    scaled_w = bc.width * scale_x
    bc_x = x + (cell_w - scaled_w) / 2
    return bc, scale_x, bc_x


def render_barcode_sheet(items: list[tuple[str, str]]) -> bytes:
    """Render ``items`` (list of ``(barcode, name)``) to an A4 PDF.

    Each cell holds one Code128 barcode with the product name beneath it.
    An empty selection yields a single page with an explanatory note so the
    download never looks broken.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    if not items:
        c.setFont("Helvetica", 12)
        c.drawCentredString(
            page_w / 2, page_h / 2,
            "Keine Produkte für das Barcode-Blatt ausgewählt.",
        )
        c.showPage()
        c.save()
        return buf.getvalue()

    cell_w, cell_h = _cell_size()
    per_page = COLS * ROWS

    for index, (barcode, name) in enumerate(items):
        pos = index % per_page
        if index > 0 and pos == 0:
            c.showPage()
        col = pos % COLS
        row = pos // COLS
        x = MARGIN + col * cell_w
        y_top = page_h - MARGIN - row * cell_h

        bc, scale_x, bc_x = _barcode_layout(barcode, x, cell_w)
        bc_y = y_top - 16 * mm
        c.saveState()
        c.translate(bc_x, bc_y)
        c.scale(scale_x, 1.0)
        bc.drawOn(c, 0, 0)
        c.restoreState()

        c.setFont("Helvetica", 9)
        label = name if len(name) <= 28 else name[:27] + "…"
        c.drawCentredString(x + cell_w / 2, bc_y - 5 * mm, label)

    c.showPage()
    c.save()
    return buf.getvalue()
