"""Link to ass3, Dustin's agent server: the add-on calls out, never in.

Long-polls ass3 for commands, runs only the whitelist below and posts each
result; pushes its state (inventory, restock rules, Picnic cart and open
orders) as a snapshot. Nothing in the add-on listens for ass3, and checkout
is not on the list: a compromised ass3 can at most take items out of the
inventory and change the Picnic cart.

Spec: ass3 repo, docs/superpowers/specs/2026-10-05-inventory-link-design.md.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Annotated, Any, TypeVar

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError
from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.database import async_session
from app.models.inventory import InventoryItem
from app.models.log import InventoryLog
from app.models.tracked_product import TrackedProduct
from app.services.inventory_ops import scan_out_one
from app.services.picnic.cart import cart_from_raw, selected_slot_window
from app.services.picnic.catalog import image_urls_by_ean, picnic_image_url, search_products
from app.services.picnic.client import (
    PicnicAPIError,
    PicnicClientProtocol,
    PicnicNotConfigured,
    PicnicReauthRequired,
    get_picnic_client,
)
from app.services.picnic.ean_links import linked_quantity
from app.services.picnic.orders import parse_pending_orders

log = logging.getLogger("ass3_link")

PREFIX = "/api/inventory-link"
POLL_WAIT_S = 50
POLL_TIMEOUT_S = 65
# An empty poll that came back this fast means ass3 didn't hold it open;
# don't spin.
MIN_EMPTY_POLL_S = 2
REQUEST_TIMEOUT_S = 15
FINGERPRINT_EVERY_S = 15
INVENTORY_PUSH_MAX_AGE_S = 5 * 60
PICNIC_PUSH_EVERY_S = 30 * 60
# Picnic blocks accounts on bursts. Live cart/order fetches for a snapshot
# are at least this far apart, whatever asks for them (refresh, cart
# commands), and Picnic commands are capped per window, so a looping or
# compromised ass3 can't make the add-on hammer Picnic.
PICNIC_FETCH_MIN_GAP_S = 60
PICNIC_COMMANDS_PER_WINDOW = 40
PICNIC_COMMAND_WINDOW_S = 10 * 60
SEARCH_LIMIT = 8
HISTORY_WINDOW = timedelta(hours=48)
HISTORY_LIMIT = 300

T = TypeVar("T")


def is_enabled(settings: Settings) -> bool:
    return bool(settings.ass3_url.strip() and settings.ass3_token.strip())


def backoff_delay(failures: int) -> float:
    """Wait after the n-th failure in a row: 5 s, doubling, at most 60 s."""
    return float(min(5 * 2 ** min(max(failures - 1, 0), 4), 60))


# ── Commands ──────────────────────────────────────────────────────────────

Count = Annotated[int, Field(ge=1, le=20)]
Ident = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ScanOutArgs(_Args):
    barcode: Ident
    count: Count


class CartArgs(_Args):
    picnic_id: Ident
    count: Count


class SearchArgs(_Args):
    q: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RefreshArgs(_Args):
    pass


class CommandError(Exception):
    """Ends a command with ok=false and this short reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _expires_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CommandError("bad_args")
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        raise CommandError("bad_args") from None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


# ── Snapshot ──────────────────────────────────────────────────────────────

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


# Quantity formats the code writes into `details`. Read only for entries
# without quantity_before/after (written before migration 012).
_QUANTITY_DETAILS = (
    (re.compile(r"quantity: (-?\d+) → (-?\d+)"), 1, 2),  # add, remove, scan-out, update, delete
    (re.compile(r"qty → (-?\d+)"), None, 1),  # scan-in
    (re.compile(r"qty→(-?\d+), cart delta=\d+"), None, 1),  # restock_auto: stock at the time
)
_FIXED_DETAILS = {"removed last item": (None, 0), "new item": (0, 1)}


def quantities_from_details(details: str | None) -> tuple[int | None, int | None]:
    """(before, after) from a log entry's details; None where it doesn't say."""
    if not details:
        return None, None
    if details in _FIXED_DETAILS:
        return _FIXED_DETAILS[details]
    for pattern, before, after in _QUANTITY_DETAILS:
        match = pattern.fullmatch(details)
        if match:
            return (int(match.group(before)) if before else None), int(match.group(after))
    return None, None


