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

SAMPLE_DELIVERY_DETAIL = {
    "delivery_id": "del-1",
    "status": "COMPLETED",
    "delivery_time": {
        "start": "2026-04-04T10:00:00+00:00",
        "end": "2026-04-04T10:30:00+00:00",
    },
    "orders": [
        {
            "items": [
                {
                    "id": "order-line-1",
                    "items": [
                        {
                            "id": "s100",
                            "name": "Ja! Vollmilch 1 L",
                            "image_id": "img-100",
                            "unit_quantity": "1 L",
                            "price": 99,
                        }
                    ],
                    "decorators": [{"quantity": 2}],
                },
                {
                    "id": "order-line-2",
                    "items": [
                        {
                            "id": "s200",
                            "name": "Barilla Spaghetti Nr. 5 500 g",
                            "image_id": "img-200",
                            "unit_quantity": "500 g",
                            "price": 149,
                        }
                    ],
                    "decorators": [{"quantity": 1}],
                },
            ]
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
