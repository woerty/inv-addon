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

    cell_w = (page_w - 2 * MARGIN) / COLS
    cell_h = (page_h - 2 * MARGIN) / ROWS
    per_page = COLS * ROWS

    for index, (barcode, name) in enumerate(items):
        pos = index % per_page
        if index > 0 and pos == 0:
            c.showPage()
        col = pos % COLS
        row = pos // COLS
        x = MARGIN + col * cell_w
        y_top = page_h - MARGIN - row * cell_h

        bc = code128.Code128(barcode, barHeight=12 * mm, barWidth=0.4 * mm)
        bc_x = x + (cell_w - bc.width) / 2
        bc_y = y_top - 16 * mm
        bc.drawOn(c, bc_x, bc_y)

        c.setFont("Helvetica", 9)
        label = name if len(name) <= 28 else name[:27] + "…"
        c.drawCentredString(x + cell_w / 2, bc_y - 5 * mm, label)

    c.showPage()
    c.save()
    return buf.getvalue()
