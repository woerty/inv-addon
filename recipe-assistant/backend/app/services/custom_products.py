"""Synthetic barcode convention for user-created ("eigene") products.

Products the user defines themselves (e.g. loose fruit with no EAN) get a
placeholder barcode of the form ``EIGEN-<token>``. The scan paths detect this
prefix to skip the external OpenFoodFacts lookup, and the decrement logic keeps
such rows alive at quantity 0 so a printed barcode stays valid.
"""

from __future__ import annotations

import uuid

CUSTOM_BARCODE_PREFIX = "EIGEN-"


def is_custom_barcode(barcode: str) -> bool:
    """Return True if *barcode* follows the ``EIGEN-<token>`` convention."""
    return barcode.startswith(CUSTOM_BARCODE_PREFIX)


def make_custom_barcode() -> str:
    """Build a collision-free synthetic barcode for a user-created product."""
    return f"{CUSTOM_BARCODE_PREFIX}{uuid.uuid4().hex[:12].upper()}"
