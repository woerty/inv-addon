import json
from types import SimpleNamespace

import pytest

from app.services.picnic.client import PicnicNotConfigured
from app.services.picnic.login import (
    PicnicLoginInvalidCode,
    PicnicLoginNotInProgress,
    PicnicLoginSession,
)


class _FakePicnicAPI:
    """Simulates python_picnic_api2.PicnicAPI for the 2FA flow."""

    # Class-level instrumentation so tests can assert calls
    instances: list["_FakePicnicAPI"] = []
    require_2fa = True
    valid_code = "123456"

    def __init__(self, country_code: str = "DE", auth_token: str | None = None):
        self.country_code = country_code
        self.session = SimpleNamespace(auth_token=auth_token)
        self.login_called = False
        self.generate_calls: list[str] = []
        self.verify_calls: list[str] = []
        _FakePicnicAPI.instances.append(self)

    def login(self, username: str, password: str):
        self.login_called = True
        if _FakePicnicAPI.require_2fa:
            from python_picnic_api2 import Picnic2FARequired

            raise Picnic2FARequired("2FA required")
        self.session.auth_token = "token-no-2fa"

    def generate_2fa_code(self, channel: str = "SMS"):
        self.generate_calls.append(channel)

    def verify_2fa_code(self, code: str):
        self.verify_calls.append(code)
        if code != _FakePicnicAPI.valid_code:
            from python_picnic_api2 import Picnic2FAError

            raise Picnic2FAError("wrong code")
        self.session.auth_token = "token-after-2fa"


@pytest.fixture(autouse=True)
def patched_picnic_api(monkeypatch, tmp_path):
    """Patch PicnicAPI and redirect token path to a temp file per test."""
    _FakePicnicAPI.instances = []
    _FakePicnicAPI.require_2fa = True
    _FakePicnicAPI.valid_code = "123456"

    import python_picnic_api2

    monkeypatch.setattr(python_picnic_api2, "PicnicAPI", _FakePicnicAPI)

    import app.services.picnic.client as client_mod

    token_path = tmp_path / "picnic_token.json"
    monkeypatch.setattr(client_mod, "TOKEN_CACHE_PATH", token_path)

    # Force settings to have credentials
    monkeypatch.setenv("PICNIC_MAIL", "test@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "secret")
    from app.config import get_settings

    get_settings.cache_clear()
    yield token_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_start_triggers_2fa_and_returns_awaiting(patched_picnic_api):
    session = PicnicLoginSession()
    result = await session.start()
    assert result == "awaiting_2fa"
    assert _FakePicnicAPI.instances[0].login_called is True
    # Token file should NOT yet exist
    assert not patched_picnic_api.exists()


@pytest.mark.asyncio
async def test_start_ok_without_2fa_persists_token(patched_picnic_api):
    _FakePicnicAPI.require_2fa = False
    session = PicnicLoginSession()
    result = await session.start()
    assert result == "ok"
    assert patched_picnic_api.exists()
    assert json.loads(patched_picnic_api.read_text())["token"] == "token-no-2fa"


@pytest.mark.asyncio
async def test_send_code_before_start_raises(patched_picnic_api):
    session = PicnicLoginSession()
    with pytest.raises(PicnicLoginNotInProgress):
        await session.send_code("SMS")


@pytest.mark.asyncio
async def test_verify_before_start_raises(patched_picnic_api):
    session = PicnicLoginSession()
    with pytest.raises(PicnicLoginNotInProgress):
        await session.verify("123456")


@pytest.mark.asyncio
async def test_full_2fa_flow_persists_token(patched_picnic_api):
    session = PicnicLoginSession()
    assert await session.start() == "awaiting_2fa"
    await session.send_code("SMS")
    assert _FakePicnicAPI.instances[0].generate_calls == ["SMS"]
    await session.verify("123456")
    assert patched_picnic_api.exists()
    assert json.loads(patched_picnic_api.read_text())["token"] == "token-after-2fa"


@pytest.mark.asyncio
async def test_wrong_code_raises_invalid_code(patched_picnic_api):
    session = PicnicLoginSession()
    await session.start()
    await session.send_code("SMS")
    with pytest.raises(PicnicLoginInvalidCode):
        await session.verify("000000")
    # Session should still be active so the user can retry with the correct code
    await session.verify("123456")
    assert patched_picnic_api.exists()


@pytest.mark.asyncio
async def test_start_without_credentials_raises(monkeypatch, patched_picnic_api):
    monkeypatch.delenv("PICNIC_MAIL", raising=False)
    monkeypatch.delenv("PICNIC_EMAIL", raising=False)
    monkeypatch.delenv("PICNIC_PASSWORD", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    session = PicnicLoginSession()
    with pytest.raises(PicnicNotConfigured):
        await session.start()


@pytest.mark.asyncio
async def test_start_resets_in_flight_session(patched_picnic_api):
    session = PicnicLoginSession()
    await session.start()
    # Second start should create a fresh api instance
    await session.start()
    assert len(_FakePicnicAPI.instances) == 2
