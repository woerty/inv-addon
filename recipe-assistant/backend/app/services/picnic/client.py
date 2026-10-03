from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from collections.abc import Callable
from typing import Any, Protocol

from app.config import get_settings

log = logging.getLogger("picnic.client")


def _token_path() -> Path:
    """Resolve the Picnic token cache location.

    Defaults to the HA addon's persistent /data dir; PICNIC_TOKEN_PATH (read
    from .env via Settings) overrides it for local dev, where /data is not
    writable. Resolved per-call so tests/env changes take effect immediately.
    """
    return Path(get_settings().picnic_token_path)


class PicnicClientProtocol(Protocol):
    """Minimal interface we use. Lets tests swap in a FakePicnicClient."""

    async def search(self, query: str) -> list[dict[str, Any]]: ...
    async def get_article_by_gtin(self, ean: str) -> dict[str, Any] | None: ...
    async def gtin_picnic_id(self, ean: str) -> str | None: ...
    async def get_deliveries(self) -> list[dict[str, Any]]: ...
    async def get_delivery(self, delivery_id: str) -> dict[str, Any]: ...
    async def get_cart(self) -> dict[str, Any]: ...
    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def get_user(self) -> dict[str, Any]: ...
    async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def clear_cart(self) -> dict[str, Any]: ...
    async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]: ...
    async def get_article(self, article_id: str) -> dict[str, Any]: ...
    async def get_product_page(self, picnic_id: str) -> dict[str, Any]: ...
    async def get_promo_page(self) -> dict[str, Any]: ...
    async def get_delivery_slots(self) -> dict[str, Any]: ...
    async def set_delivery_slot(self, slot_id: str) -> dict[str, Any]: ...
    async def checkout_start(self, mts: int, resolve_key: str | None = None) -> dict[str, Any]: ...
    async def initiate_payment(self, order_id: str) -> dict[str, Any]: ...
    async def get_checkout_status(self, order_id: str) -> dict[str, Any]: ...


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


