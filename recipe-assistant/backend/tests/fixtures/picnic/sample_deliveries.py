"""Sanitized sample responses shaped like python-picnic-api2 output."""

SAMPLE_DELIVERIES_SUMMARY = [
    {
        "delivery_id": "del-1",
        "status": "COMPLETED",
        "delivery_time": {
            "start": "2026-04-04T10:00:00+00:00",
            "end": "2026-04-04T10:30:00+00:00",
        },
    },
]

# Shaped like a real /deliveries/{id} response: orders[].items[] are ORDER_LINEs
# carrying the line total (`price`/`display_price`); the nested ORDER_ARTICLE
# carries a sentinel `price` (432199) that must be ignored, plus `image_ids`.
SAMPLE_DELIVERY_DETAIL = {
    "type": "DELIVERY",
    "delivery_id": "del-1",
    "status": "COMPLETED",
    "delivery_time": {
        "start": "2026-04-04T10:00:00+00:00",
        "end": "2026-04-04T10:30:00+00:00",
    },
    "slot": {
        "window_start": "2026-04-04T10:00:00+00:00",
        "window_end": "2026-04-04T10:30:00+00:00",
    },
    "orders": [
        {
            "type": "ORDER",
            "id": "order-1",
            "total_price": 347,  # 198 (2x milk) + 149 (spaghetti)
            "items": [
                {
                    "type": "ORDER_LINE",
                    "id": "order-line-1",
                    "price": 198,
                    "display_price": 198,
                    "items": [
                        {
                            "type": "ORDER_ARTICLE",
                            "id": "s100",
                            "name": "Ja! Vollmilch 1 L",
                            "image_ids": ["img-100"],
                            "unit_quantity": "1 L",
                            "price": 432199,
                            "decorators": [
                                {"type": "IMMUTABLE"},
                                {"type": "QUANTITY", "quantity": 2},
                            ],
                        }
                    ],
                },
                {
                    "type": "ORDER_LINE",
                    "id": "order-line-2",
                    "price": 149,
                    "display_price": 149,
                    "items": [
                        {
                            "type": "ORDER_ARTICLE",
                            "id": "s200",
                            "name": "Barilla Spaghetti Nr. 5 500 g",
                            "image_ids": ["img-200"],
                            "unit_quantity": "500 g",
                            "price": 432199,
                            "decorators": [
                                {"type": "IMMUTABLE"},
                                {"type": "QUANTITY", "quantity": 1},
                            ],
                        }
                    ],
                },
            ],
        }
    ],
}

SAMPLE_SEARCH_MILK = [
    {
        "type": "CATEGORY",
        "items": [
            {
                "id": "s100",
                "name": "Ja! Vollmilch 1 L",
                "display_price": 99,
                "image_id": "img-100",
                "unit_quantity": "1 L",
            },
            {
                "id": "s101",
                "name": "Weihenstephan Vollmilch 3,5% 1 L",
                "display_price": 139,
                "image_id": "img-101",
                "unit_quantity": "1 L",
            },
        ],
    },
]

# Shaped like /pages/promo-page-root: SELLING_UNIT_TILE.sellingUnit is
# self-contained; the strikethrough/label live in a paired analytics promotion
# context (product_id + promotion). Nesting is irrelevant — the parser walks.
SAMPLE_PROMO_PAGE = {
    "type": "PAGE",
    "child": {
        "type": "BLOCK",
        "children": [
            {
                "type": "PML",
                "id": "selling-unit-s100-tile-PromoBox",
                "analytics": {
                    "contexts": [
                        {"data": {"product_id": "s100"}, "schema": "iglu:.../product/1-0-0"},
                        {
                            "data": {
                                "promotion_id": "p1",
                                "promotion_label": "20% Rabatt",
                                "price": 143,
                                "strikethrough_price": 179,
                                "show_strikethrough_price": True,
                            },
                            "schema": "iglu:.../promotion/1-1-0",
                        },
                    ]
                },
            },
            {
                "type": "SELLING_UNIT_TILE",
                "sellingUnit": {
                    "id": "s100",
                    "name": "Gut&Günstig Gouda gerieben",
                    "image_id": "img-100",
                    "display_price": 143,
                    "unit_quantity": "250g",
                },
            },
            {
                "type": "PML",
                "analytics": {
                    "contexts": [
                        {"data": {"product_id": "s200"}, "schema": "iglu:.../product/1-0-0"},
                        {"data": {"promotion_label": "jetzt 0.99€"}, "schema": "iglu:.../promotion/1-1-0"},
                    ]
                },
            },
            {
                "type": "SELLING_UNIT_TILE",
                "sellingUnit": {
                    "id": "s200",
                    "name": "Ja! Toastbrot",
                    "image_id": "img-200",
                    "display_price": 99,
                    "unit_quantity": "1 Stück",
                },
            },
        ],
    },
}

SAMPLE_USER = {
    "user_id": "u-1",
    "firstname": "Test",
    "lastname": "User",
    "contact_email": "test@example.com",
}

SAMPLE_CART_EMPTY = {"items": [], "total_price": 0}
