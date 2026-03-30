import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.barcode import lookup_barcode


def _make_client_mock(response_mock):
    """Create a mock httpx.AsyncClient that works as async context manager."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response_mock)
    # AsyncMock automatically supports __aenter__/__aexit__
    # but we need the context manager to return the client itself
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.mark.asyncio
async def test_lookup_barcode_found():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": 1,
        "product": {
            "product_name": "Vollmilch",
            "categories": "Milchprodukte",
        },
    }

    mock_client = _make_client_mock(mock_response)
    with patch("app.services.barcode.httpx.AsyncClient", return_value=mock_client):
        result = await lookup_barcode("4014400900057")

    assert result["name"] == "Vollmilch"
    assert result["category"] == "Milchprodukte"


@pytest.mark.asyncio
async def test_lookup_barcode_not_found():
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": 0}

    mock_client = _make_client_mock(mock_response)
    with patch("app.services.barcode.httpx.AsyncClient", return_value=mock_client):
        result = await lookup_barcode("0000000000000")

    assert result["name"] == "Unbekanntes Produkt"
    assert result["category"] == "Unbekannt"


@pytest.mark.asyncio
async def test_lookup_barcode_timeout():
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

    with patch("app.services.barcode.httpx.AsyncClient", return_value=mock_client):
        result = await lookup_barcode("4014400900057")

    assert result["name"] == "Unbekanntes Produkt"
    assert result["category"] == "Unbekannt"
