"""Synthetic barcode convention for Picnic-only tracked products.

Products subscribed from the Picnic Store Browser have no real EAN yet.
They use the format ``picnic:<picnic_id>`` as a placeholder primary key
until the user promotes them to a real barcode.
"""

from __future__ import annotations

SYNTHETIC_BARCODE_PREFIX = "picnic:"


def is_synthetic_barcode(barcode: str) -> bool:
    """Return True if *barcode* follows the synthetic ``picnic:<id>`` convention."""
    return barcode.startswith(SYNTHETIC_BARCODE_PREFIX)


def make_synthetic_barcode(picnic_id: str) -> str:
    """Build a synthetic barcode for a Picnic product ID."""
    return f"{SYNTHETIC_BARCODE_PREFIX}{picnic_id}"
