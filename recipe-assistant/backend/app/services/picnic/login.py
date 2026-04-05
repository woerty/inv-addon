"""Interactive Picnic 2FA bootstrap for the web UI.

Unlike setup.py (the CLI bootstrap), this module exposes three async steps
that map to HTTP endpoints. It holds an in-progress PicnicAPI instance across
calls so the login -> generate_2fa_code -> verify_2fa_code handshake works
as a multi-request flow from the browser.

Single-user assumption: the HA addon serves one user, so a module-level
singleton guarded by an asyncio lock is sufficient. No session IDs, no TTL.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from app.config import get_settings
from app.services.picnic.client import (
    PicnicNotConfigured,
    reset_picnic_client,
    save_token,
)

log = logging.getLogger("picnic.login")

LoginStatus = Literal["ok", "awaiting_2fa"]
Channel = Literal["SMS", "EMAIL"]


class PicnicLoginError(Exception):
    """Base for recoverable login-flow errors (bad code, bad state, etc.)."""


class PicnicLoginNotInProgress(PicnicLoginError):
    """Caller invoked send-code or verify without a prior successful start."""


class PicnicLoginInvalidCode(PicnicLoginError):
    """The OTP code was rejected by Picnic (verify_2fa_code raised Picnic2FAError)."""


class PicnicLoginSession:
    """Holds an in-progress PicnicAPI instance across the 2FA handshake.

    State machine:
      idle -> start() -> (ok | awaiting_2fa)
      awaiting_2fa -> send_code(channel) -> awaiting_code
      awaiting_code -> verify(code) -> ok (token persisted, client reset)

    On a successful verify, the token is persisted and the in-memory
    PicnicClient singleton is reset so the next normal API call picks up
    the fresh token. On an invalid code, the session stays active so the
    user can retry with the correct code. Calling start() again resets
    any prior in-flight session.
    """

    def __init__(self) -> None:
        self._api: Any | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> LoginStatus:
        async with self._lock:
            settings = get_settings()
            if not settings.picnic_email or not settings.picnic_password:
                raise PicnicNotConfigured(
                    "PICNIC_MAIL / PICNIC_PASSWORD not set in addon config"
                )

            from python_picnic_api2 import PicnicAPI, Picnic2FARequired

            country = settings.picnic_country_code or "DE"
            email = settings.picnic_email
            password = settings.picnic_password
            # Reset any prior in-flight session so retries always start fresh.
            self._api = None

            def _do_login() -> tuple[LoginStatus, Any]:
                api = PicnicAPI(country_code=country)
                try:
                    api.login(email, password)
                    return "ok", api
                except Picnic2FARequired:
                    return "awaiting_2fa", api

            status, api = await asyncio.to_thread(_do_login)

            if status == "ok":
                self._finalize(api)
                return "ok"

            # 2FA path: keep the api instance around for the next step.
            self._api = api
            return "awaiting_2fa"

    async def send_code(self, channel: Channel) -> None:
        async with self._lock:
            if self._api is None:
                raise PicnicLoginNotInProgress(
                    "no login in progress; call start() first"
                )
            api = self._api
            await asyncio.to_thread(api.generate_2fa_code, channel=channel)

    async def verify(self, code: str) -> None:
        async with self._lock:
            if self._api is None:
                raise PicnicLoginNotInProgress(
                    "no login in progress; call start() first"
                )
            api = self._api

            from python_picnic_api2 import Picnic2FAError

            try:
                await asyncio.to_thread(api.verify_2fa_code, code)
            except Picnic2FAError as e:
                # Keep the session active so the user can retry with the
                # correct code without having to redo start + send_code.
                raise PicnicLoginInvalidCode(f"invalid 2FA code: {e}") from e

            self._finalize(api)

    def _finalize(self, api: Any) -> None:
        """Persist the token from a successfully authenticated session and reset state."""
        token = getattr(api.session, "auth_token", None)
        if not token:
            # Login reported success but we can't find a token - shouldn't happen
            # with python-picnic-api2 but we fail loudly rather than silently.
            self._api = None
            raise RuntimeError("login succeeded but no auth_token in session")
        save_token(token)
        reset_picnic_client()
        self._api = None
        log.info("picnic login succeeded, token persisted")


# Module-level singleton
_session_singleton: PicnicLoginSession | None = None


def get_login_session() -> PicnicLoginSession:
    """FastAPI dependency. Tests override via app.dependency_overrides."""
    global _session_singleton
    if _session_singleton is None:
        _session_singleton = PicnicLoginSession()
    return _session_singleton


def reset_login_session() -> None:
    """Test helper: clear the singleton so each test starts fresh."""
    global _session_singleton
    _session_singleton = None
