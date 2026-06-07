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

SAMPLE_USER = {
    "user_id": "u-1",
    "firstname": "Test",
    "lastname": "User",
    "contact_email": "test@example.com",
}

SAMPLE_CART_EMPTY = {"items": [], "total_price": 0}