async def build_history(db: AsyncSession, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Inventory log of the last 48 h, newest first, at most 300 entries.

    inventory_log.timestamp is a naive DateTime filled by the database's
    now(), so which zone it is in depends on the database:
    - Postgres (the add-on) stores now() into a timestamp-without-time-zone
      column as local time of the session TimeZone. asyncpg doesn't set one,
      so it is the server's `timezone` from postgresql.conf, which initdb
      (run.sh, first start) took from the container's TZ -- the Supervisor
      sets that to Home Assistant's zone, e.g. Europe/Berlin; without TZ it
      would be /etc/localtime (UTC in the image). Checked on Postgres 16:
      TZ=Europe/Berlin initdb, insert at 19:08 UTC stores 21:08. So the
      database converts back with its own setting rather than us guessing:
      timezone(current_setting('TimeZone'), timestamp).
    - SQLite (dev, tests) fills it with CURRENT_TIMESTAMP, which is UTC.
    """
    cutoff = (now or datetime.now(UTC)) - HISTORY_WINDOW
    if db.bind.dialect.name == "postgresql":
        logged_at = func.timezone(
            func.current_setting("TimeZone"), InventoryLog.timestamp, type_=DateTime(timezone=True)
        )
    else:
        logged_at = InventoryLog.timestamp
        cutoff = cutoff.replace(tzinfo=None)
    rows = (
        await db.execute(
            select(InventoryLog, logged_at, InventoryItem.name)
            .outerjoin(InventoryItem, InventoryItem.barcode == InventoryLog.barcode)
            .where(logged_at >= cutoff)
            .order_by(InventoryLog.timestamp.desc(), InventoryLog.id.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all()
    history = []
    for entry, at, current_name in rows:
        before, after = entry.quantity_before, entry.quantity_after
        if before is None and after is None:
            before, after = quantities_from_details(entry.details)
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        history.append(
            {
                "id": entry.id,
                "at": at.astimezone(UTC).isoformat(timespec="seconds"),
                "barcode": entry.barcode,
                # Kept on the entry, so a scanned-out-and-deleted item keeps its name.
                "name": entry.name or current_name,
                "action": entry.action,
                "details": entry.details,
                "quantity_before": before,
                "quantity_after": after,
            }
        )
    return history


async def build_snapshot(db: AsyncSession) -> dict[str, Any]:
    """Inventory, restock rules and recent history; cart and orders are
    added by the caller."""
    items = (
        await db.execute(
            select(InventoryItem)
            .options(selectinload(InventoryItem.storage_location))
            .order_by(InventoryItem.name)
        )
    ).scalars().all()
    images = await image_urls_by_ean(db, [i.barcode for i in items])
    rules = (await db.execute(select(TrackedProduct).order_by(TrackedProduct.name))).scalars().all()
    # Counted like the restock check: own barcode plus every EAN stored as
    # linked to the rule's Picnic product (no live lookup).
    current = {r.barcode: await linked_quantity(db, r) for r in rules}
    return {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "inventory": [
            {
                "barcode": i.barcode,
                "name": i.name,
                "quantity": i.quantity,
                "category": i.category,
                "location": i.storage_location.name if i.storage_location else None,
                "expiration_date": i.expiration_date.isoformat() if i.expiration_date else None,
                # Picnic image wins, like the inventory list in the add-on.
                "image_url": images.get(i.barcode) or i.image_url,
            }
            for i in items
        ],
        "rules": [
            {
                "barcode": r.barcode,
                "name": r.name,
                "min_quantity": r.min_quantity,
                # The level a restock fills up to, not an order amount.
                "restock_quantity": r.target_quantity,
                "picnic_id": r.picnic_id,
                "current": current[r.barcode],
            }
            for r in rules
        ],
        "history": await build_history(db),
    }


def cart_payload(raw: dict[str, Any]) -> dict[str, Any]:
    cart = cart_from_raw(raw)
    window = selected_slot_window(raw)
    return {
        "items": [
            {"picnic_id": i.picnic_id, "name": i.name, "count": i.quantity, "price_cents": i.price_cents}
            for i in cart.items
        ],
        "total_cents": cart.total_price_cents,
        "slot": {"start": window[0], "end": window[1]} if window else None,
    }


async def orders_payload(client: PicnicClientProtocol) -> list[dict[str, Any]]:
    pending = await parse_pending_orders(client)
    return [
        {
            "id": o.delivery_id,
            "status": o.status,
            "slot_start": _iso(o.delivery_time),
            "slot_end": _iso(o.delivery_time_end),
            "items_count": o.total_items,
            "total_cents": o.total_price_cents,
        }
        for o in pending.orders
    ]


# ── Failures and logging ──────────────────────────────────────────────────

class Unauthorized(Exception):
    """ass3 refused the token (401, or 403 as its token endpoints answer)."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


def _describe(exc: Exception) -> str:
    if isinstance(exc, Unauthorized):
        return f"ass3 rejected the token ({exc.status}) - check the ass3_token add-on option"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"ass3 answered HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "ass3 timed out"
    if isinstance(exc, httpx.TransportError):
        return f"ass3 unreachable ({type(exc).__name__})"
    return f"{type(exc).__name__}: {exc}"


class _Failures:
    """Failures in a row of one loop. Logs a failure only when it differs
    from the previous one, so a long outage is one line, not one per retry."""

    def __init__(self, what: str) -> None:
        self.what = what
        self.count = 0
        self._last: str | None = None

    def failed(self, exc: Exception) -> float:
        self.count += 1
        message = _describe(exc)
        if message != self._last:
            self._last = message
            known = isinstance(exc, (Unauthorized, httpx.HTTPError))
            level = logging.ERROR if isinstance(exc, Unauthorized) else logging.WARNING
            log.log(level, "%s failed: %s; retrying with backoff", self.what, message, exc_info=not known)
        return backoff_delay(self.count)

    def succeeded(self) -> None:
        if self.count:
            log.info("%s works again after %d failed attempts", self.what, self.count)
        self.count = 0
        self._last = None


# ── The link ──────────────────────────────────────────────────────────────

class Ass3Link:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], AsyncSession] = async_session,
        picnic_factory: Callable[[], PicnicClientProtocol] = get_picnic_client,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sessions = session_factory
        self._picnic_factory = picnic_factory
        self._picnic_enabled = bool(settings.picnic_email and settings.picnic_password)
        self._clock = clock
        self._http = httpx.AsyncClient(
            base_url=settings.ass3_url.strip().rstrip("/"),
            headers={"Authorization": f"Bearer {settings.ass3_token.strip()}"},
            transport=transport,
        )
        self._push_lock = asyncio.Lock()
        # Cart/orders read from Picnic but not delivered to ass3 yet; they
        # ride along with the next snapshot instead of being fetched again.
        self._pending_picnic: dict[str, Any] = {}
        self._last_picnic_fetch: float | None = None
        self._picnic_commands: deque[float] = deque()
        self._poll_failures = _Failures("command poll")
        self._snapshot_failures = _Failures("snapshot push")
        self._commands: dict[str, tuple[type[_Args], Callable[[Any], Awaitable[dict[str, Any]]]]] = {
            "scan_out": (ScanOutArgs, self._scan_out),
            "cart_add": (CartArgs, partial(self._cart, add=True)),
            "cart_remove": (CartArgs, partial(self._cart, add=False)),
            "picnic_search": (SearchArgs, self._search),
            "refresh": (RefreshArgs, self._refresh),
        }

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(self) -> None:
        try:
            await asyncio.gather(self._poll_loop(), self._snapshot_loop())
        finally:
            await self.aclose()

    async def _request(self, method: str, path: str, *, timeout: float = REQUEST_TIMEOUT_S, **kwargs: Any) -> httpx.Response:
        response = await self._http.request(method, PREFIX + path, timeout=timeout, **kwargs)
        if response.status_code in (401, 403):
            raise Unauthorized(response.status_code)
        response.raise_for_status()
        return response

    # ── Commands ──

    async def _poll_loop(self) -> None:
        while True:
            started = self._clock()
            try:
                count = await self.poll_once()
            except Exception as exc:
                await asyncio.sleep(self._poll_failures.failed(exc))
                continue
            self._poll_failures.succeeded()
            rest = MIN_EMPTY_POLL_S - (self._clock() - started)
            if count == 0 and rest > 0:
                await asyncio.sleep(rest)

    async def poll_once(self) -> int:
        """One long-poll: run what came in, in order, and post each result.
        Returns how many commands came.

        A failed result post raises and drops the rest of the batch: better
        unexecuted (ass3 reports "no answer") than executed unreported."""
        response = await self._request(
            "GET", "/commands", params={"wait": POLL_WAIT_S}, timeout=POLL_TIMEOUT_S
        )
        commands = response.json().get("commands") or []
        cart_changed = False
        for command in commands:
            result = await self.execute(command)
            if result is None:
                continue
            await self._request("POST", "/results", json=result)
            if result["ok"] and command.get("action") in ("cart_add", "cart_remove"):
                cart_changed = True
        if cart_changed:
            await self._push_quietly(picnic=True)
        return len(commands)

    async def execute(self, command: Any) -> dict[str, Any] | None:
        """Run one command; the result to post, or None if it has no id."""
        cmd_id = command.get("id") if isinstance(command, dict) else None
        if not isinstance(cmd_id, str) or not cmd_id:
            log.warning("command without id ignored: %r", command)
            return None
        action = command.get("action")
        args: Any = command.get("args") or {}
        try:
            if datetime.now(UTC) > _expires_at(command.get("expires_at")):
                raise CommandError("expired")
            if not isinstance(action, str) or action not in self._commands:
                raise CommandError("unknown_action")
            model, run = self._commands[action]
            try:
                parsed = model.model_validate(args)
            except ValidationError:
                raise CommandError("bad_args") from None
            data = await run(parsed)
        except CommandError as e:
            result: dict[str, Any] = {"id": cmd_id, "ok": False, "error": e.reason}
        except Exception:
            log.exception("command %s %s crashed", action, cmd_id)
            result = {"id": cmd_id, "ok": False, "error": "internal_error"}
        else:
            result = {"id": cmd_id, "ok": True, "data": data}
        log.info(
            "command %s %s %s: %s", cmd_id, action, args, "ok" if result["ok"] else result["error"]
        )
        return result

    def _picnic_or_none(self) -> PicnicClientProtocol | None:
        try:
            return self._picnic_factory()
        except Exception:
            return None

    async def _scan_out(self, args: ScanOutArgs) -> dict[str, Any]:
        """`count` scanner scan-outs, stopping when the item is gone. The
        restock check runs on the last one only: one Picnic round instead of
        one per unit, and it tops up to the same level."""
        async with self._sessions() as db:
            item = (
                await db.execute(select(InventoryItem).where(InventoryItem.barcode == args.barcode))
            ).scalar_one_or_none()
            if item is None:
                raise CommandError("not_found")
            name, quantity = item.name, max(item.quantity, 0)
            steps = min(args.count, quantity)
            picnic = self._picnic_or_none()
            removed = 0
            for step in range(steps):
                result = await scan_out_one(
                    db, args.barcode, picnic_client=picnic, restock=step == steps - 1
                )
                if result is None:  # deleted meanwhile, e.g. by the scanner
                    quantity = 0
                    break
                await db.commit()
                removed += 1
                quantity = result.remaining_quantity
        return {"barcode": args.barcode, "name": name, "quantity": quantity, "removed": removed}

    def _take_picnic_slot(self) -> None:
        """Admit one Picnic command, or refuse it (not configured, too many)."""
        if not self._picnic_enabled:
            raise CommandError("picnic_not_configured")
        now = self._clock()
        while self._picnic_commands and now - self._picnic_commands[0] >= PICNIC_COMMAND_WINDOW_S:
            self._picnic_commands.popleft()
        if len(self._picnic_commands) >= PICNIC_COMMANDS_PER_WINDOW:
            raise CommandError("rate_limited")
        self._picnic_commands.append(now)

    async def _with_picnic(self, call: Callable[[PicnicClientProtocol], Awaitable[T]]) -> T:
        """Run a Picnic call; its failure ends the command with a short reason."""
        try:
            return await call(self._picnic_factory())
        except PicnicNotConfigured:
            raise CommandError("picnic_not_configured") from None
        except PicnicReauthRequired:
            raise CommandError("picnic_login_required") from None
        except PicnicAPIError as e:
            raise CommandError(f"picnic_rejected: {e.message or e.code}"[:120]) from None
        except Exception:
            log.warning("Picnic call for ass3 failed", exc_info=True)
            raise CommandError("picnic_error") from None

    async def _cart(self, args: CartArgs, *, add: bool) -> dict[str, Any]:
        self._take_picnic_slot()
        if add:
            await self._with_picnic(lambda c: c.add_product(args.picnic_id, count=args.count))
        else:
            await self._with_picnic(lambda c: c.remove_product(args.picnic_id, count=args.count))
        try:
            raw = await self._with_picnic(lambda c: c.get_cart())
        except CommandError:
            # Not a plain failure: a retry would change the cart twice.
            raise CommandError("cart_changed_but_unreadable") from None
        cart = cart_payload(raw)
        self._pending_picnic["cart"] = cart
        return cart

    async def _search(self, args: SearchArgs) -> dict[str, Any]:
        self._take_picnic_slot()
        async with self._sessions() as db:
            hits = await self._with_picnic(
                lambda client: search_products(db, client, args.q, limit=SEARCH_LIMIT)
            )
            await db.commit()  # search_products caches the hits in the catalog
        return {
            "results": [
                {
                    "picnic_id": h.picnic_id,
                    "name": h.name,
                    "unit_quantity": h.unit_quantity,
                    "price_cents": h.price_cents,
                    "image_url": picnic_image_url(h.image_id) if h.image_id else None,
                }
                for h in hits
            ]
        }

    async def _refresh(self, _args: RefreshArgs) -> dict[str, Any]:
        try:
            await self.push_snapshot(picnic=True)
        except Exception as exc:
            log.warning("refresh: snapshot push failed: %s", _describe(exc))
            raise CommandError("snapshot_failed") from None
        return {}

    # ── Snapshots ──

    def _picnic_fetch_due(self, gap_s: float) -> bool:
        return self._last_picnic_fetch is None or self._clock() - self._last_picnic_fetch >= gap_s

    async def _fetch_picnic(self) -> dict[str, Any]:
        """Cart and open orders, live. Empty when Picnic isn't logged in or
        the cart is unreadable (then orders aren't tried either)."""
        client = self._picnic_factory()
        try:
            state: dict[str, Any] = {"cart": cart_payload(await client.get_cart())}
        except (PicnicNotConfigured, PicnicReauthRequired):
            return {}
        except Exception:
            log.warning("Picnic cart for the ass3 snapshot unreadable", exc_info=True)
            return {}
        try:
            state["orders"] = await orders_payload(client)
        except Exception:
            log.warning("Picnic orders for the ass3 snapshot unreadable", exc_info=True)
        return state

    async def push_snapshot(self, *, picnic: bool = False) -> None:
        """Push inventory and rules; with picnic=True also cart and open
        orders read live, unless the last live read is under a minute old."""
        async with self._push_lock:
            if picnic and self._picnic_enabled and self._picnic_fetch_due(PICNIC_FETCH_MIN_GAP_S):
                self._last_picnic_fetch = self._clock()
                self._pending_picnic.update(await self._fetch_picnic())
            async with self._sessions() as db:
                payload = await build_snapshot(db)
            sent = dict(self._pending_picnic)
            payload.update(sent)
            await self._request("POST", "/snapshot", json=payload)
            for key, value in sent.items():
                # A cart command may have replaced it while this was in flight.
                if self._pending_picnic.get(key) is value:
                    del self._pending_picnic[key]

    async def _push_quietly(self, *, picnic: bool) -> None:
        """Push from the poll loop: a failure is logged, never raised; what
        wasn't delivered goes with the snapshot loop's next push."""
        try:
            await self.push_snapshot(picnic=picnic)
        except Exception as exc:
            self._snapshot_failures.failed(exc)
        else:
            self._snapshot_failures.succeeded()

    async def _fingerprint(self) -> tuple[Any, ...]:
        """Changes whenever the inventory or the rules do; one query."""
        async with self._sessions() as db:
            row = (
                await db.execute(
                    select(
                        func.count(InventoryItem.id),
                        func.max(InventoryItem.updated_date),
                        func.sum(InventoryItem.quantity),
                        select(func.count()).select_from(TrackedProduct).scalar_subquery(),
                        select(func.max(TrackedProduct.updated_at)).scalar_subquery(),
                    )
                )
            ).one()
        return tuple(row)

    async def _snapshot_loop(self) -> None:
        last_fingerprint: tuple[Any, ...] | None = None
        last_push: float | None = None
        while True:
            try:
                fingerprint = await self._fingerprint()
                picnic_due = self._picnic_enabled and self._picnic_fetch_due(PICNIC_PUSH_EVERY_S)
                if (
                    fingerprint != last_fingerprint
                    or last_push is None
                    or self._clock() - last_push >= INVENTORY_PUSH_MAX_AGE_S
                    or picnic_due
                    or self._pending_picnic
                ):
                    await self.push_snapshot(picnic=picnic_due)
                    last_fingerprint, last_push = fingerprint, self._clock()
            except Exception as exc:
                await asyncio.sleep(self._snapshot_failures.failed(exc))
                continue
            self._snapshot_failures.succeeded()
            await asyncio.sleep(FINGERPRINT_EVERY_S)


def _ensure_log_output() -> None:
    """The add-on configures no handler for app loggers (only uvicorn's), so
    give this one its own; every command then shows in the add-on log."""
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s ass3_link: %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        log.propagate = False


def start_ass3_link(settings: Settings) -> asyncio.Task[None] | None:
    """Start the link as a background task, or None when it is off."""
    if not is_enabled(settings):
        return None
    _ensure_log_output()
    log.info("link to %s on", settings.ass3_url.strip())
    return asyncio.create_task(Ass3Link(settings).run(), name="ass3_link")
