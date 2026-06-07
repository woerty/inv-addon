# Picnic Ordering Flow — Design

**Date:** 2026-06-07
**Status:** Approved (design), pending implementation plan

## Goal

Reach feature parity with the Picnic app for the last missing piece:
**selecting a delivery slot and placing an order**. A sibling effort builds the
offers page; this spec covers only the ordering/slot flow.

Scope (confirmed): **slot selection + placing the order** only. Out of scope for
this iteration: a dedicated minimum-order-value warning feature, cancelling a
placed order, and changing the slot of an already-placed order. (The MOV value is
still used passively to disable the order button — see below.)

## Background: ground-truthed API

`python-picnic-api2` v1.3.4 only exposes `get_delivery_slots()`
(`GET /cart/delivery_slots`). Slot selection, checkout and payment are **absent**
and must be called as raw `_post`/`_get` requests (like `add_product` already is).

Endpoints (verified read-only against the live account + cross-checked against the
MRVDH/picnic-api Node wrapper and simonmartyr/picnic-api Go wrapper):

1. `POST /cart/set_delivery_slot` body `{"slot_id": "..."}` → returns updated Cart; reserves the slot.
2. `POST /cart/checkout/start` body `{"mts": <cart.mts>, "oos_article_ids": null}` →
   `{order_id, total_price, transaction_expiry, total_count, ...}`. On issues
   (e.g. alcohol) returns a CheckoutError carrying a `resolve_key`; retry with
   `"resolve_key": "age_verified"`.
3. `POST /cart/checkout/initiate_payment` body `{"order_id", "app_return_url"}` →
   may return `issuer_authentication_url` (3DS) for card accounts; SEPA/auto-pay
   (typical DE accounts) auto-completes.
4. `GET /cart/checkout/{transaction_id}/status` → poll until `checkout_status == "FINISHED"`.

`mts` and `state_token` are already present in the live cart payload.

**Risk:** steps 2–4 (especially `initiate_payment`) are genuinely irreversible
writes that could not be tested under the read-only investigation constraint. The
single real end-to-end write test is performed by the account owner during
implementation. See the memory note `reference_picnic_order_endpoints`.

## Architecture decision

**Orchestrated checkout (chosen)** over stepwise endpoints. A single
`POST /cart/checkout` performs `checkout/start → initiate_payment → status-poll`
server-side and returns success/failure. The irreversible multi-step sequence is
encapsulated in one place; the frontend stays simple. Stepwise endpoints were
rejected as needless frontend complexity (the client would have to drive polling
and the resolve_key retry itself).

## Components

### Backend (`recipe-assistant/backend/app/`)

**`services/picnic/client.py`** — new methods on `PicnicClient` and the
`PicnicClientProtocol`, all via raw `_get`/`_post`:
- `get_delivery_slots()` → `GET /cart/delivery_slots`
- `set_delivery_slot(slot_id)` → `POST /cart/set_delivery_slot {"slot_id"}`
- `checkout_start(mts, resolve_key=None)` → `POST /cart/checkout/start`
- `initiate_payment(order_id)` → `POST /cart/checkout/initiate_payment`
- `get_checkout_status(transaction_id)` → `GET /cart/checkout/{id}/status`

**`services/picnic/checkout.py`** (new):
- `parse_delivery_slots(client) -> DeliverySlotsResponse` — fetch slots, group by
  day, expose `selected`/`reserved`/`minimum_order_value`/window times.
- `place_order(client) -> OrderPlacedResult` — read `mts` from the cart →
  `checkout_start` (retry once with `resolve_key="age_verified"` on a resolvable
  CheckoutError) → `initiate_payment` → poll `get_checkout_status` until `FINISHED`
  or a bounded timeout. If `issuer_authentication_url` is returned (3DS / non-SEPA),
  raise a clear error ("Bitte in der Picnic-App abschließen") rather than leaving a
  half-placed state.

**`routers/picnic.py`** — new endpoints (transaction boundary / error mapping as
the module already documents):
- `GET /cart/delivery-slots` → `DeliverySlotsResponse`
- `POST /cart/slot` body `{slot_id}` → updated `CartResponse`
- `POST /cart/checkout` → `OrderPlacedResult`
- Error mapping: MOV-below / checkout failure → 409 with a clear German message;
  `PicnicReauthRequired` → 503 as elsewhere.

**`schemas/picnic.py`** — `DeliverySlot`, `DeliverySlotsResponse`,
`OrderPlacedResult`.

### Frontend (`recipe-assistant/frontend/src/`)

**`components/picnic/cart/SlotPicker.tsx`** (new) — slots grouped by day, radio
selection; selecting calls `POST /cart/slot`. Shows window start–end and marks the
currently reserved slot.

**`components/picnic/cart/CartTab.tsx`** — below the existing total footer: render
`SlotPicker` + a **"Jetzt bestellen"** button. The button is **disabled** while no
slot is selected or the cart total is below the selected slot's
`minimum_order_value` (reuses data already in the slot payload — no separate MOV
feature). Click → confirmation dialog ("Verbindlich bestellen für X €?") →
`POST /cart/checkout` → on success: snackbar + reload cart and orders.

**`hooks/usePicnicCart.ts`, `api/client.ts`, `types/index.ts`** — load slots, set
slot, place order; matching TypeScript types.

## Data flow

show cart → load slots (`GET /cart/delivery-slots`) → select slot
(`POST /cart/slot`) → "Jetzt bestellen" → confirm dialog →
`POST /cart/checkout` (server orchestrates start/pay/poll) → success → the new
order appears in the Bestellungen tab.

## Error handling & safety

- Double confirmation before the irreversible checkout call.
- `checkout/start` below MOV → 409; the button is already disabled (defense in depth).
- 3DS / non-SEPA payment → clean error instead of a half-placed state.
- The one real end-to-end write test is run by the account owner; it was never
  executed during the read-only investigation.

## Testing (TDD)

- Backend: extend `FakePicnicClient` with the new methods; `test_checkout.py`
  covering `parse_delivery_slots` (day grouping, MOV, selected flag) and
  `place_order` (happy path, MOV error, resolve_key retry, 3DS error, poll timeout).
- Frontend: lightweight tests in the existing style for `SlotPicker` and the
  order button enabled/disabled logic.

## Versioning

Bump `config.json` version after implementation, before push (per project convention).
