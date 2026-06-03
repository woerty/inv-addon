"""Tests for parsing the Picnic "Bündel-Bonus" (quantity-tier) block.

The structure mirrors the real product-details-page-root PML: a BLOCK whose id
starts with ``product-page-bundles`` containing one SELLING_UNIT_TILE per tier.
Each tier carries its own selling-unit id, a PRICE node (per-unit price), an
optional quantity marker (a digit next to a ``crossSmall`` icon) and an optional
"Spare X Cent" savings label.
"""

from __future__ import annotations

from app.services.picnic.bundles import parse_bundles

SAMPLE_BUNDLE_PAGE = {
    "body": {
        "child": {
            "child": {
                "children": [
                    {
                        "id": "product-page-bundles-12173408",
                        "type": "BLOCK",
                        "children": [
                            {
                                "id": "s1026031",
                                "type": "STATE_BOUNDARY",
                                "child": {
                                    "type": "PML",
                                    "content": {
                                        "type": "SELLING_UNIT_TILE",
                                        "sellingUnit": {"id": "s1026031", "name": "Fruity Mix"},
                                    },
                                    "pml": {
                                        "component": {
                                            "type": "STACK",
                                            "children": [
                                                {"markdown": "Fruity Mix", "type": "RICH_TEXT"},
                                                {"markdown": "54g", "type": "RICH_TEXT"},
                                                {"type": "PRICE", "price": 199},
                                            ],
                                        }
                                    },
                                },
                            },
                            {
                                "id": "s1079385",
                                "type": "STATE_BOUNDARY",
                                "child": {
                                    "type": "PML",
                                    "content": {
                                        "type": "SELLING_UNIT_TILE",
                                        "sellingUnit": {"id": "s1079385"},
                                    },
                                    "pml": {
                                        "component": {
                                            "type": "STACK",
                                            "children": [
                                                {"markdown": "#(#333333)Spare 20 Cent#(#333333)", "type": "RICH_TEXT"},
                                                {"markdown": "#(#b40117)2#(#b40117)", "type": "RICH_TEXT"},
                                                {"type": "ICON", "iconKey": "crossSmall"},
                                                {"type": "PRICE", "price": 189},
                                            ],
                                        }
                                    },
                                },
                            },
                            {
                                "id": "s1079386",
                                "type": "STATE_BOUNDARY",
                                "child": {
                                    "type": "PML",
                                    "content": {
                                        "type": "SELLING_UNIT_TILE",
                                        "sellingUnit": {"id": "s1079386"},
                                    },
                                    "pml": {
                                        "component": {
                                            "type": "STACK",
                                            "children": [
                                                {"markdown": "#(#b40117)Spare 56 Cent#(#b40117)", "type": "RICH_TEXT"},
                                                {"markdown": "#(#b40117)4#(#b40117)", "type": "RICH_TEXT"},
                                                {"type": "ICON", "iconKey": "crossSmall"},
                                                {"type": "PRICE", "price": 185},
                                            ],
                                        }
                                    },
                                },
                            },
                        ],
                    }
                ]
            }
        }
    }
}


def test_parse_bundles_extracts_three_tiers():
    tiers = parse_bundles(SAMPLE_BUNDLE_PAGE)
    assert len(tiers) == 3

    base, two, four = tiers  # sorted by quantity

    assert base == {
        "picnic_id": "s1026031",
        "quantity": 1,
        "unit_price_cents": 199,
        "total_price_cents": 199,
        "savings_text": None,
    }
    assert two == {
        "picnic_id": "s1079385",
        "quantity": 2,
        "unit_price_cents": 189,
        "total_price_cents": 378,
        "savings_text": "Spare 20 Cent",
    }
    assert four == {
        "picnic_id": "s1079386",
        "quantity": 4,
        "unit_price_cents": 185,
        "total_price_cents": 740,
        "savings_text": "Spare 56 Cent",
    }


def test_parse_bundles_no_block_returns_empty():
    assert parse_bundles({"body": {"child": {}}}) == []
    assert parse_bundles({}) == []
