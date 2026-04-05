import json

import pytest
from httpx import AsyncClient

from app.services.picnic.login import reset_login_session
from tests.services.picnic.test_login import _FakePicnicAPI


@pytest.fixture(autouse=True)
def setup_login_env(monkeypatch, tmp_path):
    """Shared setup: patch PicnicAPI, redirect token path, enable feature."""
    _FakePicnicAPI.instances = []
    _FakePicnicAPI.require_2fa = True
    _FakePicnicAPI.valid_code = "123456"
    reset_login_session()

    import python_picnic_api2

    monkeypatch.setattr(python_picnic_api2, "PicnicAPI", _FakePicnicAPI)

    import app.services.picnic.client as client_mod

    token_path = tmp_path / "picnic_token.json"
    monkeypatch.setattr(client_mod, "TOKEN_CACHE_PATH", token_path)

    monkeypatch.setenv("PICNIC_MAIL", "test@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "secret")
    from app.config import get_settings

    get_settings.cache_clear()

    try:
        yield token_path
    finally:
        get_settings.cache_clear()
        reset_login_session()


@pytest.mark.asyncio
async def test_login_start_returns_awaiting_2fa(client: AsyncClient):
    response = await client.post("/api/picnic/login/start")
    assert response.status_code == 200
    assert response.json() == {"status": "awaiting_2fa"}


@pytest.mark.asyncio
async def test_login_start_returns_ok_when_no_2fa(client: AsyncClient, setup_login_env):
    _FakePicnicAPI.require_2fa = False
    response = await client.post("/api/picnic/login/start")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # Token should be written
    assert setup_login_env.exists()


@pytest.mark.asyncio
async def test_login_send_code_before_start_returns_409(client: AsyncClient):
    response = await client.post(
        "/api/picnic/login/send-code",
        json={"channel": "SMS"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "no_login_in_progress"


@pytest.mark.asyncio
async def test_full_login_flow(client: AsyncClient, setup_login_env):
    r1 = await client.post("/api/picnic/login/start")
    assert r1.json()["status"] == "awaiting_2fa"

    r2 = await client.post("/api/picnic/login/send-code", json={"channel": "SMS"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "sent"

    r3 = await client.post("/api/picnic/login/verify", json={"code": "123456"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "ok"

    assert setup_login_env.exists()
    assert json.loads(setup_login_env.read_text())["token"] == "token-after-2fa"


@pytest.mark.asyncio
async def test_wrong_otp_returns_400(client: AsyncClient):
    await client.post("/api/picnic/login/start")
    await client.post("/api/picnic/login/send-code", json={"channel": "SMS"})
    r = await client.post("/api/picnic/login/verify", json={"code": "000000"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_2fa_code"


@pytest.mark.asyncio
async def test_login_endpoints_503_when_feature_disabled(
    client: AsyncClient, monkeypatch
):
    monkeypatch.delenv("PICNIC_MAIL", raising=False)
    monkeypatch.delenv("PICNIC_EMAIL", raising=False)
    monkeypatch.delenv("PICNIC_PASSWORD", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    r = await client.post("/api/picnic/login/start")
    assert r.status_code == 503