class PicnicAPIError(Exception):
    """Picnic answered with an error payload ({"error": {"code": ...}}).

    The library returns those like any other response instead of raising, so
    a rejected cart write used to look like a success.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


def save_token(token: str) -> None:
    """Persist the auth token to the token cache path with chmod 600.

    Shared between the runtime PicnicClient (after a successful silent
    re-login) and the web-based PicnicLoginSession (after a successful
    interactive 2FA handshake).
    """
    try:
        path = _token_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"token": token}))
        path.chmod(0o600)
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
    # The library signals a rejected token as PicnicAuthError("Picnic
    # authentication error") -- no "401" in the text -- so match it by name.
    if type(exc).__name__ == "PicnicAuthError":
        return True
    s = str(exc).lower()
    return "401" in s or "unauthor" in s


# python-picnic-api2 >= 2.0 returns pydantic models instead of the raw
# dicts this codebase parses (cart decorators, order lines, PML pages ...).
# Every model keeps the verbatim payload on `.raw`; unwrap at this boundary
# so callers keep receiving exactly what the Picnic API sent.

def _raw(value: Any) -> Any:
    raw = getattr(value, "raw", None)
    return raw if isinstance(raw, dict) else value


def _checked(value: Any) -> dict[str, Any]:
    """Unwrap a response; raise if Picnic answered with an error payload."""
    raw = _raw(value)
    error = raw.get("error") if isinstance(raw, dict) else None
    if isinstance(error, dict) and error.get("code"):
        raise PicnicAPIError(str(error["code"]), str(error.get("message") or ""))
    return raw


def _search_groups(result: Any) -> list[dict[str, Any]]:
    """SearchResult -> the 1.x shape: [{"items": [sellingUnit + sole_article_id]}]."""
    items = getattr(result, "items", None)
    if items is None:
        return result
    hits = []
    for item in items:
        node = item.raw if isinstance(item.raw, dict) else {}
        hits.append({**node.get("sellingUnit", {}), "sole_article_id": item.sole_article_id})
    return [{"items": hits}]


def _article_dict(article: Any) -> dict[str, Any] | None:
    """Article -> the 1.x shape {"id", "name"} (name "<producer> <title>"),
    plus the fields 2.x parses that callers read when present."""
    if article is None or isinstance(article, dict):
        return article
    return {
        "id": article.id,
        "name": article.name,
        "unit_quantity": article.unit_quantity,
        "image_id": article.image_id,
        "description": article.description,
    }


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
        # Set once a fresh login hit 2FA. Every further call would otherwise
        # retry the password login against the dead token; cleared by
        # reset_picnic_client() after the web login flow.
        self._reauth_required = False

    def _load_token(self) -> str | None:
        path = _token_path()
        if path.exists():
            try:
                return json.loads(path.read_text()).get("token")
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
            except PicnicReauthRequired:
                self._reauth_required = True
                raise

            # Persist the (possibly new) token for future runs.
            try:
                token = getattr(self._inner.session, "auth_token", None)
                if token and token != cached_token:
                    self._save_token(token)
            except Exception:
                pass

    async def _call(self, method_name: str, *args, **kwargs) -> Any:
        def _do():
            return getattr(self._inner, method_name)(*args, **kwargs)

        return await self._run(_do)

    async def _run(self, fn: Callable[[], Any]) -> Any:
        """Run a sync library call in a thread, re-logging in once on a rejected token."""
        if self._reauth_required:
            raise PicnicReauthRequired("2FA login required")
        await self._ensure_ready()
        assert self._inner is not None

        try:
            return await asyncio.to_thread(fn)
        except Exception as e:
            if _is_auth_error(e):
                log.info("picnic token rejected, attempting fresh login: %s", e)
                # Invalidate cached token and retry once
                try:
                    _token_path().unlink(missing_ok=True)
                except Exception:
                    pass
                await self._ensure_ready(force_relogin=True)
                return await asyncio.to_thread(fn)
            raise

    async def gtin_picnic_id(self, ean: str) -> str | None:
        """picnic_id for an EAN from Picnic's GTIN redirect alone.

        get_article_by_gtin follows the whole redirect chain and then loads
        and parses the product page; linking needs only the id, which is in
        the resolver's redirect (verified live 2026-10-03):
          picnic.app/<cc>/qr/gtin/<ean> -301-> gtin-resolver -302->
          .../store/storefront/product-detail;id=<picnic_id>  (known EAN)
          .../store/storefront                                (unknown EAN)
        Anything else (429, 5xx, no redirect) raises instead of reading as
        "not on Picnic" -- the library returns None for those.
        """
        country = (get_settings().picnic_country_code or "DE").lower()

        def _resolve() -> str | None:
            from python_picnic_api2.client import _HEADERS

            url = f"https://picnic.app/{country}/qr/gtin/{ean}"
            for _ in range(4):
                r = self._inner.session.get(
                    url, headers=_HEADERS, allow_redirects=False, timeout=15
                )
                location = r.headers.get("Location")
                if not (300 <= r.status_code < 400 and location):
                    raise PicnicAPIError(f"HTTP_{r.status_code}", f"GTIN lookup for {ean}")
                if ";id=" in location:
                    return location.split(";id=", 1)[1].split("&", 1)[0]
                if location.rstrip("/").endswith("/store/storefront"):
                    return None
                url = location
            raise PicnicAPIError("TOO_MANY_REDIRECTS", f"GTIN lookup for {ean}")

        return await self._run(_resolve)

    async def search(self, query: str) -> list[dict[str, Any]]:
        return _search_groups(await self._call("search", query))

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
        result = _article_dict(result)
        if not result:
            return None
        if isinstance(result, dict) and result.get("id") and result.get("name"):
            return result
        return None

    async def get_deliveries(self) -> list[dict[str, Any]]:
        return [_raw(d) for d in await self._call("get_deliveries")]

    async def get_delivery(self, delivery_id: str) -> dict[str, Any]:
        return _checked(await self._call("get_delivery", delivery_id))

    async def get_cart(self) -> dict[str, Any]:
        return _checked(await self._call("get_cart"))

    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        return _checked(await self._call("add_product", picnic_id, count=count))

    async def get_user(self) -> dict[str, Any]:
        return _raw(await self._call("get_user"))

    async def remove_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        return _checked(await self._call("remove_product", picnic_id, count=count))

    async def clear_cart(self) -> dict[str, Any]:
        return _checked(await self._call("clear_cart"))

    async def get_categories(self, depth: int = 0) -> list[dict[str, Any]]:
        return await self._call("get_categories", depth=depth)

    async def get_article(self, article_id: str) -> dict[str, Any]:
        return _article_dict(await self._call("get_article", article_id))

    async def get_product_page(self, picnic_id: str) -> dict[str, Any]:
        """Fetch the raw product-details PML page.

        Mirrors the library's get_article request (Picnic headers +
        show_category_action), but returns the full unparsed page so callers
        can extract data the library drops — e.g. the Bündel-Bonus tiers.
        """
        path = (
            f"/pages/product-details-page-root?id={picnic_id}"
            "&show_category_action=true"
        )
        return await self._call("_get", path, add_picnic_headers=True)

    async def get_promo_page(self) -> dict[str, Any]:
        """Fetch the raw 'Diese Woche im Angebot' PML page (all current offers).

        The library has no offers endpoint; this is the page the app's promo
        section links to. Parsed by app.services.picnic.offers.
        """
        return await self._call("_get", "/pages/promo-page-root", add_picnic_headers=True)

    # ── Slot selection / checkout ──
    # The library has none of these; call the raw Picnic endpoints directly.
    # The flow is set_delivery_slot -> checkout_start -> initiate_payment -> poll
    # get_checkout_status; orchestrated by app.services.picnic.checkout.place_order.

    async def get_delivery_slots(self) -> dict[str, Any]:
        return _raw(await self._call("get_delivery_slots"))

    async def set_delivery_slot(self, slot_id: str) -> dict[str, Any]:
        return await self._call("_post", "/cart/set_delivery_slot", {"slot_id": slot_id})

    async def checkout_start(self, mts: int, resolve_key: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"mts": mts, "oos_article_ids": None}
        if resolve_key:
            data["resolve_key"] = resolve_key
        return await self._call("_post", "/cart/checkout/start", data)

    async def initiate_payment(self, order_id: str) -> dict[str, Any]:
        data = {"order_id": order_id, "app_return_url": "nl.picnic-supermarkt://payment"}
        return await self._call("_post", "/cart/checkout/initiate_payment", data)

    async def get_checkout_status(self, order_id: str) -> dict[str, Any]:
        # Verified live: status is keyed by order_id (the dashed "200-371-1144"
        # form from checkout/start), NOT the payment transaction_id — the latter
        # 404s. Shape: {"checkout_status": "FINISHED", "error": {}}.
        return await self._call("_get", f"/cart/checkout/order/{order_id}/status")


# --- FastAPI dependency ---

_client_singleton: PicnicClient | None = None


def get_picnic_client() -> PicnicClientProtocol:
    """FastAPI dependency. Tests override this via app.dependency_overrides."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = PicnicClient()
    return _client_singleton
