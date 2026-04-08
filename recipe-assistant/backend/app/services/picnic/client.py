from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings

log = logging.getLogger("picnic.client")

TOKEN_CACHE_PATH = Path("/data/picnic_token.json")


class PicnicClientProtocol(Protocol):
    """Minimal interface we use. Lets tests swap in a FakePicnicClient."""

    async def search(self, query: str) -> list[dict[str, Any]]: ...
    async def get_article_by_gtin(self, ean: str) -> dict[str, Any] | None: ...
    async def get_deliveries(self) -> list[dict[str, Any]]: ...
    async def get_delivery(self, delivery_id: str) -> dict[str, Any]: ...
    async def get_cart(self) -> dict[str, Any]: ...
    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def get_user(self) -> dict[str, Any]: ...
    async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def clear_cart(self) -> dict[str, Any]: ...
    async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]: ...
    async def get_article(self, article_id: str) -> dict[str, Any]: ...


class PicnicNotConfigured(Exception):
    """Raised when credentials are absent from addon config."""


class PicnicReauthRequired(Exception):
    """Raised when the cached token is invalid/missing and a fresh login triggers 2FA.

    Recovery paths:
      - The web UI login flow (POST /api/picnic/login/start -> send-code -> verify),
        which drives app.services.picnic.login.PicnicLoginSession.
      - The CLI bootstrap `python -m app.services.picnic.setup` as a fallback for
        headless environments.

    The HTTP layer surfaces this on the runtime code paths as a 503 with
    {"error": "picnic_reauth_required"}, and on /status it sets
    needs_login=True so the frontend can render the login screen.
    """


def save_token(token: str) -> None:
    """Persist the auth token to TOKEN_CACHE_PATH with chmod 600.

    Shared between the runtime PicnicClient (after a successful silent
    re-login) and the web-based PicnicLoginSession (after a successful
    interactive 2FA handshake).
    """
    try:
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(json.dumps({"token": token}))
        TOKEN_CACHE_PATH.chmod(0o600)
    except Exception as e:
        log.warning("could not persist picnic token: %s", e)


def reset_picnic_client() -> None:
    """Force the runtime PicnicClient singleton to rebuild on next use.

    Called after a successful fresh login (web flow) so the next
    /api/picnic/* call picks up the new token instead of the stale
    in-memory instance.
    """
    global _client_singleton
    _client_singleton = None


def _is_auth_error(exc: Exception) -> bool:
    s = str(exc).lower()
    return "401" in s or "unauthor" in s


class PicnicClient:
    """Thin async wrapper around python-picnic-api2 (which is sync).

    Token lifecycle:
      1. On first call, loads cached token from /data/picnic_token.json if present.
      2. If token works (any API call returns cleanly), keep using it.
      3. If token is missing or fails with 401, attempt a username+password login.
      4. If that login raises Picnic2FARequired, surface as PicnicReauthRequired
         (user must run setup CLI). We never try SMS flow from the HTTP path.
    """

    def __init__(self) -> None:
        self._inner = None
        self._lock = asyncio.Lock()

    def _load_token(self) -> str | None:
        if TOKEN_CACHE_PATH.exists():
            try:
                return json.loads(TOKEN_CACHE_PATH.read_text()).get("token")
            except Exception:
                return None
        return None

    def _save_token(self, token: str) -> None:
        # Delegate to the module-level helper so there's one canonical
        # implementation shared with PicnicLoginSession.
        save_token(token)

    async def _ensure_ready(self, force_relogin: bool = False) -> None:
        if self._inner is not None and not force_relogin:
            return
        async with self._lock:
            if self._inner is not None and not force_relogin:
                return

            from python_picnic_api2 import PicnicAPI, Picnic2FARequired

            settings = get_settings()
            country = settings.picnic_country_code or "DE"

            cached_token = None if force_relogin else self._load_token()

            def _build() -> Any:
                if cached_token:
                    return PicnicAPI(country_code=country, auth_token=cached_token)
                if not settings.picnic_email or not settings.picnic_password:
                    raise PicnicNotConfigured("PICNIC_MAIL / PICNIC_PASSWORD not set")
                api = PicnicAPI(country_code=country)
                try:
                    api.login(settings.picnic_email, settings.picnic_password)
                except Picnic2FARequired as e:
                    raise PicnicReauthRequired(
                        "2FA required - run `python -m app.services.picnic.setup` once"
                    ) from e
                return api

            try:
                self._inner = await asyncio.to_thread(_build)
            except (PicnicNotConfigured, PicnicReauthRequired):
                raise

            # Persist the (possibly new) token for future runs.
            try:
                token = getattr(self._inner.session, "auth_token", None)
                if token and token != cached_token:
                    self._save_token(token)
            except Exception:
                pass

    async def _call(self, method_name: str, *args, **kwargs) -> Any:
        await self._ensure_ready()
        assert self._inner is not None

        def _do():
            return getattr(self._inner, method_name)(*args, **kwargs)

        try:
            return await asyncio.to_thread(_do)
        except Exception as e:
            if _is_auth_error(e):
                log.info("picnic token rejected, attempting fresh login: %s", e)
                # Invalidate cached token and retry once
                try:
                    TOKEN_CACHE_PATH.unlink(missing_ok=True)
                except Exception:
                    pass
                await self._ensure_ready(force_relogin=True)
                return await asyncio.to_thread(_do)
            raise

    async def search(self, query: str) -> list[dict[str, Any]]:
        return await self._call("search", query)

    async def get_article_by_gtin(self, ean: str) -> dict[str, Any] | None:
        """Look up a Picnic product by EAN/GTIN.

        Returns a dict with at least {"id", "name"} on hit, or None on miss.
        The underlying library may return an error-shaped dict or raise on miss;
        normalise both to None here.
        """
        try:
            result = await self._call("get_article_by_gtin", ean)
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "404" in msg:
                log.debug("get_article_by_gtin miss for %s: %s", ean, e)
                return None
            raise
        if not result:
            return None
        if isinstance(result, dict) and result.get("id") and result.get("name"):
            return result
        return None

    async def get_deliveries(self) -> list[dict[str, Any]]:
        return await self._call("get_deliveries")

    async def get_delivery(self, delivery_id: str) -> dict[str, Any]:
        return await self._call("get_delivery", delivery_id)

    async def get_cart(self) -> dict[str, Any]:
        return await self._call("get_cart")

    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        return await self._call("add_product", picnic_id, count=count)

    async def get_user(self) -> dict[str, Any]:
        return await self._call("get_user")

    async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        return await self._call("remove_product", picnic_id, count=count)

    async def clear_cart(self) -> dict[str, Any]:
        return await self._call("clear_cart")

    async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]:
        return await self._call("get_categories", depth=depth)

    async def get_article(self, article_id: str) -> dict[str, Any]:
        return await self._call("get_article", article_id)


# --- FastAPI dependency ---

_client_singleton: PicnicClient | None = None


def get_picnic_client() -> PicnicClientProtocol:
    """FastAPI dependency. Tests override this via app.dependency_overrides."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = PicnicClient()
    return _client_singleton
