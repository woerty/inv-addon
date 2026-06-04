# Barcode-Blatt PDF: fit barcodes to their cell

Date: 2026-06-04
Status: approved
Area: `backend/app/services/barcode_sheet.py`

## Problem

On the printable A4 barcode sheet (`/api/inventory/barcode-sheet.pdf`), barcodes
for **own products** ("eigene Produkte") render far too wide and overflow /
overlap their grid cell — spilling into the neighbouring barcode or off the page
edge.

## Root cause

Every barcode is drawn at a fixed `barWidth=0.4mm` with **no fit-to-cell logic**
(`barcode_sheet.py:56-59`). The horizontal placement uses
`bc_x = x + (cell_w - bc.width) / 2`; when `bc.width > cell_w` this term goes
negative and the barcode is pushed left, out of its cell.

Measured (at `barWidth=0.4mm`, cell width = `(210 - 2*12)/3` = **62 mm**):

| Barcode | Width | vs. 62 mm cell |
|---|---|---|
| Own product `EIGEN-` + 12 hex (18 chars) | **92.7 mm** | overflows by ~30 mm |
| Retail EAN-13 (13 digits) | **61.9 mm** | fills the cell wall-to-wall, no margin |

So own-product codes overflow badly, and even EAN-13 codes already touch the cell
edges today.

## Decision

**Scale every barcode horizontally to fit its cell, with a uniform margin.**

- `CELL_PAD = 3 * mm` on each side → `avail_w = cell_w - 2*CELL_PAD` (= 56 mm).
- Build the Code128 at the existing `barWidth=0.4mm`, `barHeight=12mm`.
- `scale_x = min(1.0, avail_w / bc.width)`.
- Draw via a **canvas X-axis transform only** (`c.scale(scale_x, 1.0)`), so the
  bar-height stays 12 mm and the bar-width *ratios* are preserved → still a valid,
  scannable Code128 at a smaller X-dimension.
- Re-center on the *scaled* width: `bc_x = x + (cell_w - bc.width*scale_x) / 2`.

Effect: EIGEN- codes shrink ~40% (X-dim ~0.25 mm); EAN-13 shrinks ~10%
(X-dim ~0.36 mm) and gains a clean 3 mm gap. Nothing overflows or touches.

Canvas X-scaling is chosen over recomputing `barWidth` because it is
geometrically exact (independent of ReportLab quiet-zone rounding), so the result
provably fits.

### Rejected alternatives

- **Global smaller `barWidth`** — shrinks fine codes too, still overflows for long
  enough codes, not adaptive.
- **Shorten the `EIGEN-` scheme** — touches the data model + existing products
  (migration), doesn't make the renderer robust. Out of scope.

## Tests (TDD)

- Pure helper `_fit_scale(natural_width, avail_width)`: clamps to 1.0; shrinks when
  wider; returns 1.0 for a code that already fits.
- Real Code128 geometry: long `EIGEN-…` → `bc.width * scale <= avail_w` and
  `scale < 1`; EAN-13 → fits `avail_w`; EIGEN- scale < EAN-13 scale.
- Render smoke test: a mixed sheet returns valid `%PDF` bytes without error.

## Out of scope

Dark mode; prices in cart/store (tracked separately). Bar height, grid
dimensions, and the label rendering are unchanged.

## Follow-up

Bump add-on version in `config.json` before push (per project convention).
